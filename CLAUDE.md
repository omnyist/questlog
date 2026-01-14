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
