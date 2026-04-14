"""poll_steam_warframe — manual wrapper around the scheduled Celery task.

The task runs automatically via Celery beat every 5 minutes
(see `config/celery.py`). This command calls the same logic inline
for one-off debugging.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.profiles.warframe.tasks import poll_steam_warframe


class Command(BaseCommand):
    help = "Run one poll cycle of the Warframe session detector (normally scheduled via Celery beat)"

    def handle(self, *args, **options):
        # Call the task's underlying function directly, not via Celery.
        poll_steam_warframe()
