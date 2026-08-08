"""import_umamusume — load merged career runs into Character/Outfit/CareerRun.

Consumes merge.py's runs.json. Idempotent: runs are keyed on their content
fingerprint, so re-importing the full file after adding new screenshots updates
what changed and inserts what's new. Safe to run repeatedly.

Reads a path or `-` for stdin, so new runs can go straight to prod:

    cat data/umamusume/runs.json | ssh saya \\
      'docker exec -i questlog-server uv run python manage.py import_umamusume -'
"""

from __future__ import annotations

import datetime
import json
import sys
import zoneinfo

from django.core.management.base import BaseCommand
from django.core.management.base import CommandError
from django.db import transaction
from django.utils.text import slugify

from apps.library.models import Work
from apps.profiles.umamusume.models import CareerRun
from apps.profiles.umamusume.models import Character
from apps.profiles.umamusume.models import Outfit
from apps.profiles.umamusume.models import Profile


def unique_slug(model, base: str, fallback: str) -> str:
    """Slug that survives names slugify empties out — [El☆Número 1], [pf. …]."""
    stem = slugify(base) or slugify(fallback) or "uma"
    slug, n = stem, 1
    while model.objects.filter(slug=slug).exists():
        n += 1
        slug = f"{stem}-{n}"
    return slug


class Command(BaseCommand):
    help = "Import merged Umamusume career runs from runs.json"

    def add_arguments(self, parser):
        parser.add_argument("runs", help="path to runs.json, or - for stdin")
        parser.add_argument("--work-slug", default="umamusume-pretty-derby")
        parser.add_argument(
            "--timezone",
            default="America/Los_Angeles",
            help="Screenshot timestamps are naive local wall-clock; this is the zone "
            "they were captured in. Guessing wrong shifts every run by hours.",
        )
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument(
            "--include-suspect",
            action="store_true",
            help="also import runs merge.py flagged as another trainer's uma",
        )

    def handle(self, *args, **options):
        source = options["runs"]
        raw = sys.stdin.read() if source == "-" else open(source).read()
        runs = json.loads(raw)

        try:
            tz = zoneinfo.ZoneInfo(options["timezone"])
        except zoneinfo.ZoneInfoNotFoundError as exc:
            raise CommandError(f"unknown timezone: {options['timezone']}") from exc

        try:
            work = Work.objects.get(slug=options["work_slug"])
        except Work.DoesNotExist as exc:
            raise CommandError(f"no Work with slug {options['work_slug']!r}") from exc

        skipped = [r for r in runs if r.get("suspect") and not options["include_suspect"]]
        runs = [r for r in runs if not r.get("suspect") or options["include_suspect"]]

        counts = {"characters": 0, "outfits": 0, "created": 0, "updated": 0}

        with transaction.atomic():
            profile, _ = Profile.objects.get_or_create(work=work)

            for run in sorted(runs, key=lambda r: r["run_date"]):
                name = run["character"]
                character = Character.objects.filter(profile=profile, name=name).first()
                if not character:
                    character = Character.objects.create(
                        profile=profile, name=name, slug=unique_slug(Character, name, name)
                    )
                    counts["characters"] += 1

                title = run.get("outfit_title") or ""
                outfit = Outfit.objects.filter(character=character, title=title).first()
                if not outfit:
                    outfit = Outfit.objects.create(
                        character=character,
                        title=title,
                        slug=unique_slug(Outfit, f"{name} {title}", name),
                    )
                    counts["outfits"] += 1

                naive = datetime.datetime.fromisoformat(run["run_date"])
                _, created = CareerRun.objects.update_or_create(
                    fingerprint=run["fingerprint"],
                    defaults={
                        "outfit": outfit,
                        "run_date": naive.replace(tzinfo=tz),
                        "platform": run["platform"],
                        "rank": run.get("rank") or "",
                        "rating": run.get("rating"),
                        "earned_title": run.get("earned_title") or "",
                        "speed": run.get("speed"),
                        "stamina": run.get("stamina"),
                        "power": run.get("power"),
                        "guts": run.get("guts"),
                        "wit": run.get("wit"),
                        "fans": run.get("fans"),
                        "races": run.get("races"),
                        "wins": run.get("wins"),
                        "aptitudes": run.get("aptitudes") or {},
                        "major_wins": run.get("major_wins") or [],
                        "support_cards": run.get("support_cards") or [],
                        "legacy": {"ranks": run.get("legacy_ranks") or []},
                        "source_images": run.get("source_images") or [],
                        "raw": run,
                    },
                )
                counts["created" if created else "updated"] += 1

            if options["dry_run"]:
                transaction.set_rollback(True)

        prefix = "[dry run] " if options["dry_run"] else ""
        self.stdout.write(
            self.style.SUCCESS(
                f"{prefix}{counts['created']} runs created, {counts['updated']} updated | "
                f"{counts['characters']} new characters, {counts['outfits']} new outfits"
            )
        )
        if skipped:
            self.stdout.write(f"{prefix}skipped {len(skipped)} flagged as another trainer's uma")
        if options["dry_run"]:
            self.stdout.write(self.style.WARNING("rolled back — nothing was written"))
