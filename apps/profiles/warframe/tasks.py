"""Celery tasks for the Warframe archive.

The `poll_steam_warframe` task is scheduled every 5 minutes via Celery
beat (see `config/celery.py`). It detects Warframe session transitions
via the Steam Web API and triggers an archive on session end.
"""

from __future__ import annotations

import asyncio
import logging

import redis
from celery import shared_task
from django.conf import settings
from django.core.management import call_command

from apps.integrations.steam import SteamClient
from apps.profiles.warframe.events import publish_warframe_event

logger = logging.getLogger(__name__)

STATE_KEY = "questlog:steam:warframe_state"
STATE_TTL = 3600  # 1 hour — auto-resets if polling stops


@shared_task(bind=True, ignore_result=True, name="apps.profiles.warframe.tasks.poll_steam_warframe")
def poll_steam_warframe(self):
    """Detect Warframe session transitions and trigger archive on session end.

    Logic:
        1. Ask Steam whether we're currently in Warframe
        2. Compare against previous state in Redis
        3. On `playing -> not_playing`, invoke `archive_warframe --trigger=session_end`
        4. Always refresh the state key TTL
    """
    if not settings.STEAM_API_KEY or not settings.STEAM_ID:
        logger.info("STEAM_API_KEY or STEAM_ID not set, skipping Warframe poll")
        return

    current_state = _check_current_state()
    redis_client = redis.from_url(settings.REDIS_URL)

    previous_raw = redis_client.get(STATE_KEY)
    previous_state = previous_raw.decode() if previous_raw else None

    logger.info("Steam state: previous=%s, current=%s", previous_state, current_state)

    if previous_state == current_state:
        redis_client.set(STATE_KEY, current_state, ex=STATE_TTL)
        return

    redis_client.set(STATE_KEY, current_state, ex=STATE_TTL)

    if current_state == "playing":
        logger.info("Warframe session detected")
        publish_warframe_event(
            "warframe:session_detected",
            {"steam_id": settings.STEAM_ID},
        )
        return

    if current_state == "not_playing" and previous_state == "playing":
        logger.info("Warframe session ended — triggering archive")
        publish_warframe_event(
            "warframe:session_end",
            {"steam_id": settings.STEAM_ID},
        )
        try:
            call_command("archive_warframe", trigger="session_end")
        except Exception as exc:  # noqa: BLE001
            logger.exception("archive_warframe failed")
            publish_warframe_event(
                "warframe:archive_failed",
                {"error": str(exc)},
            )
            raise


def _check_current_state() -> str:
    """Run the async Steam check in a sync context (Celery tasks are sync)."""
    return asyncio.run(_check_current_state_async())


async def _check_current_state_async() -> str:
    client = SteamClient()
    playing = await client.is_playing(settings.STEAM_ID, SteamClient.WARFRAME_APPID)
    return "playing" if playing else "not_playing"
