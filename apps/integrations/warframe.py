"""Warframe Profile API Client.

Uses the undocumented (but public) content endpoint that returns a full
profile blob for a given account ID. No auth required.

Endpoint shape varies per platform:
    pc      → http://content.warframe.com/dynamic/getProfileViewingData.php
    ps      → http://content-ps4.warframe.com/...
    xbox    → http://content-xb1.warframe.com/...
    switch  → http://content-swi.warframe.com/...

The response uses MongoDB extended JSON for ObjectIds and dates. Helpers
below unwrap those shapes. Weapon display names are derived from path
tails since Warframe embeds names in asset paths.
"""

from __future__ import annotations

import asyncio
import re
import time
from datetime import UTC
from datetime import datetime

import httpx
from django.conf import settings
from django.core.cache import cache


class WarframeAPIError(Exception):
    pass


class RateLimiter:
    """Token bucket rate limiter using Redis."""

    def __init__(self, rate: int = 2, key: str = "warframe_rate_limit"):
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


class WarframeClient:
    PLATFORM_HOSTS = {
        "pc": "http://content.warframe.com",
        "ps": "http://content-ps4.warframe.com",
        "xbox": "http://content-xb1.warframe.com",
        "switch": "http://content-swi.warframe.com",
    }
    PROFILE_PATH = "/dynamic/getProfileViewingData.php"

    def __init__(self):
        self.rate_limiter = RateLimiter(
            rate=getattr(settings, "WARFRAME_RATE_LIMIT", 2),
            key="warframe_rate_limit",
        )

    async def get_profile(self, account_id: str, platform: str = "pc") -> dict:
        """Fetch the full profile blob for an account ID.

        Returns the parsed JSON dict with top-level keys:
            Results      — list with a single profile object
            Stats        — top-level aggregate stats (MissionsCompleted, Weapons, ...)
            TechProjects — dojo research state
            XpComponents — unknown, often empty
        """
        host = self.PLATFORM_HOSTS.get(platform)
        if not host:
            raise WarframeAPIError(f"Unknown platform: {platform}")

        await self.rate_limiter.acquire()

        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            response = await client.get(
                f"{host}{self.PROFILE_PATH}",
                params={"playerId": account_id},
            )
            response.raise_for_status()
            return response.json()


# ---- BSON extended-JSON helpers ----


def parse_oid(value: dict | str | None) -> str:
    """Unwrap a MongoDB ObjectId from Warframe's BSON-flavored JSON.

    Accepts `{"$oid": "abc"}` or a plain string (passes through).
    """
    if isinstance(value, dict):
        return value.get("$oid", "")
    return value or ""


def parse_bson_date(value: dict | None) -> datetime | None:
    """Unwrap `{"$date": {"$numberLong": "1529692811761"}}` into a datetime."""
    if not value or not isinstance(value, dict):
        return None
    date_field = value.get("$date")
    if isinstance(date_field, dict):
        ms = int(date_field.get("$numberLong", 0))
    elif isinstance(date_field, (int, str)):
        ms = int(date_field)
    else:
        return None
    return datetime.fromtimestamp(ms / 1000, tz=UTC)


_UPPERCASE_BOUNDARY = re.compile(r"(?<!^)(?=[A-Z])")


def weapon_name_from_path(path: str) -> str:
    """Derive a display name from a Warframe asset path.

    `/Lotus/Weapons/MK1Series/MK1Kunai` → `"MK1 Kunai"`
    """
    if not path:
        return ""
    tail = path.rsplit("/", 1)[-1]
    # Strip common prefixes that appear in some asset names.
    return _UPPERCASE_BOUNDARY.sub(" ", tail).strip()
