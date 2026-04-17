from __future__ import annotations

import logging
import os

from celery import Celery

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
}


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    logger.debug(f"Request: {self.request!r}")
