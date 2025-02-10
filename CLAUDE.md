# CLAUDE.md

This file contains important information for Claude when working with this codebase.

## Project Overview

Questlog is a personal gaming data backend that provides structured, API-accessible data about games played, completion records, curated lists, and live game integrations. It serves as the data layer for Omnyist (the hobbies site in the multiverse of personal sites).

**Architecture:**
- **Questlog (this project)**: Django REST API backend - holds firm statistical data
- **Omnyist (Astro frontend)**: Tools and editorial content that consume Questlog's API
- **Synthform (sibling project)**: Streaming overlay system - separate concern, same deployment target

The separation is intentional: Questlog could eventually be extracted as a standalone, self-hostable gaming library tracker.

## Tech Stack

- Python 3.13+
- Django 5.2+ with Django Ninja for REST API
- PostgreSQL 16
- Redis (for caching, future Celery tasks)
- Docker Compose for local development
- uv for package management
- Deployed to Mac mini (same as Synthform)

## Django Apps Structure

```
questlog/
├── config/              # Django settings, urls, asgi
├── apps/
│   ├── library/         # Game metadata (IGDB-backed)
│   │   └── models: Game
│   ├── journal/         # Personal play records
│   │   └── models: PlayedGame
│   ├── lists/           # Curated collections
│   │   └── models: List, ListEntry
│   ├── profiles/        # Live game integrations (optional per-game)
│   │   ├── ffxiv/       # XIVAPI integration
│   │   ├── destiny/     # Bungie API integration
│   │   ├── poe/         # Path of Exile API
│   │   └── umamusume/   # Manual schema (no API)
│   └── integrations/    # External API clients
│       ├── igdb.py
│       ├── xivapi.py
│       ├── bungie.py
│       └── poe.py
└── api/                 # Django Ninja API routes
```

## Core Data Model

**Game** (library app) - IGDB-backed metadata, cached locally:
- `igdb_id`: Links to IGDB
- `slug`: URL-friendly identifier
- `name`, `cover_url`, `release_date`, `summary`
- `igdb_data`: Full IGDB response (JSONField)
- `last_synced`: For cache invalidation

**PlayedGame** (journal app) - Personal play records:
- `game`: FK to Game
- `platform`: What platform played on
- `started_at`, `completed_at`: Date tracking
- `playtime_hours`: Optional time tracking
- `rating`: Personal rating
- `notes`: Freeform notes ("NG+ run", "JP version")

**List** (lists app) - Curated collections:
- `slug`, `name`, `description`
- `is_ranked`: Whether position matters

**ListEntry** (lists app) - Game membership in lists:
- `list`: FK to List
- `game`: FK to Game
- `position`: For ranked lists
- `notes`: List-specific notes

