"""Shared loop for synchronous, no-request-cycle `--loop` management commands.

`poll_steam_warframe` and `warframe_upkeep` carried byte-for-byte identical
`while True` bodies before this existed: liveness beat, try the tick, work
beat on success, sleep. That duplication is why `close_old_connections()` had
to be added by hand in both places in the same sitting (2026-09-08) -- neither
command's `--loop` had it, both are long-lived processes with no request
cycle to return the connection on their own, and a third worker copying the
loop without copying the fix is the failure this collapses. A subclass of the
enrollment-failure reasoning `config/heartbeat.py` already documents for
beats, applied one level down to the loop that calls them.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable

from django.db import close_old_connections

from config.heartbeat import beat_boot
from config.heartbeat import beat_liveness
from config.heartbeat import beat_work

logger = logging.getLogger(__name__)


def run_worker_loop(worker: str, interval: int, tick: Callable[[], None]) -> None:
    """Run `tick()` every `interval` seconds forever, with beats and connection hygiene.

    `tick` takes no arguments and returns nothing; a tick that needs its own
    per-iteration state (e.g. the current time) computes it inside itself
    rather than receiving it here, so this stays a plain callable and not
    another thing every caller has to shape around.
    """
    beat_boot(worker)
    while True:
        # Liveness before the attempt, work after it succeeds -- fresh
        # liveness with a stale work beat reads as "the loop is running but
        # the tick keeps failing", not as a dead process.
        beat_liveness(worker)
        try:
            # No request cycle, so nothing else ever returns this thread's
            # connection. See the module docstring.
            close_old_connections()
            tick()
            beat_work(worker)
        except Exception:
            logger.exception("[%s] tick failed; retrying next interval", worker)
        time.sleep(interval)
