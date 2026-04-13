"""archive_destiny — pulls Destiny 2 history from Bungie's API into the archive.

Phases (all idempotent, safe to re-run):
    1. manifest     — download/cache the Bungie manifest SQLite DB
    2. profile      — fetch profile components, store raw blobs
    3. characters   — fetch character details, resolve class/race/gender
    4. stats        — account + per-character historical stats, every mode
    5. activities   — paginate all activity history (supports --incremental)
    6. pgcr         — Post-Game Carnage Reports for raids/dungeons (optional)
"""

from __future__ import annotations

import asyncio
from datetime import UTC
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.core.management.base import CommandError
from django.utils import timezone as django_tz

from apps.integrations.bungie import BungieAPIError
from apps.integrations.bungie import BungieClient
from apps.library.models import Work
from apps.profiles.destiny.manifest import ManifestResolver
from apps.profiles.destiny.manifest import extract_manifest_if_zipped
from apps.profiles.destiny.manifest import mode_category_for
from apps.profiles.destiny.models import Activity
from apps.profiles.destiny.models import AggregateStats
from apps.profiles.destiny.models import CarnageReport
from apps.profiles.destiny.models import CarnageReportEntry
from apps.profiles.destiny.models import Character
from apps.profiles.destiny.models import ManifestCache
from apps.profiles.destiny.models import Profile

PHASES = ["manifest", "profile", "characters", "stats", "activities", "pgcr"]

# Full stat field map: Bungie stat key → model field name.
STAT_FIELD_MAP: dict[str, str] = {
    "activitiesEntered": "activities_entered",
    "activitiesWon": "activities_won",
    "activitiesCleared": "activities_cleared",
    "kills": "kills",
    "deaths": "deaths",
    "assists": "assists",
    "precisionKills": "precision_kills",
    "suicides": "suicides",
    "bestSingleGameKills": "best_single_game_kills",
    "longestKillSpree": "longest_kill_spree",
    "longestSingleLife": "longest_single_life",
    "orbsDropped": "orbs_dropped",
    "resurrectionsPerformed": "resurrections_performed",
    "resurrectionsReceived": "resurrections_received",
    "secondsPlayed": "seconds_played",
    "averageLifespan": "average_lifespan",
    "killsDeathsRatio": "kd_ratio",
    "killsDeathsAssists": "kda_ratio",
    "efficiency": "efficiency",
    "bestSingleGameScore": "best_single_game_score",
    "fastestCompletionMs": "fastest_completion",
    "longestKillDistance": "longest_kill_distance",
    "totalKillDistance": "total_kill_distance",
    "highestLightLevel": "highest_light_level",
    "combatRating": "combat_rating",
}


def basic_value(stat_dict: dict | None) -> float | int:
    """Extract the basic numeric value from a Bungie stat entry."""
    if not stat_dict:
        return 0
    return stat_dict.get("basic", {}).get("value", 0) or 0


