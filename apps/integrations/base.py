"""Shared helpers for external API integration clients."""

from __future__ import annotations

import asyncio
import time

from django.core.cache import cache


class RateLimiter:
    """Simple token-bucket rate limiter backed by the Redis cache.

    Each client instantiates with its own `rate` (requests/sec) and `key`
    (cache namespace) so limits are tracked independently per source.
    """

    def __init__(self, rate: int = 4, key: str = "rate_limit"):
        self.rate = rate  # requests per second
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
