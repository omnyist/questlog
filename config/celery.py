from __future__ import annotations

import logging
import os

from celery import Celery
from celery.schedules import crontab
from celery.signals import task_prerun
from celery.signals import task_success
from celery.signals import worker_ready

from config.heartbeat import beat_boot
from config.heartbeat import beat_liveness
from config.heartbeat import beat_work

logger = logging.getLogger(__name__)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("questlog")

app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

# Python 3.13 changed dbm to use SQLite, which causes locking errors with
# Celery beat's default PersistentScheduler + prefork. Since our schedule is
# a static dict (not dynamic), the in-memory scheduler works fine.
app.conf.beat_scheduler = "celery.beat:Scheduler"

app.conf.beat_schedule = {
    "poll-steam-warframe": {
        "task": "apps.profiles.warframe.tasks.poll_steam_warframe",
        "schedule": 300.0,  # Every 5 minutes
    },
    "sync-warframe-catalog": {
        "task": "apps.profiles.warframe.tasks.sync_catalog",
        "schedule": crontab(day_of_week=0, hour=4, minute=0),  # Sundays 04:00 UTC
    },
    "check-warframe-staleness": {
        "task": "apps.profiles.warframe.tasks.check_warframe_staleness",
        "schedule": crontab(hour=12, minute=0),  # Daily 12:00 UTC
    },
}


# Heartbeats via signals, not in the task bodies. "A task started" and "a
# task succeeded" are precisely the liveness/work distinction the convention
# asks for, and celery already publishes both -- so a task added next year is
# monitored without anyone remembering to instrument it.
#
# The cadence is set by the most frequent task: poll-steam-warframe every 300s.
# The daily and weekly entries beat too, but nothing depends on them to keep
# the signal fresh.


@worker_ready.connect
def _beat_boot(**_kwargs) -> None:
    beat_boot()


@task_prerun.connect
def _beat_liveness(**_kwargs) -> None:
    beat_liveness()


@task_success.connect
def _beat_work(**_kwargs) -> None:
    beat_work()


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    logger.debug(f"Request: {self.request!r}")
