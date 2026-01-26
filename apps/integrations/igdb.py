from __future__ import annotations

"""
IGDB API Client

Authenticates via Twitch OAuth (client credentials flow).
Requires IGDB_CLIENT_ID and IGDB_CLIENT_SECRET in settings.

Features:
- OAuth token caching in Redis
- Rate limiting (4 req/sec for free tier)
- Response caching for game data

Usage:
    client = IGDBClient()
    results = await client.search("Xenoblade Chronicles 3")
    game = await client.get_by_id(12345)
"""

import asyncio
import hashlib
import time

import httpx
from django.conf import settings
from django.core.cache import cache


class RateLimiter:
    """Simple token bucket rate limiter using Redis."""

    def __init__(self, rate: int = 4, key: str = "igdb_rate_limit"):
        self.rate = rate  # requests per second
        self.key = key

    async def acquire(self) -> None:
        """Wait until a request slot is available."""
        while True:
            now = time.time()
            window_start = int(now)
            cache_key = f"{self.key}:{window_start}"

            # Get current count for this second
            count = cache.get(cache_key, 0)

            if count < self.rate:
                # Increment and allow
                cache.set(cache_key, count + 1, timeout=2)
                return

            # Wait until next second
            sleep_time = 1.0 - (now - window_start)
            if sleep_time > 0:
                await asyncio.sleep(sleep_time)


class IGDBClient:
    BASE_URL = "https://api.igdb.com/v4"
    AUTH_URL = "https://id.twitch.tv/oauth2/token"
    TOKEN_CACHE_KEY = "igdb_access_token"
    GAME_CACHE_TTL = 86400  # 24 hours

    def __init__(self):
        self.client_id = settings.IGDB_CLIENT_ID
        self.client_secret = settings.IGDB_CLIENT_SECRET
        self.rate_limiter = RateLimiter(rate=getattr(settings, "IGDB_RATE_LIMIT", 4))

    async def _get_access_token(self) -> str:
        """Get OAuth access token from Twitch, cached in Redis."""
        # Check cache first
        cached_token = cache.get(self.TOKEN_CACHE_KEY)
        if cached_token:
            return cached_token

        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.AUTH_URL,
                params={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "grant_type": "client_credentials",
                },
            )
            response.raise_for_status()
            data = response.json()

            token = data["access_token"]
            # Cache for slightly less than expiry time (tokens last ~60 days)
            expires_in = data.get("expires_in", 5184000)  # Default 60 days
            cache.set(self.TOKEN_CACHE_KEY, token, timeout=expires_in - 3600)

            return token

    def _cache_key(self, endpoint: str, body: str) -> str:
        """Generate cache key for a request."""
        body_hash = hashlib.md5(body.encode()).hexdigest()[:12]
        return f"igdb:{endpoint}:{body_hash}"

    async def _request(self, endpoint: str, body: str, use_cache: bool = True) -> dict | list:
        """Make authenticated request to IGDB with rate limiting and caching."""
        # Check cache for GET-like requests
        if use_cache:
            cache_key = self._cache_key(endpoint, body)
            cached = cache.get(cache_key)
            if cached is not None:
                return cached

        # Rate limit
        await self.rate_limiter.acquire()

        token = await self._get_access_token()

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.BASE_URL}/{endpoint}",
                headers={
                    "Client-ID": self.client_id,
                    "Authorization": f"Bearer {token}",
                },
                content=body,
            )
            response.raise_for_status()
            result = response.json()

            # Cache the response
            if use_cache:
                cache.set(cache_key, result, timeout=self.GAME_CACHE_TTL)

            return result

    async def search(self, query: str, limit: int = 10) -> list[dict]:
        """Search for games by name."""
        body = f'''
            search "{query}";
            fields name, slug, cover.url, first_release_date, summary,
                   genres.name, platforms.name, franchise.name, collection.name;
            limit {limit};
        '''
        return await self._request("games", body)

    async def get_by_id(self, igdb_id: int) -> dict | None:
        """Fetch full game data by IGDB ID."""
        body = f'''
            where id = {igdb_id};
            fields name, slug, cover.url, first_release_date, summary,
                   genres.name, platforms.name, franchise.name, collection.name,
                   storyline, rating, aggregated_rating;
        '''
        results = await self._request("games", body)
        return results[0] if results else None

    @staticmethod
    def get_cover_url(cover_id: str, size: str = "cover_big") -> str:
        """
        Get cover image URL.

        Sizes: cover_small, cover_big, 720p, 1080p
        """
        return f"https://images.igdb.com/igdb/image/upload/t_{size}/{cover_id}.jpg"
