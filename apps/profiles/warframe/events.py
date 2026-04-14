"""Redis event publishing for Warframe archival.

Publishes to `events:questlog` on synthcore Redis so Synthform (or any
other subscriber) can react to archive/session events.

Message format matches the pattern sketched in CLAUDE.md:
    {
        "type": "warframe:archive_complete",
        "payload": {...},
        "timestamp": "2026-04-14T08:00:00.000+00:00"
    }
"""

from __future__ import annotations

import json
import logging
from datetime import UTC
from datetime import datetime

import redis
from django.conf import settings

logger = logging.getLogger(__name__)

CHANNEL = "events:questlog"


def publish_warframe_event(event_type: str, payload: dict) -> None:
    """Publish a Warframe-scoped event to the shared questlog channel.

    Never raises — logs and swallows errors so publishing never blocks
    the main archival flow.
    """
    try:
        client = redis.from_url(settings.REDIS_URL)
        message = {
            "type": event_type,
            "payload": payload,
            "timestamp": datetime.now(tz=UTC).isoformat(),
        }
        client.publish(CHANNEL, json.dumps(message))
        logger.debug("Published %s to %s", event_type, CHANNEL)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to publish %s: %s", event_type, exc)
