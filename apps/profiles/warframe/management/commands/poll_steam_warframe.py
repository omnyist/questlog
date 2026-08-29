"""The Warframe session poller — a looping container, not a Celery task.

Runs every 300s and detects Warframe session transitions via the Steam Web
API, triggering an archive on session end.

**Why this is a container and not a task.** Until 2026-08-28 this ran under
Celery beat. Measured before the change: queue depth peaked at 0 over a
60-second sample, beat was the only producer, and the prefork pool cost
715 MiB to run 194 tasks a day against a 105 MiB Django process. A broker
whose only producer is its own scheduler is a delivery mechanism between two
halves of one process.

**Why it is separate from `warframe_upkeep`.** Cadences here span two orders
of magnitude — 300s against daily and weekly — and a heartbeat threshold has
to be per worker or it is dishonest for one of them. One container would have
one identity and therefore one number: set it for this poller and a dead
weekly sync is invisible for six days. Two containers also mean `docker ps`
tells the truth about both, since Docker's restart machinery only ever sees
one lifecycle per container.

`--loop` is the container's entrypoint; without it this runs a single cycle,
which is what you want when debugging by hand.
"""

from __future__ import annotations

import time

from django.core.management.base import BaseCommand

from apps.profiles.warframe.tasks import poll_steam_warframe
from config.heartbeat import beat_boot
from config.heartbeat import beat_liveness
from config.heartbeat import beat_work

WORKER = "warframe"

# 300s, matching the schedule this replaced. The health endpoint allows ~2x.
INTERVAL_SECONDS = 300


class Command(BaseCommand):
    help = "Poll Steam for Warframe session transitions (--loop for the container)"

    def add_arguments(self, parser):
        parser.add_argument("--loop", action="store_true")
        parser.add_argument("--interval", type=int, default=INTERVAL_SECONDS)

    def handle(self, *args, **options):
        if not options["loop"]:
            poll_steam_warframe()
            return

        # Before the first cycle, so the health endpoint can tell "never
        # started" from "started but failing" -- the same seam synthhome uses.
        beat_boot(WORKER)
        while True:
            # Liveness before the attempt, work after it succeeds. Fresh
            # liveness with a stale work beat therefore reads "the loop is
            # running but Steam is refusing us", which is what an expired or
            # rate-limited API key looks like.
            beat_liveness(WORKER)
            try:
                poll_steam_warframe()
                # The cycle completing IS the work. Not "a session transition
                # was found" -- Bryan is not playing Warframe most of the time,
                # and gating the beat on a transition would report this worker
                # dead for days at a stretch.
                beat_work(WORKER)
            except Exception:
                self.stderr.write(
                    "[Warframe] poll cycle failed; retrying next interval"
                )
                import logging

                logging.getLogger(__name__).exception("poll_steam_warframe failed")
            time.sleep(options["interval"])
