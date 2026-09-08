"""run_worker_loop is the structural home for the 2026-09-08 connection-release
fix: poll_steam_warframe and warframe_upkeep both had byte-for-byte identical
loops missing close_old_connections() until an adversarial review found it in
both places in the same sitting. These pin the guarantee this class exists to
make so a future edit can't quietly drop it.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from config.worker_loop import run_worker_loop


class _StopLoop(Exception):
    """Escapes the infinite loop deterministically instead of really sleeping."""


def _patched(calls):
    return (
        patch(
            "config.worker_loop.close_old_connections",
            side_effect=lambda: calls.append("close"),
        ),
        patch(
            "config.worker_loop.beat_boot",
            side_effect=lambda w: calls.append(f"boot:{w}"),
        ),
        patch(
            "config.worker_loop.beat_liveness",
            side_effect=lambda w: calls.append(f"live:{w}"),
        ),
        patch(
            "config.worker_loop.beat_work",
            side_effect=lambda w: calls.append(f"work:{w}"),
        ),
    )


def test_boot_then_release_before_every_tick_then_work_beat_then_sleep():
    calls: list[str] = []

    def tick():
        calls.append("tick")

    def fake_sleep(seconds):
        calls.append(f"sleep:{seconds}")
        raise _StopLoop

    p1, p2, p3, p4 = _patched(calls)
    with p1, p2, p3, p4, patch("config.worker_loop.time.sleep", side_effect=fake_sleep):
        with pytest.raises(_StopLoop):
            run_worker_loop("demo", 42, tick)

    assert calls == [
        "boot:demo",
        "live:demo",
        "close",
        "tick",
        "work:demo",
        "sleep:42",
    ]


def test_a_failing_tick_is_logged_and_the_loop_continues():
    """The tick raising must not skip the sleep or kill the process -- next
    interval retries, same as every other loop this pattern replaced."""
    calls: list[str] = []

    def failing_tick():
        raise RuntimeError("boom")

    def fake_sleep(seconds):
        calls.append(f"sleep:{seconds}")
        raise _StopLoop

    p1, p2, p3, p4 = _patched(calls)
    with p1, p2, p3, p4, patch("config.worker_loop.time.sleep", side_effect=fake_sleep):
        with pytest.raises(_StopLoop):
            run_worker_loop("demo", 5, failing_tick)

    # work:demo must be ABSENT -- a failed tick is not work.
    assert calls == ["boot:demo", "live:demo", "close", "sleep:5"]
