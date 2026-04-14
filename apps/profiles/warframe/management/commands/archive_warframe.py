"""archive_warframe — pulls the Warframe profile into the archive.

Single-phase, fully idempotent. Uses a short-lived Redis lock to prevent
concurrent runs (the session-end poller invokes this command inline).
"""

from __future__ import annotations

import asyncio

import redis
from django.conf import settings
from django.core.management.base import BaseCommand
from django.core.management.base import CommandError
from django.utils import timezone as django_tz

from apps.integrations.warframe import WarframeAPIError
from apps.integrations.warframe import WarframeClient
from apps.integrations.warframe import parse_bson_date
from apps.integrations.warframe import parse_oid
from apps.integrations.warframe import weapon_name_from_path
from apps.library.models import Work
from apps.profiles.warframe.events import publish_warframe_event
from apps.profiles.warframe.models import Affiliation
from apps.profiles.warframe.models import MissionStat
from apps.profiles.warframe.models import Profile
from apps.profiles.warframe.models import Snapshot
from apps.profiles.warframe.models import WeaponStat

LOCK_KEY = "questlog:locks:warframe_archive"
LOCK_TTL = 300  # 5 minutes


class Command(BaseCommand):
    help = "Archive the Warframe profile from the public content endpoint"

    def add_arguments(self, parser):
        parser.add_argument("--account-id", type=str, default=None)
        parser.add_argument(
            "--platform",
            type=str,
            default=None,
            choices=["pc", "ps", "xbox", "switch"],
        )
        parser.add_argument("--work-slug", type=str, default="warframe")
        parser.add_argument(
            "--trigger",
            type=str,
            default="manual",
            choices=["manual", "session_end", "scheduled"],
        )
        parser.add_argument("--no-snapshot", action="store_true")

    def handle(self, *args, **options):
        redis_client = redis.from_url(settings.REDIS_URL)
        got_lock = redis_client.set(LOCK_KEY, "1", nx=True, ex=LOCK_TTL)
        if not got_lock:
            raise CommandError("Another archive_warframe run is in progress")

        try:
            asyncio.run(self._run(options))
        finally:
            try:
                redis_client.delete(LOCK_KEY)
            except Exception:  # noqa: BLE001
                pass

    async def _run(self, options: dict) -> None:
        from asgiref.sync import sync_to_async

        account_id = options["account_id"] or settings.WARFRAME_ACCOUNT_ID
        platform = options["platform"] or settings.WARFRAME_PLATFORM or "pc"

        work = await sync_to_async(
            Work.objects.get_or_create, thread_sensitive=True
        )(slug=options["work_slug"], defaults={"name": "Warframe"})
        work = work[0]

        profile = await sync_to_async(
            Profile.objects.filter(work=work).first, thread_sensitive=True
        )()

        if profile is None:
            if not account_id:
                raise CommandError(
                    "First run requires --account-id or WARFRAME_ACCOUNT_ID in env"
                )
            profile = await sync_to_async(
                Profile.objects.create, thread_sensitive=True
            )(
                work=work,
                account_id=account_id,
                platform=platform,
                steam_id=settings.STEAM_ID or "",
            )
            self.stdout.write(self.style.SUCCESS(f"Created Profile for {account_id}"))
        elif account_id and account_id != profile.account_id:
            profile.account_id = account_id
            profile.platform = platform
            await sync_to_async(profile.save, thread_sensitive=True)(
                update_fields=["account_id", "platform", "updated_at"]
            )

        self.stdout.write(f"Fetching Warframe profile for {profile.account_id} ({profile.platform})...")

        client = WarframeClient()
        try:
            data = await client.get_profile(profile.account_id, platform=profile.platform)
        except WarframeAPIError as exc:
            await sync_to_async(publish_warframe_event)(
                "warframe:archive_failed",
                {"account_id": profile.account_id, "error": str(exc)},
            )
            raise CommandError(f"Warframe API error: {exc}") from exc

        results = data.get("Results", [])
        if not results:
            raise CommandError("Warframe returned no profile results")
        result = results[0]
        stats = data.get("Stats", {}) or {}

        await self._update_profile(profile, result, stats)
        weapons_tracked, total_weapon_kills = await self._sync_weapons(profile, stats)
        await self._sync_missions(profile, result)
        await self._sync_affiliations(profile, result)

        if not options["no_snapshot"]:
            await self._create_snapshot(
                profile,
                options["trigger"],
                data,
                weapons_tracked,
                total_weapon_kills,
            )

        profile.last_synced = django_tz.now()
        await sync_to_async(profile.save, thread_sensitive=True)(
            update_fields=["last_synced", "updated_at"]
        )

        summary = {
            "account_id": profile.account_id,
            "display_name": profile.display_name,
            "mastery_rank": profile.mastery_rank,
            "time_played_seconds": profile.time_played_seconds,
            "missions_completed": profile.missions_completed,
            "weapons_tracked": weapons_tracked,
            "total_weapon_kills": total_weapon_kills,
            "trigger": options["trigger"],
        }
        await sync_to_async(publish_warframe_event)("warframe:archive_complete", summary)

        self.stdout.write(
            self.style.SUCCESS(
                f"Archived {profile.display_name}: MR{profile.mastery_rank}, "
                f"{profile.missions_completed} missions, "
                f"{profile.time_played_seconds // 3600}h played, "
                f"{weapons_tracked} weapons, {total_weapon_kills} total kills"
            )
        )

    # ---- sub-phases ----

    async def _update_profile(self, profile: Profile, result: dict, stats: dict) -> None:
        from asgiref.sync import sync_to_async

        profile.display_name = result.get("DisplayName", "") or profile.display_name
        profile.wf_created_at = parse_bson_date(result.get("Created"))
        profile.player_level = int(result.get("PlayerLevel", 0) or 0)
        profile.title = result.get("TitleType", "") or ""
        profile.migrated_to_console = bool(result.get("MigratedToConsole", False))
        profile.daily_focus = int(result.get("DailyFocus", 0) or 0)

        profile.mastery_rank = int(stats.get("Rank", 0) or 0)
        profile.missions_completed = int(stats.get("MissionsCompleted", 0) or 0)
        profile.missions_quit = int(stats.get("MissionsQuit", 0) or 0)
        profile.missions_failed = int(stats.get("MissionsFailed", 0) or 0)
        profile.missions_interrupted = int(stats.get("MissionsInterrupted", 0) or 0)
        profile.missions_dumped = int(stats.get("MissionsDumped", 0) or 0)
        profile.time_played_seconds = int(stats.get("TimePlayedSec", 0) or 0)
        profile.pickup_count = int(stats.get("PickupCount", 0) or 0)

        # Store the account_id from the response too (belt-and-suspenders)
        if not profile.account_id:
            profile.account_id = parse_oid(result.get("AccountId")) or profile.account_id

        profile.profile_data = result
        profile.stats_data = stats

        await sync_to_async(profile.save, thread_sensitive=True)()

    async def _sync_weapons(self, profile: Profile, stats: dict) -> tuple[int, int]:
        from asgiref.sync import sync_to_async

        weapons = stats.get("Weapons") or []
        total_kills = 0
        tracked = 0

        for w in weapons:
            path = w.get("type", "")
            if not path:
                continue
            fired = int(w.get("fired", 0) or 0)
            hits = int(w.get("hits", 0) or 0)
            kills = int(w.get("kills", 0) or 0)
            headshots = int(w.get("headshots", 0) or 0)
            accuracy = (hits / fired) if fired else 0.0
            headshot_rate = (headshots / kills) if kills else 0.0

            defaults = {
                "weapon_name": weapon_name_from_path(path),
                "fired": fired,
                "hits": hits,
                "kills": kills,
                "headshots": headshots,
                "assists": int(w.get("assists", 0) or 0),
                "equip_time_seconds": float(w.get("equipTime", 0) or 0),
                "xp": int(w.get("xp", 0) or 0),
                "accuracy": round(accuracy, 4),
                "headshot_rate": round(headshot_rate, 4),
            }
            await sync_to_async(
                WeaponStat.objects.update_or_create, thread_sensitive=True
            )(profile=profile, weapon_path=path, defaults=defaults)
            total_kills += kills
            tracked += 1

        return tracked, total_kills

    async def _sync_missions(self, profile: Profile, result: dict) -> None:
        from asgiref.sync import sync_to_async

        missions = result.get("Missions") or []
        for m in missions:
            tag = m.get("Tag", "")
            if not tag:
                continue
            completes = int(m.get("Completes", 0) or 0)
            await sync_to_async(
                MissionStat.objects.update_or_create, thread_sensitive=True
            )(profile=profile, node_tag=tag, defaults={"completes": completes})

    async def _sync_affiliations(self, profile: Profile, result: dict) -> None:
        from asgiref.sync import sync_to_async

        affiliations = result.get("Affiliations") or []
        for a in affiliations:
            tag = a.get("Tag", "")
            if not tag:
                continue
            await sync_to_async(
                Affiliation.objects.update_or_create, thread_sensitive=True
            )(
                profile=profile,
                syndicate_tag=tag,
                defaults={
                    "standing": int(a.get("Standing", 0) or 0),
                    "title_rank": int(a.get("Title", 0) or 0),
                },
            )

    async def _create_snapshot(
        self,
        profile: Profile,
        trigger: str,
        raw_data: dict,
        weapons_tracked: int,
        total_weapon_kills: int,
    ) -> None:
        from asgiref.sync import sync_to_async

        await sync_to_async(Snapshot.objects.create, thread_sensitive=True)(
            profile=profile,
            trigger=trigger,
            mastery_rank=profile.mastery_rank,
            time_played_seconds=profile.time_played_seconds,
            missions_completed=profile.missions_completed,
            pickup_count=profile.pickup_count,
            total_weapon_kills=total_weapon_kills,
            weapons_tracked=weapons_tracked,
            raw_profile=raw_data,
        )
