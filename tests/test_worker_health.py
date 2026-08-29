"""The `workers` block in /health/ — questlog's half of the suite convention.

`standards/conventions/health.md` is the contract; synthhome is the reference
implementation. These tests pin the two properties that matter most here and
that are easiest to get wrong for a looping container: a healthy worker stays
silent, and a worker nobody enrolled does not.

No database: these call the worker check directly with a fake Redis, so they
run anywhere the suite does.
"""

from __future__ import annotations

import time
from unittest.mock import patch

from config.health import WORKER_THRESHOLDS
from config.health import _worker_health


class FakeRedis:
    """Stands in for Redis so beat ages can be dictated exactly."""

    def __init__(self, values: dict[str, str] | None = None, raises: bool = False):
        self._values = values or {}
        self._raises = raises

    def get(self, key):
        if self._raises:
            raise ConnectionError("redis is gone")
        return self._values.get(key)

    def scan_iter(self, match=None):
        if self._raises:
            raise ConnectionError("redis is gone")
        return iter(list(self._values))

    def close(self):
        pass


def _beats(**ages: float) -> dict[str, str]:
    """Beat keys with the given ages; unnamed workers get fresh beats."""
    now = time.time()
    values: dict[str, str] = {}
    for worker in WORKER_THRESHOLDS:
        for kind in ("boot", "liveness", "work"):
            values[f"hb:{worker}:{kind}"] = str(now - ages.get(f"{worker}_{kind}", 1.0))
    return values


def _run(fake: FakeRedis) -> dict:
    status: dict = {"status": "ok", "services": {}}
    with patch("config.health.redis.from_url", return_value=fake):
        _worker_health(status)
    return status


def test_a_healthy_poller_is_silent():
    """The property that decides whether a monitor survives contact with a
    human: a monitor that cannot stay quiet is the one that gets muted."""
    status = _run(FakeRedis(_beats()))

    assert status["services"]["workers"] == "ok"
    assert status["status"] == "ok"


def test_a_task_that_finds_nothing_is_not_a_dead_worker():
    """poll_steam_warframe returns None on almost every run -- Bryan is not
    playing Warframe most of the time. The work beat fires on task success,
    not on the task having found something, so a quiet day must look identical
    to a busy one."""
    quiet = WORKER_THRESHOLDS["warframe"] - 60
    status = _run(FakeRedis(_beats(warframe_work=quiet)))

    assert status["services"]["workers"] == "ok"
    assert status["status"] == "ok"


def test_a_stale_work_beat_degrades_and_names_the_worker():
    """A broker that dispatches into a pool that cannot reach Postgres looks
    exactly like this: tasks keep starting, so liveness stays fresh, and none
    of them ever succeed."""
    stale = WORKER_THRESHOLDS["warframe"] + 120
    status = _run(FakeRedis(_beats(warframe_work=stale)))

    assert status["status"] == "degraded"
    assert "warframe.work" in status["services"]["workers"]


def test_a_worker_that_never_beat_is_not_forgiven_forever():
    """A process that never starts is the loudest possible failure and must
    not render as silence."""
    beats = _beats()
    del beats["hb:warframe:work"]
    beats["hb:warframe:boot"] = str(time.time() - 99_999)

    status = _run(FakeRedis(beats))

    assert status["status"] == "degraded"
    assert "never beat" in status["services"]["workers"]


def test_a_worker_beating_without_a_threshold_is_reported():
    """Enrollment by hand is how synthhome-vesync stayed invisible for months:
    running, beating, and checked by nobody."""
    beats = _beats()
    now = time.time()
    for kind in ("boot", "liveness", "work"):
        beats[f"hb:newcomer:{kind}"] = str(now - 7200)

    status = _run(FakeRedis(beats))

    assert "newcomer" in status["services"]["workers_unenrolled"]
    assert status["status"] == "degraded"


def test_redis_down_is_unknown_not_a_pile_of_dead_workers():
    """A Redis outage and a dead poller are different incidents; collapsing
    them sends someone to the wrong place."""
    status = _run(FakeRedis(raises=True))

    assert "unknown" in status["services"]["workers"]
    assert "warframe" not in status["services"]["workers"]
