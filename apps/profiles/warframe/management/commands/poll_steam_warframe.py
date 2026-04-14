"""poll_steam_warframe — session-end detector for the Warframe archive.

Runs periodically (launchd on Saya, every ~5 min). Reads the last known
play state from Redis, compares to current Steam state, and on a
`playing → not_playing` transition invokes `archive_warframe --trigger=session_end`
inline to capture the post-session snapshot.

State keys on synthcore Redis:
    questlog:steam:warframe_state   — "playing" | "not_playing" (1h TTL)
"""

from __future__ import annotations

import asyncio

import redis
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.core.management.base import CommandError

from apps.integrations.steam import SteamClient
from apps.profiles.warframe.events import publish_warframe_event

STATE_KEY = "questlog:steam:warframe_state"
STATE_TTL = 3600  # 1 hour — auto-resets if polling stops


class Command(BaseCommand):
    help = "Poll Steam for Warframe play state and trigger archive on session end"

    def handle(self, *args, **options):
        if not settings.STEAM_API_KEY or not settings.STEAM_ID:
            raise CommandError("STEAM_API_KEY and STEAM_ID must be set")

        current_state = asyncio.run(self._check_current_state())
        redis_client = redis.from_url(settings.REDIS_URL)

        previous_raw = redis_client.get(STATE_KEY)
        previous_state = previous_raw.decode() if previous_raw else None

        self.stdout.write(
            f"Steam state: previous={previous_state!r}, current={current_state!r}"
        )

        if previous_state == current_state:
            # No transition, just refresh TTL
            redis_client.set(STATE_KEY, current_state, ex=STATE_TTL)
            return

        # Transition detected
        redis_client.set(STATE_KEY, current_state, ex=STATE_TTL)

        if current_state == "playing":
            self.stdout.write(self.style.SUCCESS("Session detected — Warframe launched"))
            publish_warframe_event(
                "warframe:session_detected",
                {"steam_id": settings.STEAM_ID},
            )
            return

        if current_state == "not_playing" and previous_state == "playing":
            self.stdout.write(self.style.SUCCESS("Session ended — triggering archive"))
            publish_warframe_event(
                "warframe:session_end",
                {"steam_id": settings.STEAM_ID},
            )
            try:
                call_command("archive_warframe", trigger="session_end")
            except Exception as exc:  # noqa: BLE001
                self.stderr.write(self.style.ERROR(f"Archive failed: {exc}"))
                publish_warframe_event(
                    "warframe:archive_failed",
                    {"error": str(exc)},
                )
                raise
            return

    async def _check_current_state(self) -> str:
        client = SteamClient()
        playing = await client.is_playing(settings.STEAM_ID, SteamClient.WARFRAME_APPID)
        return "playing" if playing else "not_playing"
