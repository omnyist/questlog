"""The upkeep loop's scheduling — the part that replaced Celery beat.

beat guaranteed "once per slot" for free. A loop that ticks every 60s and asks
"is it past the target?" does not, so these pin the two properties that
guarantee has to keep: it fires when the slot arrives, and it fires exactly
once. The second matters more than it looks -- check_warframe_staleness
ALERTS, and an alert that repeats because a container bounced is how people
learn to ignore alerts.
"""

from __future__ import annotations

from datetime import UTC
from datetime import datetime
from unittest.mock import patch

from apps.profiles.warframe.management.commands.warframe_upkeep import Command


class FakeRedis:
    """Last-run state lives in Redis so a restart cannot re-fire a job."""

    def __init__(self, values: dict | None = None, unreachable: bool = False):
        self.d = dict(values or {})
        self.unreachable = unreachable

    def get(self, key):
        if self.unreachable:
            raise ConnectionError("redis is gone")
        return self.d.get(key)

    def set(self, key, value, ex=None):
        if self.unreachable:
            raise ConnectionError("redis is gone")
        self.d[key] = value


def _run(redis, when: datetime) -> list[str]:
    fired: list[str] = []
    mod = "apps.profiles.warframe.management.commands.warframe_upkeep"
    with (
        patch(f"{mod}.check_warframe_staleness", lambda: fired.append("staleness")),
        patch(f"{mod}.sync_catalog", lambda: fired.append("catalog")),
    ):
        Command()._maybe_run(redis, when)
    return fired


def test_nothing_fires_before_its_slot():
    assert _run(FakeRedis(), datetime(2026, 8, 31, 11, 0, tzinfo=UTC)) == []


def test_the_daily_check_fires_once_the_slot_arrives():
    assert _run(FakeRedis(), datetime(2026, 8, 31, 12, 30, tzinfo=UTC)) == ["staleness"]


def test_the_daily_check_does_not_fire_twice_in_one_day():
    """The property beat gave for free and a polling loop must earn."""
    r = FakeRedis()
    assert _run(r, datetime(2026, 8, 31, 12, 30, tzinfo=UTC)) == ["staleness"]
    assert _run(r, datetime(2026, 8, 31, 13, 0, tzinfo=UTC)) == []
    assert _run(r, datetime(2026, 8, 31, 23, 59, tzinfo=UTC)) == []


def test_a_new_day_fires_again():
    r = FakeRedis()
    _run(r, datetime(2026, 8, 31, 12, 30, tzinfo=UTC))
    assert _run(r, datetime(2026, 9, 1, 12, 30, tzinfo=UTC)) == ["staleness"]


def test_the_weekly_sync_fires_on_sunday_only():
    r = FakeRedis()
    # Sunday 05:00 is past the 04:00 catalog slot but before the 12:00 daily one,
    # so the catalog runs alone. The two schedules are independent.
    assert _run(r, datetime(2026, 9, 6, 5, 0, tzinfo=UTC)) == ["catalog"]
    assert _run(r, datetime(2026, 9, 6, 6, 0, tzinfo=UTC)) == []
    # Monday is not Sunday.
    assert "catalog" not in _run(r, datetime(2026, 9, 7, 5, 0, tzinfo=UTC))


def test_the_weekly_sync_fires_again_the_following_week():
    r = FakeRedis()
    _run(r, datetime(2026, 9, 6, 5, 0, tzinfo=UTC))
    assert _run(r, datetime(2026, 9, 13, 5, 0, tzinfo=UTC)) == ["catalog"]


def test_an_unreachable_redis_refuses_to_run_rather_than_risk_a_repeat():
    """Without last-run state there is no way to know whether a job already
    fired. Silence is recoverable -- the heartbeat goes stale and says so. A
    duplicate alert is not."""
    assert (
        _run(FakeRedis(unreachable=True), datetime(2026, 8, 31, 12, 30, tzinfo=UTC))
        == []
    )
