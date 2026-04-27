"""Redis event publishing for Warframe archival.

Publishes to `events:questlog:warframe` on synthcore Redis so Synthform
(or any other subscriber) can react to archive/session events.

Envelope format (standardized across the synth suite):
    {
        "event_type": "warframe:archive_complete",
        "source": "warframe",
        "data": {...},
        "timestamp": "2026-04-14T08:00:00.000+00:00"
    }
"""

from __future__ import annotations

from config.redis import publish_event_sync


def publish_warframe_event(event_type: str, data: dict) -> None:
    """Publish a Warframe-scoped event to events:questlog:warframe.

    Never raises — publish_event_sync logs and swallows errors so
    publishing never blocks the main archival flow.
    """
    publish_event_sync("warframe", event_type, data)
