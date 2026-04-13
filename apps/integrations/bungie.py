"""Bungie API Client.

Authenticates via a simple X-API-Key header. Register an app at:
    https://www.bungie.net/en/Application

Requires BUNGIE_API_KEY in settings. No OAuth needed for public profile data.
Rate-limited at 8 req/sec (conservative vs ~25/sec observed).
"""

from __future__ import annotations

import asyncio
import hashlib
import time
from pathlib import Path

import httpx
from django.conf import settings
from django.core.cache import cache


class RateLimiter:
    """Simple token bucket rate limiter using Redis."""

    def __init__(self, rate: int = 8, key: str = "bungie_rate_limit"):
        self.rate = rate
        self.key = key

    async def acquire(self) -> None:
        """Wait until a request slot is available."""
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


class BungieAPIError(Exception):
    """Raised when Bungie returns a non-success ErrorCode."""

    def __init__(self, error_code: int, error_status: str, message: str):
        self.error_code = error_code
        self.error_status = error_status
        super().__init__(f"{error_status} ({error_code}): {message}")


class BungieClient:
    BASE_URL = "https://www.bungie.net/Platform"
    MANIFEST_ROOT = "https://www.bungie.net"
    CACHE_TTL = 3600  # 1 hour default
    MANIFEST_CACHE_TTL = 86400  # manifest metadata: 24 hours

    def __init__(self):
        self.api_key = settings.BUNGIE_API_KEY
        self.rate_limiter = RateLimiter(
            rate=getattr(settings, "BUNGIE_RATE_LIMIT", 8),
            key="bungie_rate_limit",
        )

    def _cache_key(self, path: str, params: dict | None) -> str:
        body = f"{path}?{sorted((params or {}).items())}"
        body_hash = hashlib.md5(body.encode()).hexdigest()[:12]
        return f"bungie:{body_hash}"

    async def _request(
        self,
        path: str,
        params: dict | None = None,
        use_cache: bool = False,
        cache_ttl: int | None = None,
    ) -> dict:
        """Make an authenticated GET request to the Bungie Platform API.

        Returns the unwrapped `Response` payload from Bungie's envelope.
        """
        if use_cache:
            key = self._cache_key(path, params)
            cached = cache.get(key)
            if cached is not None:
                return cached

        await self.rate_limiter.acquire()

        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            response = await client.get(
                f"{self.BASE_URL}{path}",
                headers={"X-API-Key": self.api_key},
                params=params,
            )
            response.raise_for_status()
            data = response.json()

        if data.get("ErrorCode", 1) != 1:
            raise BungieAPIError(
                error_code=data.get("ErrorCode", 0),
                error_status=data.get("ErrorStatus", "Unknown"),
                message=data.get("Message", ""),
            )

        result = data.get("Response", {})

        if use_cache:
            cache.set(
                self._cache_key(path, params),
                result,
                timeout=cache_ttl or self.CACHE_TTL,
            )

        return result

    async def search_player(
        self,
        display_name: str,
        display_name_code: int,
        membership_type: int = -1,
    ) -> list[dict]:
        """Find a player by Bungie Name (e.g., "Avalonstar" + 1234).

        membership_type=-1 searches all platforms.
        """
        path = f"/Destiny2/SearchDestinyPlayerByBungieName/{membership_type}/"
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            await self.rate_limiter.acquire()
            response = await client.post(
                f"{self.BASE_URL}{path}",
                headers={
                    "X-API-Key": self.api_key,
                    "Content-Type": "application/json",
                },
                json={
                    "displayName": display_name,
                    "displayNameCode": display_name_code,
                },
            )
            response.raise_for_status()
            data = response.json()

        if data.get("ErrorCode", 1) != 1:
            raise BungieAPIError(
                error_code=data.get("ErrorCode", 0),
                error_status=data.get("ErrorStatus", "Unknown"),
                message=data.get("Message", ""),
            )
        return data.get("Response", [])

    async def get_profile(
        self,
        membership_type: int,
        membership_id: str,
        components: list[int],
    ) -> dict:
        """Fetch profile data with specified components.

        Common components:
          100 = Profiles, 200 = Characters, 800 = Collectibles,
          900 = Records, 1100 = Metrics
        """
        path = f"/Destiny2/{membership_type}/Profile/{membership_id}/"
        params = {"components": ",".join(str(c) for c in components)}
        return await self._request(path, params=params)

    async def get_character(
        self,
        membership_type: int,
        membership_id: str,
        character_id: str,
        components: list[int],
    ) -> dict:
        """Fetch character-scoped data with specified components."""
        path = f"/Destiny2/{membership_type}/Profile/{membership_id}/Character/{character_id}/"
        params = {"components": ",".join(str(c) for c in components)}
        return await self._request(path, params=params)

    async def get_historical_stats_account(
        self,
        membership_type: int,
        membership_id: str,
        groups: list[str] | None = None,
    ) -> dict:
        """Fetch account-wide aggregate stats merged across all characters."""
        path = f"/Destiny2/{membership_type}/Account/{membership_id}/Stats/"
        params: dict = {}
        if groups:
            params["groups"] = ",".join(groups)
        return await self._request(path, params=params or None)

    async def get_historical_stats_character(
        self,
        membership_type: int,
        membership_id: str,
        character_id: str,
        groups: list[str] | None = None,
        modes: list[int] | None = None,
    ) -> dict:
        """Fetch per-character aggregate stats."""
        path = (
            f"/Destiny2/{membership_type}/Account/{membership_id}"
            f"/Character/{character_id}/Stats/"
        )
        params: dict = {}
        if groups:
            params["groups"] = ",".join(groups)
        if modes:
            params["modes"] = ",".join(str(m) for m in modes)
        return await self._request(path, params=params or None)

    async def get_activity_history(
        self,
        membership_type: int,
        membership_id: str,
        character_id: str,
        mode: int = 0,
        count: int = 250,
        page: int = 0,
    ) -> dict:
        """Fetch a page of activity history. 250 activities max per page."""
        path = (
            f"/Destiny2/{membership_type}/Account/{membership_id}"
            f"/Character/{character_id}/Stats/Activities/"
        )
        params = {"mode": mode, "count": count, "page": page}
        return await self._request(path, params=params)

    async def get_pgcr(self, activity_id: str | int) -> dict:
        """Fetch a Post-Game Carnage Report for a single activity instance."""
        path = f"/Destiny2/Stats/PostGameCarnageReport/{activity_id}/"
        return await self._request(path, use_cache=True, cache_ttl=self.CACHE_TTL * 24 * 30)

    async def get_manifest(self) -> dict:
        """Fetch manifest metadata including version and content paths."""
        return await self._request(
            "/Destiny2/Manifest/",
            use_cache=True,
            cache_ttl=self.MANIFEST_CACHE_TTL,
        )

    async def download_manifest_database(
        self,
        dest_dir: str | Path,
        locale: str = "en",
    ) -> tuple[Path, str]:
        """Download the SQLite content database for the given locale.

        Returns (path_to_sqlite_file, version).
        """
        manifest = await self.get_manifest()
        version = manifest.get("version", "unknown")
        content_paths = manifest.get("mobileWorldContentPaths", {})
        relative_path = content_paths.get(locale)
        if not relative_path:
            raise BungieAPIError(
                error_code=0,
                error_status="NoContentPath",
                message=f"No manifest content path for locale '{locale}'",
            )

        dest_dir = Path(dest_dir)
        dest_dir.mkdir(parents=True, exist_ok=True)
        filename = Path(relative_path).name
        dest_path = dest_dir / filename

        if dest_path.exists():
            return dest_path, version

        url = f"{self.MANIFEST_ROOT}{relative_path}"
        async with httpx.AsyncClient(timeout=300.0) as client:
            await self.rate_limiter.acquire()
            async with client.stream("GET", url) as response:
                response.raise_for_status()
                with dest_path.open("wb") as f:
                    async for chunk in response.aiter_bytes(chunk_size=65536):
                        f.write(chunk)

        return dest_path, version
