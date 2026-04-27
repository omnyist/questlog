from __future__ import annotations

import json
from typing import Any

import redis.asyncio as aioredis
import redis as sync_redis
from django.conf import settings
from django.utils import timezone

_async_pool: aioredis.ConnectionPool | None = None
_sync_pool: sync_redis.ConnectionPool | None = None


def _get_async_pool() -> aioredis.ConnectionPool:
    global _async_pool
    if _async_pool is None:
        _async_pool = aioredis.ConnectionPool.from_url(settings.REDIS_URL)
    return _async_pool


def _get_sync_pool() -> sync_redis.ConnectionPool:
    global _sync_pool
    if _sync_pool is None:
        _sync_pool = sync_redis.ConnectionPool.from_url(settings.REDIS_URL)
    return _sync_pool


def get_client() -> aioredis.Redis:
    """Get an async Redis client from the shared connection pool."""
    return aioredis.Redis(connection_pool=_get_async_pool())


def get_sync_client() -> sync_redis.Redis:
    """Get a sync Redis client from the shared connection pool."""
    return sync_redis.Redis(connection_pool=_get_sync_pool())


# --- Event Publishing ---


def build_channel(source: str) -> str:
    """Build a Redis channel name for a data source."""
    return f"events:questlog:{source}"


def build_event_envelope(
    event_type: str,
    source: str,
    data: dict,
    timestamp: str | None = None,
    **extra: Any,
) -> str:
    """Build a standardized Redis event envelope as JSON.

    Standard fields: event_type, source, timestamp, data.
    Additional fields can be passed as kwargs.
    """
    envelope = {
        "event_type": event_type,
        "source": source,
        "timestamp": timestamp or timezone.now().isoformat(),
        "data": data,
        **extra,
    }
    return json.dumps(envelope)


async def publish_event(
    source: str,
    event_type: str,
    data: dict,
    **extra: Any,
) -> None:
    """Publish an event to a source's Redis channel (async)."""
    channel = build_channel(source)
    message = build_event_envelope(event_type, source, data, **extra)
    await get_client().publish(channel, message)


def publish_event_sync(
    source: str,
    event_type: str,
    data: dict,
    redis_client: sync_redis.Redis | None = None,
    **extra: Any,
) -> None:
    """Publish an event to a source's Redis channel (sync).

    Never raises — logs and swallows errors so publishing never blocks
    the caller.
    """
    import logging

    logger = logging.getLogger(__name__)
    try:
        client = redis_client or get_sync_client()
        channel = build_channel(source)
        message = build_event_envelope(event_type, source, data, **extra)
        client.publish(channel, message)
        logger.debug("Published %s to %s", event_type, channel)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to publish %s: %s", event_type, exc)
