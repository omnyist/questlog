"""Celery tasks for the Warframe archive.

The `poll_steam_warframe` task is scheduled every 5 minutes via Celery
beat (see `config/celery.py`). It detects Warframe session transitions
via the Steam Web API and triggers an archive on session end.

`check_warframe_staleness` runs daily as a safety net — it alerts (Sentry +
event) if the archive has gone stale despite recent play, catching silent
failures like an upstream endpoint moving.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime

import redis
import sentry_sdk
from celery import shared_task
from django.conf import settings
from django.core.management import call_command
from django.utils import timezone

from apps.integrations.steam import SteamClient
from apps.profiles.warframe.events import publish_warframe_event

logger = logging.getLogger(__name__)

STATE_KEY = "questlog:steam:warframe_state"
STATE_TTL = 3600  # 1 hour — auto-resets if polling stops
STALENESS_THRESHOLD_HOURS = 48


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
            sentry_sdk.capture_exception(exc)
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


def staleness_alert_needed(
    last_synced: datetime | None,
    now: datetime,
    played_recently: bool,
    threshold_hours: int = STALENESS_THRESHOLD_HOURS,
) -> bool:
    """Decide whether a staleness alert should fire.

    Only alerts when the archive is older than the threshold AND Steam shows
    recent play — so genuine breaks (not playing) never false-positive.
    """
    if last_synced is None:
        return False
    if not played_recently:
        return False
    age_hours = (now - last_synced).total_seconds() / 3600
    return age_hours > threshold_hours


def _warframe_played_recently() -> bool:
    return asyncio.run(_warframe_played_recently_async())


async def _warframe_played_recently_async() -> bool:
    client = SteamClient()
    games = await client.get_recent_games(settings.STEAM_ID)
    return any(
        str(g.get("appid")) == str(SteamClient.WARFRAME_APPID)
        and (g.get("playtime_2weeks", 0) or 0) > 0
        for g in games
    )


@shared_task(bind=True, ignore_result=True, name="apps.profiles.warframe.tasks.check_warframe_staleness")
def check_warframe_staleness(self):
    """Daily safety net: alert if the archive is stale despite recent play.

    Catches failure modes where no archive is even attempted (poller broken,
    Steam detection dead, upstream endpoint moved) — anything that would
    otherwise let data go stale silently.
    """
    if not settings.STEAM_API_KEY or not settings.STEAM_ID:
        return

    from apps.profiles.warframe.models import Profile

    profile = Profile.objects.first()
    if not profile or not profile.last_synced:
        return

    now = timezone.now()
    played_recently = _warframe_played_recently()
    if not staleness_alert_needed(profile.last_synced, now, played_recently):
        return

    age_hours = (now - profile.last_synced).total_seconds() / 3600
    msg = (
        f"Warframe archive stale: last synced {age_hours:.0f}h ago "
        f"despite recent play (threshold {STALENESS_THRESHOLD_HOURS}h)"
    )
    logger.error(msg)
    sentry_sdk.capture_message(msg, level="error")
    publish_warframe_event(
        "warframe:archive_stale",
        {"last_synced": profile.last_synced.isoformat(), "age_hours": round(age_hours, 1)},
    )


@shared_task(bind=True, ignore_result=True, name="apps.profiles.warframe.tasks.sync_catalog")
def sync_catalog(self):
    """Refresh the WFCD item catalog weekly so newly-released frames classify.

    Idempotent — update_or_create on uniqueName. Logs and swallows errors so a
    transient GitHub/network failure never crashes the beat worker.
    """
    try:
        call_command("sync_warframe_catalog")
    except Exception:  # noqa: BLE001
        logger.exception("sync_warframe_catalog failed")
