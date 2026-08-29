"""Warframe upkeep: the daily staleness check and the weekly catalog sync.

Both were Celery beat entries until 2026-08-28 (`check-warframe-staleness`
daily at 12:00 UTC, `sync-warframe-catalog` Sundays at 04:00 UTC). They live
together because they are the same concern at the same scale — slow, periodic
tidying of the Warframe data — and apart from the 300s poller because a
heartbeat threshold is per worker and 300s against a week is not one number.

**Last-run state is in Redis, not memory.** A container restart must not
re-fire either job: `sync_catalog` is idempotent so a repeat is merely wasted
work, but `check_warframe_staleness` alerts, and an alert that fires again
because a container bounced is how people learn to ignore alerts. Redis also
means the state survives the deploy that restarts this.

The loop ticks every 60s and asks "is it past the target, and has it not run
in this period yet?" rather than sleeping until a computed time. A sleeping
process that misses its window because the host slept is a real failure mode;
a cheap tick that re-checks the clock is not.
"""

from __future__ import annotations

import logging
import time
from datetime import UTC
from datetime import datetime

import redis
from django.conf import settings
from django.core.management.base import BaseCommand

from apps.profiles.warframe.tasks import check_warframe_staleness
from apps.profiles.warframe.tasks import sync_catalog
from config.heartbeat import beat_boot
from config.heartbeat import beat_liveness
from config.heartbeat import beat_work

logger = logging.getLogger(__name__)

WORKER = "warframe-upkeep"
TICK_SECONDS = 60

# Same wall-clock slots the beat schedule used, so nothing moves for Bryan.
STALENESS_HOUR_UTC = 12
CATALOG_HOUR_UTC = 4
CATALOG_WEEKDAY = 6  # Sunday, matching crontab(day_of_week=0)

KEY_PREFIX = "warframe:upkeep"


def _client():
    return redis.from_url(settings.REDIS_URL, socket_connect_timeout=2)


def _already_ran(client, job: str, period: str) -> bool:
    """True when this job has already run for the given period key."""
    try:
        raw = client.get(f"{KEY_PREFIX}:{job}:last")
    except Exception:  # noqa: BLE001
        # Redis unreachable: refuse to run rather than risk a duplicate alert.
        # The heartbeat going stale is the signal; a double page is not.
        return True
    if raw is None:
        return False
    value = raw.decode() if isinstance(raw, bytes) else raw
    return value == period


def _mark_ran(client, job: str, period: str) -> None:
    try:
        # 40 days: comfortably past the weekly job's period without keeping
        # state for a job that has been removed.
        client.set(f"{KEY_PREFIX}:{job}:last", period, ex=40 * 24 * 3600)
    except Exception:  # noqa: BLE001
        logger.warning("[Warframe] could not record last-run for %s", job)


class Command(BaseCommand):
    help = "Warframe daily staleness check + weekly catalog sync (--loop for the container)"

    def add_arguments(self, parser):
        parser.add_argument("--loop", action="store_true")
        parser.add_argument(
            "--force",
            choices=["staleness", "catalog"],
            help="Run one job now regardless of schedule, for debugging.",
        )

    def handle(self, *args, **options):
        if options.get("force"):
            {"staleness": check_warframe_staleness, "catalog": sync_catalog}[
                options["force"]
            ]()
            return

        if not options["loop"]:
            self.stdout.write("Nothing to do without --loop or --force.")
            return

        beat_boot(WORKER)
        client = _client()
        while True:
            beat_liveness(WORKER)
            now = datetime.now(UTC)
            try:
                self._maybe_run(client, now)
                # The tick completing is the work. These jobs fire once a day
                # and once a week, so beating only when one runs would report
                # this worker dead almost always.
                beat_work(WORKER)
            except Exception:  # noqa: BLE001
                logger.exception("[Warframe] upkeep tick failed")
            time.sleep(TICK_SECONDS)

    def _maybe_run(self, client, now: datetime) -> None:
        if now.hour >= STALENESS_HOUR_UTC:
            period = now.strftime("%Y-%m-%d")
            if not _already_ran(client, "staleness", period):
                logger.info("[Warframe] running daily staleness check for %s", period)
                check_warframe_staleness()
                _mark_ran(client, "staleness", period)

        if now.weekday() == CATALOG_WEEKDAY and now.hour >= CATALOG_HOUR_UTC:
            # ISO year+week, so the key rolls over exactly once a week and does
            # not care how many Sundays a month has.
            period = f"{now.isocalendar().year}-W{now.isocalendar().week:02d}"
            if not _already_ran(client, "catalog", period):
                logger.info("[Warframe] running weekly catalog sync for %s", period)
                sync_catalog()
                _mark_ran(client, "catalog", period)
