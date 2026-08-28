"""Worker heartbeats: proof of recent work, not proof of a running process.

Follows the suite convention in `standards/conventions/health.md`; synthhome's
`apps/core/heartbeat.py` is the reference implementation and carries the full
reasoning. The shape:

    boot      once when the worker comes up. Absent means it never started.
    liveness  a task began. Proves the broker dispatched and the pool ran it.
    work      a task finished successfully.

`docker ps` reporting Up answers "is the process running", which was never the
question -- on 2026-08-21 three ingesters in a sibling project held dead
database connections for three hours while every container read Up.

**Wired through celery signals rather than into the tasks themselves.** The
distinction between "a task started" and "a task succeeded" is exactly the
liveness/work split, and celery already publishes both. Beating in the task
bodies would mean every future task has to remember to do it -- which is the
enrollment failure that left synthhome-vesync unmonitored for months, moved
one level down.

Writes never break the caller: a heartbeat is an observation, and an
observation that can take down the work it observes has the relationship
backwards.
"""

from __future__ import annotations

import logging
import time

import redis
from django.conf import settings

logger = logging.getLogger(__name__)

# Key shape: hb:<worker>:<kind>. Read by config/health.py.
KEY_PREFIX = "hb"

# A key that vanishes is as informative as one that goes stale, and it keeps
# Redis from accumulating keys for workers that no longer exist.
TTL_SECONDS = 24 * 60 * 60

# The celery container is one worker from the monitor's point of view; the
# beat scheduler and the pool live in the same process.
WORKER = "celery"

_warned = False


def _key(worker: str, kind: str) -> str:
    return f"{KEY_PREFIX}:{worker}:{kind}"


def _write(worker: str, kind: str) -> None:
    global _warned
    client = None
    try:
        client = redis.from_url(settings.REDIS_URL, socket_connect_timeout=2)
        client.set(_key(worker, kind), str(time.time()), ex=TTL_SECONDS)
        _warned = False
    except Exception as exc:  # noqa: BLE001 — see module docstring
        if not _warned:
            logger.warning(
                "[Heartbeat] Redis unavailable; beats paused. worker=%s error=%s",
                worker,
                exc,
            )
            _warned = True
    finally:
        if client is not None:
            try:
                client.close()
            except Exception:  # noqa: BLE001
                pass


def beat_boot(worker: str = WORKER) -> None:
    """Record that the worker process started.

    Without this the only anchor for "how long has it been silent?" is the web
    server's start time -- the wrong process entirely, since every deploy
    restarts it and would forgive a worker dead for hours.
    """
    _write(worker, "boot")


def beat_liveness(worker: str = WORKER) -> None:
    _write(worker, "liveness")


def beat_work(worker: str = WORKER) -> None:
    _write(worker, "work")