**Profiles** (profiles/* apps) - Optional deep tracking per game:
- Link back to Game via OneToOneField
- Game-specific models (FFXIV characters, Destiny stats, etc.)

## API Endpoints

```
# Library
GET  /api/games/                    # List games (paginated, filterable)
GET  /api/games/{slug}/             # Single game with full data
POST /api/games/                    # Add game (triggers IGDB lookup)
PUT  /api/games/{slug}/sync         # Re-sync from IGDB

# Journal
GET  /api/games/{slug}/playthroughs/
POST /api/games/{slug}/playthroughs/
GET  /api/playthroughs/             # All playthroughs

# Lists
GET  /api/lists/
GET  /api/lists/{slug}/
POST /api/lists/
POST /api/lists/{slug}/entries/

# Profiles
GET  /api/profiles/ffxiv/
GET  /api/profiles/destiny/
GET  /api/profiles/poe/
POST /api/profiles/{game}/sync

# Stats
GET  /api/stats/                    # Aggregate stats
```

## External Integrations

### IGDB (Primary game metadata)
- Authenticate via Twitch OAuth (client credentials)
- Search games, fetch metadata, cache locally
- Store full response in `igdb_data` JSONField
- Re-sync on demand or via scheduled task

### XIVAPI (FFXIV)
- Character data, jobs, achievements, mounts, minions
- Lodestone ID required

### Bungie API (Destiny 2)
- Historical stats, raid clears, triumphs
- OAuth required for private data

### Path of Exile API
- Characters, builds, league progress
- OAuth registration required

### Umamusume
- No API available
- Manual schema for tracking horses, races, rankings

## Key Games to Track

Priority games with deep integration needs:
1. **Final Fantasy XIV** - XIVAPI for character/achievement data
2. **Destiny 2** - Bungie API for historical stats (even though stopped playing)
3. **Path of Exile** - PoE API for builds/characters
4. **Umamusume: Pretty Derby** - Manual tracking, custom schema

## Data Migration

The RPG completion list exists as a GitHub Gist (15+ years of data):
https://gist.github.com/bryanveloso/4244350

Contains:
- 99 completed RPGs organized by series
- Platform/version notes
- Rankings (Top 25 RPGs, FF Favorites)

This data should be migrated to Questlog and enriched with IGDB metadata.

## Writing Code

- Match Synthform patterns where applicable (same deployment target)
- Use Django Ninja for REST API (not DRF)
- Use uv for package management
- Pytest for testing
- Ruff for linting (same config as Synthform)
- NEVER implement mock modes - use real data and APIs
- Tests must cover functionality being implemented

## Docker

Development: `docker compose up`
- PostgreSQL on 5432
- Redis on 6379
- Django server on 7176 (avoiding Synthform's 7175)

## Relationship to Other Projects

- **Synthform** (`~/Code/bryanveloso/synthform`): Streaming backend, separate concern
- **Multiverse** (`~/Code/bryanveloso/multiverse`): Astro frontends including Omnyist
- **Omnyist** (`multiverse/apps/omnyist.com`): Consumes Questlog API for game data

Questlog provides data. Omnyist provides editorial and tools that reference that data.

## WebSocket Support for Synthform Integration

Questlog needs WebSocket support so Synthform's overlay system can subscribe to real-time events. This enables streaming overlays to react to gaming data changes (playthrough completions, list updates, hunt encounters, etc.).

### Architecture Overview

Synthform uses Redis pub/sub for event distribution. The pattern:
1. Questlog publishes events to Redis channels when data changes
2. Synthform's `OverlayConsumer` subscribes to those channels
3. Events flow to React overlays in real-time

### Required Dependencies

Add to `pyproject.toml`:
```toml
"channels[daphne]>=4.3.2",
"channels-redis>=4.2.0",
```

### Settings Changes

Add to `config/settings.py`:
```python
INSTALLED_APPS = [
    "daphne",  # Add before django.contrib.staticfiles
    # ... existing apps
]

# Channels
ASGI_APPLICATION = "config.asgi.application"
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [REDIS_URL],
        },
    },
}
```

### ASGI Configuration

Update `config/asgi.py` to match Synthform's pattern:
```python
from __future__ import annotations

import os

import django
from channels.routing import ProtocolTypeRouter
from channels.routing import URLRouter
from django.core.asgi import get_asgi_application
from django.urls import path

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

# Import consumers after Django setup
from apps.realtime.consumers import QuestlogConsumer  # noqa: E402

django_asgi_app = get_asgi_application()

websocket_urlpatterns = [
    path("ws/questlog/", QuestlogConsumer.as_asgi()),
]

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": URLRouter(websocket_urlpatterns),
    }
)
```

### Create Realtime App

Create `apps/realtime/` with:

**`apps/realtime/consumers.py`**:
```python
from __future__ import annotations

import json
import logging

from channels.generic.websocket import AsyncWebsocketConsumer

logger = logging.getLogger(__name__)


class QuestlogConsumer(AsyncWebsocketConsumer):
    """WebSocket consumer for Questlog events.

    Synthform connects here to receive real-time updates about:
    - Playthrough completions
    - List changes
    - ACNH hunt encounters
    - Profile syncs
    """

    async def connect(self):
        await self.channel_layer.group_add("questlog_events", self.channel_name)
        await self.accept()
        logger.info("Questlog WebSocket connected")

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard("questlog_events", self.channel_name)
        logger.info(f"Questlog WebSocket disconnected: {close_code}")

    async def questlog_event(self, event):
        """Handle events broadcast to the questlog_events group."""
        await self.send(text_data=json.dumps(event["data"]))
```

**`apps/realtime/events.py`** - Event publishing helper:
```python
from __future__ import annotations

import json
import logging
from datetime import datetime

import redis.asyncio as redis
from django.conf import settings

logger = logging.getLogger(__name__)

# Redis client for publishing (sync context)
_redis_client = None


def get_redis_client():
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.from_url(settings.REDIS_URL)
    return _redis_client


async def publish_event(event_type: str, payload: dict):
    """Publish an event to Redis for Synthform to consume.

    Event types:
    - questlog:playthrough_complete
    - questlog:list_updated
    - questlog:hunt_encounter
    - questlog:profile_synced
    """
    client = get_redis_client()
    message = {
        "type": event_type,
        "payload": payload,
        "timestamp": datetime.now().isoformat(),
    }
    await client.publish("events:questlog", json.dumps(message))
    logger.debug(f"Published {event_type}: {payload}")


def publish_event_sync(event_type: str, payload: dict):
    """Synchronous version for use in Django signals/model saves."""
    import redis as sync_redis

    client = sync_redis.from_url(settings.REDIS_URL)
    message = {
        "type": event_type,
        "payload": payload,
        "timestamp": datetime.now().isoformat(),
    }
    client.publish("events:questlog", json.dumps(message))
    logger.debug(f"Published {event_type}: {payload}")
```

### Event Triggers

Add signals or override model `save()` methods to publish events:

**Playthrough completion** (`apps/journal/signals.py`):
```python
from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.journal.models import Playthrough
from apps.realtime.events import publish_event_sync


@receiver(post_save, sender=Playthrough)
def on_playthrough_save(sender, instance, created, **kwargs):
    if instance.completed_at:
        publish_event_sync("questlog:playthrough_complete", {
            "work": instance.edition.work.name,
            "edition": instance.edition.name,
            "platform": instance.platform,
            "playtime_hours": instance.playtime_hours,
            "rating": instance.rating,
        })
```

**ACNH hunt encounter** (`apps/profiles/acnh/signals.py`):
```python
@receiver(post_save, sender=HuntEncounter)
def on_hunt_encounter(sender, instance, created, **kwargs):
    if created:
        publish_event_sync("questlog:hunt_encounter", {
            "villager": instance.villager.name,
            "personality": instance.villager.personality,
            "species": instance.villager.species,
            "icon_url": instance.villager.icon_url,
            "encounter_number": instance.hunt.encounters.count(),
            "is_target": instance.villager == instance.hunt.target_villager,
        })
```

### Synthform Integration

Synthform needs to subscribe to `events:questlog` Redis channel. In `synthform/overlays/consumers.py`, add:

```python
# In OverlayConsumer.connect():
await self.subscribe_to_redis("events:questlog")

# Add handler for questlog events:
async def handle_questlog_event(self, message: dict):
    event_type = message.get("type", "")
    payload = message.get("payload", {})

    if event_type == "questlog:playthrough_complete":
        # Could trigger a celebration overlay
        await self.send_layer_message("alerts", "push", {
            "type": "game_complete",
            "data": payload,
        })
    elif event_type == "questlog:hunt_encounter":
        # Update ACNH hunt overlay
        await self.send_layer_message("games", "acnh_encounter", payload)
```

### Redis Channel

Questlog publishes to: `events:questlog`

Message format:
```json
{
  "type": "questlog:playthrough_complete",
  "payload": {
    "work": "Final Fantasy VII Rebirth",
    "edition": "PS5",
    "platform": "PlayStation 5",
    "playtime_hours": 87,
    "rating": 5
  },
  "timestamp": "2025-02-11T12:34:56.789Z"
}
```

### Testing the Integration

1. Start both services (questlog on 7176, synthform on 7175)
2. Connect to questlog WebSocket: `ws://localhost:7176/ws/questlog/`
3. Trigger an event (complete a playthrough via admin or API)
4. Verify event appears in Synthform's overlay