def parse_period(period_str: str) -> datetime:
    """Parse a Bungie ISO timestamp into a tz-aware datetime."""
    if period_str.endswith("Z"):
        period_str = period_str[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(period_str)
    except ValueError:
        return datetime.now(tz=UTC)


class Command(BaseCommand):
    help = "Archive Destiny 2 history from Bungie's API"

    def add_arguments(self, parser):
        parser.add_argument("--membership-type", type=int, default=None)
        parser.add_argument("--membership-id", type=str, default=None)
        parser.add_argument(
            "--work-slug",
            type=str,
            default="destiny-2",
            help="Slug of the Work record to attach the Profile to",
        )
        parser.add_argument(
            "--phase",
            type=str,
            default="all",
            choices=["all", *PHASES],
        )
        parser.add_argument(
            "--incremental",
            action="store_true",
            help="Activities: stop at first already-seen instance (default after first run)",
        )
        parser.add_argument(
            "--full",
            action="store_true",
            help="Force full pagination even if activities exist",
        )
        parser.add_argument(
            "--pgcr",
            action="store_true",
            help="Also fetch Post-Game Carnage Reports for raids/dungeons",
        )
        parser.add_argument(
            "--pgcr-modes",
            nargs="+",
            default=["raid", "dungeon"],
            help="Which mode_categories to fetch PGCRs for",
        )

    def handle(self, *args, **options):
        if not settings.BUNGIE_API_KEY:
            raise CommandError("BUNGIE_API_KEY is not set in the environment")
        asyncio.run(self._run(options))

    async def _run(self, options: dict) -> None:
        from asgiref.sync import sync_to_async

        client = BungieClient()
        work = await self._get_or_create_work(options["work_slug"])
        profile = await self._get_profile(work, options)

        phase = options["phase"]
        run_all = phase == "all"

        resolver: ManifestResolver | None = None
        manifest_phase_ran = run_all or phase == "manifest"
        needs_manifest = run_all or phase in {"characters", "activities"}

        if manifest_phase_ran:
            resolver = await self._phase_manifest(client)
        elif needs_manifest:
            resolver = await self._load_existing_manifest()

        try:
            if run_all or phase == "profile":
                await self._phase_profile(client, profile)

            if run_all or phase == "characters":
                if resolver is None:
                    resolver = await self._phase_manifest(client)
                await self._phase_characters(client, profile, resolver)

            if run_all or phase == "stats":
                await self._phase_stats(client, profile)

            if run_all or phase == "activities":
                if resolver is None:
                    resolver = await self._phase_manifest(client)
                has_existing = await sync_to_async(
                    Activity.objects.filter(profile=profile).exists,
                    thread_sensitive=True,
                )()
                incremental = options["incremental"] or (
                    not options["full"] and has_existing
                )
                await self._phase_activities(client, profile, resolver, incremental)

            if options["pgcr"] or phase == "pgcr":
                await self._phase_pgcr(client, profile, options["pgcr_modes"])
        finally:
            if resolver:
                resolver.close()

        profile.last_synced = django_tz.now()
        await sync_to_async(profile.save, thread_sensitive=True)(
            update_fields=["last_synced", "updated_at"]
        )
        self.stdout.write(self.style.SUCCESS("Archive complete."))

    # ---- setup helpers ----

    async def _get_or_create_work(self, slug: str) -> Work:
        from asgiref.sync import sync_to_async

        work, created = await sync_to_async(
            Work.objects.get_or_create, thread_sensitive=True
        )(slug=slug, defaults={"name": "Destiny 2"})
        if created:
            self.stdout.write(self.style.SUCCESS(f"Created Work: {work.name}"))
        return work

    async def _get_profile(self, work: Work, options: dict) -> Profile:
        from asgiref.sync import sync_to_async

        existing = await sync_to_async(
            Profile.objects.filter(work=work).first, thread_sensitive=True
        )()

        membership_type = options["membership_type"]
        membership_id = options["membership_id"]

        if existing is None:
            if not membership_type or not membership_id:
                raise CommandError(
                    "First run requires --membership-type and --membership-id"
                )
            profile = await sync_to_async(Profile.objects.create, thread_sensitive=True)(
                work=work,
                membership_type=membership_type,
                membership_id=membership_id,
            )
            return profile

        if membership_type or membership_id:
            if membership_type:
                existing.membership_type = membership_type
            if membership_id:
                existing.membership_id = membership_id
            await sync_to_async(existing.save, thread_sensitive=True)(
                update_fields=["membership_type", "membership_id", "updated_at"]
            )
        return existing

    def _manifest_dir(self) -> Path:
        return Path(settings.BASE_DIR) / "data" / "destiny_manifest"

    async def _load_existing_manifest(self) -> ManifestResolver | None:
        from asgiref.sync import sync_to_async

        latest = await sync_to_async(
            ManifestCache.objects.order_by("-downloaded_at").first,
            thread_sensitive=True,
        )()
        if not latest or not latest.file_path:
            return None
        path = Path(latest.file_path)
        if not path.exists():
            return None
        return ManifestResolver(path)

    # ---- phase 1: manifest ----

    async def _phase_manifest(self, client: BungieClient) -> ManifestResolver:
        from asgiref.sync import sync_to_async

        self.stdout.write("Phase 1: Manifest")
        manifest_meta = await client.get_manifest()
        version = manifest_meta.get("version", "unknown")

        existing = await sync_to_async(
            ManifestCache.objects.filter(version=version).first, thread_sensitive=True
        )()
        if existing and existing.file_path and Path(existing.file_path).exists():
            self.stdout.write(f"  Manifest {version} already cached")
            return ManifestResolver(existing.file_path)

        self.stdout.write(f"  Downloading manifest version {version}...")
        dest_dir = self._manifest_dir()
        downloaded_path, _ = await client.download_manifest_database(dest_dir)
        usable_path = extract_manifest_if_zipped(downloaded_path)

        await sync_to_async(
            ManifestCache.objects.update_or_create, thread_sensitive=True
        )(
            version=version,
            defaults={"file_path": str(usable_path), "locale": "en"},
        )
        self.stdout.write(self.style.SUCCESS(f"  Cached manifest at {usable_path}"))
        return ManifestResolver(usable_path)

    # ---- phase 2: profile ----

    async def _phase_profile(self, client: BungieClient, profile: Profile) -> None:
        from asgiref.sync import sync_to_async

        self.stdout.write("Phase 2: Profile")
        data = await client.get_profile(
            profile.membership_type,
            profile.membership_id,
            components=[100, 200, 800, 900, 1100],
        )

        profile_component = data.get("profile", {}).get("data", {})
        user_info = profile_component.get("userInfo", {})

        profile.bungie_name = user_info.get("bungieGlobalDisplayName", "") or user_info.get("displayName", "")
        profile.bungie_name_code = user_info.get("bungieGlobalDisplayNameCode")
        profile.profile_data = profile_component
        profile.metrics_data = data.get("metrics", {}).get("data", {})
        profile.collectibles_data = data.get("profileCollectibles", {}).get("data", {})
        profile.records_data = data.get("profileRecords", {}).get("data", {})

        await sync_to_async(profile.save, thread_sensitive=True)()

        char_count = len(profile_component.get("characterIds", []))
        self.stdout.write(
            self.style.SUCCESS(
                f"  {profile.bungie_name}#{profile.bungie_name_code or 0:04d} "
                f"({char_count} characters)"
            )
        )

        # Stash the component data for phase 3 to use.
        profile._characters_component = data.get("characters", {}).get("data", {})

    # ---- phase 3: characters ----

    async def _phase_characters(
        self,
        client: BungieClient,
        profile: Profile,
        resolver: ManifestResolver,
    ) -> None:
        from asgiref.sync import sync_to_async

        self.stdout.write("Phase 3: Characters")
        characters_data = getattr(profile, "_characters_component", None)
        if characters_data is None:
            data = await client.get_profile(
                profile.membership_type,
                profile.membership_id,
                components=[200],
            )
            characters_data = data.get("characters", {}).get("data", {})

        for char_id, char in characters_data.items():
            class_name = resolver.resolve_class(char.get("classHash", 0))
            race_name = resolver.resolve_race(char.get("raceHash", 0))
            gender_name = resolver.resolve_gender(char.get("genderHash", 0))

            if gender_name in {"masculine"}:
                gender_name = "male"
            elif gender_name in {"feminine"}:
                gender_name = "female"

            date_last_played = char.get("dateLastPlayed")
            last_played = parse_period(date_last_played) if date_last_played else None

            defaults = {
                "profile": profile,
                "character_class": class_name if class_name in {"titan", "hunter", "warlock"} else "",
                "race": race_name if race_name in {"human", "awoken", "exo"} else "",
                "gender": gender_name if gender_name in {"male", "female"} else "",
                "light_level": char.get("light", 0),
                "minutes_played": int(char.get("minutesPlayedTotal", 0) or 0),
                "date_last_played": last_played,
                "emblem_path": char.get("emblemPath", "") or "",
                "emblem_background_path": char.get("emblemBackgroundPath", "") or "",
                "is_deleted": False,
                "raw_data": char,
            }

            character, _ = await sync_to_async(
                Character.objects.update_or_create, thread_sensitive=True
            )(character_id=char_id, defaults=defaults)
            self.stdout.write(
                f"  {character.get_character_class_display()} {character.character_id} "
                f"(light {character.light_level}, {character.minutes_played // 60}h)"
            )

    # ---- phase 4: stats ----

    async def _phase_stats(self, client: BungieClient, profile: Profile) -> None:
        from asgiref.sync import sync_to_async

        self.stdout.write("Phase 4: Stats")

        account_stats = await client.get_historical_stats_account(
            profile.membership_type, profile.membership_id
        )

        merged_all = account_stats.get("mergedAllCharacters", {}).get("results", {})
        merged_deleted = account_stats.get("mergedDeletedCharacters", {}).get("results", {})

        count = 0
        for mode_key, mode_data in merged_all.items():
            all_time = mode_data.get("allTime", {})
            if not all_time:
                continue
            await self._save_aggregate(profile, None, "account", mode_key, all_time)
            count += 1

        for mode_key, mode_data in merged_deleted.items():
            all_time = mode_data.get("allTime", {})
            if not all_time:
                continue
            await self._save_aggregate(profile, None, "account_deleted", mode_key, all_time)
            count += 1

        characters = await sync_to_async(
            list, thread_sensitive=True
        )(Character.objects.filter(profile=profile))

        for character in characters:
            try:
                char_stats = await client.get_historical_stats_character(
                    profile.membership_type,
                    profile.membership_id,
                    character.character_id,
                )
            except BungieAPIError as e:
                self.stdout.write(self.style.WARNING(f"  Skipping character stats: {e}"))
                continue

            for mode_key, mode_data in char_stats.items():
                all_time = mode_data.get("allTime", {})
                if not all_time:
                    continue
                await self._save_aggregate(profile, character, "character", mode_key, all_time)
                count += 1

        self.stdout.write(self.style.SUCCESS(f"  {count} aggregate stat rows saved"))

    async def _save_aggregate(
        self,
        profile: Profile,
        character: Character | None,
        scope: str,
        mode_key: str,
        all_time: dict,
    ) -> None:
        from asgiref.sync import sync_to_async

        defaults = {"raw_stats": all_time}
        for bungie_key, field_name in STAT_FIELD_MAP.items():
            defaults[field_name] = basic_value(all_time.get(bungie_key))

        # fastestCompletionMs is in milliseconds — convert to seconds for the model.
        if defaults.get("fastest_completion"):
            defaults["fastest_completion"] = defaults["fastest_completion"] / 1000.0

        await sync_to_async(
            AggregateStats.objects.update_or_create, thread_sensitive=True
        )(
            profile=profile,
            character=character,
            scope=scope,
            mode=mode_key,
            defaults=defaults,
        )

    # ---- phase 5: activities ----

    async def _phase_activities(
        self,
        client: BungieClient,
        profile: Profile,
        resolver: ManifestResolver,
        incremental: bool,
    ) -> None:
        from asgiref.sync import sync_to_async

        self.stdout.write(
            f"Phase 5: Activities ({'incremental' if incremental else 'full'})"
        )

        characters = await sync_to_async(
            list, thread_sensitive=True
        )(Character.objects.filter(profile=profile))

        for character in characters:
            self.stdout.write(
                f"  Character {character.get_character_class_display()} "
                f"({character.character_id})"
            )
            page = 0
            total_added = 0
            stop = False

            while not stop:
                try:
                    data = await client.get_activity_history(
                        profile.membership_type,
                        profile.membership_id,
                        character.character_id,
                        mode=0,
                        count=250,
                        page=page,
                    )
                except BungieAPIError as e:
                    self.stdout.write(self.style.WARNING(f"    Page {page} error: {e}"))
                    break

                activities = data.get("activities", [])
                if not activities:
                    break

                for raw in activities:
                    details = raw.get("activityDetails", {})
                    instance_id = str(details.get("instanceId", ""))
                    if not instance_id:
                        continue

                    exists = await sync_to_async(
                        Activity.objects.filter(instance_id=instance_id).exists,
                        thread_sensitive=True,
                    )()
                    if exists:
                        if incremental:
                            stop = True
                            break
                        continue

                    await self._save_activity(profile, character, raw, resolver)
                    total_added += 1

                self.stdout.write(f"    Page {page}: {total_added} new so far")
                page += 1

            self.stdout.write(
                self.style.SUCCESS(
                    f"    {character.get_character_class_display()}: {total_added} activities archived"
                )
            )

    async def _save_activity(
        self,
        profile: Profile,
        character: Character,
        raw: dict,
        resolver: ManifestResolver,
    ) -> None:
        from asgiref.sync import sync_to_async

        details = raw.get("activityDetails", {})
        activity_hash = details.get("referenceId", 0) or 0
        instance_id = str(details.get("instanceId", ""))
        mode = details.get("mode", 0) or 0
        modes = details.get("modes", []) or []

        resolved = resolver.resolve_activity(activity_hash)
        mode_name = resolver.resolve_activity_mode(mode) if mode else ""
        mode_category = mode_category_for(modes + [mode])

        values = raw.get("values", {})
        period = parse_period(raw.get("period", ""))

        completion_reason_dict = values.get("completionReason", {}).get("basic", {})
        completion_reason = int(completion_reason_dict.get("value", 0) or 0)
        completed_flag = bool(basic_value(values.get("completed")))
        standing = values.get("standing", {}).get("basic", {}).get("value")
        duration = int(basic_value(values.get("activityDurationSeconds")))

        fields = {
            "profile": profile,
            "character": character,
            "activity_hash": activity_hash,
            "activity_type_hash": resolved.get("activity_type_hash") or 0,
            "director_activity_hash": details.get("directorActivityHash", 0) or 0,
            "activity_name": resolved.get("name", "") or "",
            "mode": mode,
            "mode_name": mode_name,
            "mode_category": mode_category,
            "period": period,
            "duration_seconds": duration,
            "completed": completed_flag,
            "standing": int(standing) if standing is not None else None,
            "kills": int(basic_value(values.get("kills"))),
            "deaths": int(basic_value(values.get("deaths"))),
            "assists": int(basic_value(values.get("assists"))),
            "score": int(basic_value(values.get("score"))),
            "team_score": int(basic_value(values.get("teamScore"))),
            "kd_ratio": float(basic_value(values.get("killsDeathsRatio"))),
            "efficiency": float(basic_value(values.get("efficiency"))),
            "completion_reason": completion_reason,
            "raw_values": raw,
        }

        await sync_to_async(
            Activity.objects.create, thread_sensitive=True
        )(instance_id=instance_id, **fields)

    # ---- phase 6: PGCRs ----

    async def _phase_pgcr(
        self,
        client: BungieClient,
        profile: Profile,
        pgcr_modes: list[str],
    ) -> None:
        from asgiref.sync import sync_to_async

        self.stdout.write(f"Phase 6: PGCRs ({', '.join(pgcr_modes)})")

        qs_factory = Activity.objects.filter(
            profile=profile,
            mode_category__in=pgcr_modes,
            carnage_report__isnull=True,
        ).order_by("-period")
        pending = await sync_to_async(list, thread_sensitive=True)(qs_factory)
        total = len(pending)
        self.stdout.write(f"  {total} PGCRs to fetch")

        for idx, activity in enumerate(pending, start=1):
            try:
                data = await client.get_pgcr(activity.instance_id)
            except BungieAPIError as e:
                self.stdout.write(self.style.WARNING(f"  [{idx}/{total}] {activity.instance_id}: {e}"))
                continue

            period = parse_period(data.get("period", ""))
            report = await sync_to_async(
                CarnageReport.objects.create, thread_sensitive=True
            )(
                activity=activity,
                instance_id=activity.instance_id,
                activity_hash=activity.activity_hash,
                activity_name=activity.activity_name,
                period=period,
                is_private=bool(data.get("activityWasStartedFromBeginning", False) is False and data.get("isPrivate", False)),
                starting_phase_index=int(data.get("startingPhaseIndex", 0) or 0),
                raw_data=data,
            )

            entries = data.get("entries", [])
            for entry in entries:
                player = entry.get("player", {})
                dest_user = player.get("destinyUserInfo", {})
                character_class = player.get("characterClass", "") or ""
                values = entry.get("values", {})

                membership_id = str(dest_user.get("membershipId", ""))
                is_self = (
                    membership_id == profile.membership_id
                    and dest_user.get("membershipType") == profile.membership_type
                )

                await sync_to_async(
                    CarnageReportEntry.objects.create, thread_sensitive=True
                )(
                    report=report,
                    membership_id=membership_id,
                    membership_type=int(dest_user.get("membershipType", 0) or 0),
                    display_name=dest_user.get("displayName", "") or "",
                    character_id=str(entry.get("characterId", "")),
                    character_class=character_class.lower() if character_class else "",
                    light_level=int(player.get("lightLevel", 0) or 0),
                    is_self=is_self,
                    kills=int(basic_value(values.get("kills"))),
                    deaths=int(basic_value(values.get("deaths"))),
                    assists=int(basic_value(values.get("assists"))),
                    score=int(basic_value(values.get("score"))),
                    completed=bool(basic_value(values.get("completed"))),
                    time_played_seconds=int(basic_value(values.get("timePlayedSeconds"))),
                    raw_values=entry,
                )

            if idx % 10 == 0 or idx == total:
                self.stdout.write(f"  [{idx}/{total}] {activity.activity_name}")

        self.stdout.write(self.style.SUCCESS(f"  PGCR phase complete: {total} processed"))
