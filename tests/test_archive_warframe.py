"""archive_warframe._run must release+re-prove its DB connection on the
SAME thread its ORM calls actually run on.

`_run` is invoked via `asyncio.run()` from a plain sync `handle()`, so its
`sync_to_async(..., thread_sensitive=True)` calls fall through to asgiref's
process-wide `SyncToAsync.single_thread_executor` -- a persistent OS thread
distinct from both the caller's thread and Django's main-thread connection
registry. `run_worker_loop`'s own `close_old_connections()` (called on the
*loop's* thread, once per tick) never reaches it, because Django's connection
registry is thread-local. That stranded connection is what PgBouncer's
transaction pooling recycled out from under `poll_steam_warframe --loop`,
producing QUESTLOG-G/QUESTLOG-F ("the connection is closed").

This test fails against the pre-fix code because `_run` never called
`prove_database` at all -- it only started passing once `prove_database()`
was added as the first line of `_run`, dispatched through the same
thread-sensitive context as the ORM calls that follow it.
"""

from __future__ import annotations

import threading
from unittest.mock import AsyncMock
from unittest.mock import patch

import pytest

from apps.library.models import Work
from apps.profiles.warframe.management.commands.archive_warframe import Command
from apps.profiles.warframe.models import Profile
from apps.profiles.warframe.models import WeaponStat

FAKE_PROFILE_RESPONSE = {
    "Results": [
        {
            "DisplayName": "Tenno",
            "AccountId": "5b2d428bf2f2ebde1070a2b1",
            "Missions": [{"Tag": "SolNode1", "Completes": 3}],
            "Affiliations": [{"Tag": "CrewShipSyndicate", "Standing": 100}],
        }
    ],
    "Stats": {
        "Rank": 29,
        "MissionsCompleted": 200,
        "TimePlayedSec": 3600,
        "Weapons": [{"type": "/Lotus/Weapons/Kuva/KuvaZarr", "kills": 10}],
    },
}


def make_options(**overrides) -> dict:
    options = {
        "account_id": "5b2d428bf2f2ebde1070a2b1",
        "platform": "pc",
        "work_slug": "warframe",
        "trigger": "manual",
        "no_snapshot": True,
    }
    options.update(overrides)
    return options


@pytest.mark.django_db(transaction=True)
class TestArchiveWarframeConnectionRelease:
    def test_prove_database_runs_before_the_first_orm_call_on_its_own_thread(self):
        """Real prove_database, real sync_to_async dispatch -- a mock standing
        in for prove_database would just run inline on the calling thread and
        prove nothing about *which* thread the ORM calls actually land on.
        """
        from django.db import close_old_connections as real_close_old_connections

        call_order: list[str] = []
        threads: dict[str, threading.Thread] = {}

        def recording_close_old_connections(*args, **kwargs):
            call_order.append("prove_database")
            threads["prove_database"] = threading.current_thread()
            return real_close_old_connections(*args, **kwargs)

        # Work.objects.get_or_create is the first ORM call _run makes, right
        # after prove_database -- see archive_warframe.py:74-76.
        original_get_or_create = Work.objects.get_or_create

        def recording_get_or_create(*args, **kwargs):
            call_order.append("first_orm_call")
            threads["first_orm_call"] = threading.current_thread()
            return original_get_or_create(*args, **kwargs)

        with (
            # Patched where synthlib.django.db's prove_database looks it up
            # (its own module global), not where archive_warframe imports it.
            patch(
                "synthlib.django.db.close_old_connections",
                side_effect=recording_close_old_connections,
            ),
            patch.object(
                Work.objects, "get_or_create", side_effect=recording_get_or_create
            ),
            patch(
                "apps.profiles.warframe.management.commands.archive_warframe."
                "WarframeClient.get_profile",
                new=AsyncMock(return_value=FAKE_PROFILE_RESPONSE),
            ),
            patch(
                "apps.profiles.warframe.management.commands.archive_warframe."
                "publish_warframe_event"
            ),
        ):
            import asyncio

            from asgiref.sync import sync_to_async

            asyncio.run(Command()._run(make_options()))
            # asgiref's single_thread_executor is a process-wide singleton
            # that outlives this test -- return its connection explicitly so
            # pytest-django's test-database teardown isn't left racing it.
            asyncio.run(sync_to_async(real_close_old_connections)())

        assert call_order == ["prove_database", "first_orm_call"]
        # The whole point: both calls dispatched through the SAME
        # thread-sensitive executor thread, not the thread that ran
        # asyncio.run() (that's asgiref's single_thread_executor, always a
        # distinct OS thread) -- proving prove_database actually released
        # the connection the ORM call goes on to reuse.
        assert threads["prove_database"] is threads["first_orm_call"]
        assert threads["prove_database"] is not threading.main_thread()

        profile = Profile.objects.get(account_id="5b2d428bf2f2ebde1070a2b1")
        assert profile.missions_completed == 200
        assert WeaponStat.objects.filter(profile=profile).count() == 1
