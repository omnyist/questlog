"""Steam Web API Client.

Used by:
- Warframe session detector (`poll_steam_warframe` management command)
- Steam proxy endpoints for Synthform's co-working overlay (`/api/steam/player`, `/api/steam/recent`)

Requires STEAM_API_KEY in settings. Rate-limited at 4 req/sec.
Responses are cached in Redis (60s for player summary, 5min for recent games).
"""

from __future__ import annotations

import asyncio
import hashlib
import time

import httpx
from django.conf import settings
from django.core.cache import cache


class RateLimiter:
    """Token bucket rate limiter using Redis."""

    def __init__(self, rate: int = 4, key: str = "steam_rate_limit"):
        self.rate = rate
        self.key = key

    async def acquire(self) -> None:
        while True:
            now = time.time()
            window_start = int(now)
            cache_key = f"{self.key}:{window_start}"
            count = cache.get(cache_key, 0)
            if count < self.rate:
                cache.set(cache_key, count + 1, timeout=2)
                return
            sleep_time = 1.0 - (now - window_start)
            if sleep_time > 0:
                await asyncio.sleep(sleep_time)


class SteamAPIError(Exception):
    """Raised when Steam returns a non-success response."""


class SteamClient:
    BASE_URL = "https://api.steampowered.com"
    MEDIA_URL = "https://media.steampowered.com/steamcommunity/public/images/apps"
    WARFRAME_APPID = 230410

    PLAYER_CACHE_TTL = 60
    RECENT_GAMES_CACHE_TTL = 300

    def __init__(self):
        self.api_key = settings.STEAM_API_KEY
        self.rate_limiter = RateLimiter(
            rate=getattr(settings, "STEAM_RATE_LIMIT", 4),
            key="steam_rate_limit",
        )

    def _cache_key(self, name: str, params: dict) -> str:
        serialized = f"{name}:{sorted(params.items())}"
        return f"steam:{hashlib.md5(serialized.encode()).hexdigest()[:12]}"

    async def _request(
        self,
        path: str,
        params: dict,
        *,
        cache_key: str,
        cache_ttl: int,
    ) -> dict:
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        await self.rate_limiter.acquire()

        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            response = await client.get(f"{self.BASE_URL}{path}", params=params)
            response.raise_for_status()
            data = response.json()

        cache.set(cache_key, data, timeout=cache_ttl)
        return data

    async def get_player_summary(self, steam_id: str) -> dict:
        """Fetch a player's current Steam state.

        Returns the raw Steam `player` object (personaname, personastate,
        gameid, gameextrainfo, avatarfull, ...). Empty dict if the player
        is not found.
        """
        params = {"key": self.api_key, "steamids": steam_id}
        data = await self._request(
            "/ISteamUser/GetPlayerSummaries/v0002/",
            params,
            cache_key=self._cache_key("player", params),
            cache_ttl=self.PLAYER_CACHE_TTL,
        )
        players = data.get("response", {}).get("players", [])
        return players[0] if players else {}

    async def get_recent_games(self, steam_id: str, count: int = 5) -> list[dict]:
        """Fetch recently played games.

        Returns a list of raw Steam game objects (appid, name, playtime_2weeks,
        playtime_forever, img_icon_url, ...). Empty list if none.
        """
        params = {"key": self.api_key, "steamid": steam_id, "count": count}
        data = await self._request(
            "/IPlayerService/GetRecentlyPlayedGames/v0001/",
            params,
            cache_key=self._cache_key("recent", params),
            cache_ttl=self.RECENT_GAMES_CACHE_TTL,
        )
        return data.get("response", {}).get("games", []) or []

    @staticmethod
    def game_icon_url(appid: int, img_icon_url: str) -> str:
        """Build the full icon URL from an appid + img_icon_url hash."""
        if not img_icon_url:
            return ""
        return f"{SteamClient.MEDIA_URL}/{appid}/{img_icon_url}.jpg"

    async def is_playing(self, steam_id: str, appid: int) -> bool:
        """Check whether the player is currently in a specific game."""
        summary = await self.get_player_summary(steam_id)
        return summary.get("gameid") == str(appid)
