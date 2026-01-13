# Questlog

Personal gaming data backend - tracks games, playthroughs, and curated lists.

## Overview

Questlog is a Django REST API that provides structured, API-accessible data about games played, completion records, curated lists, and live game integrations. It serves as the data layer for [Omnyist](https://omnyist.com).

## Quick Start

```bash
# Start services
docker compose up -d

# Run migrations
docker compose exec server uv run python manage.py migrate

# Create superuser
docker compose exec server uv run python manage.py createsuperuser

# API available at http://localhost:7176/api/
```

## Architecture

- **library** - Game metadata (IGDB-backed)
- **journal** - Personal play records (Playthrough)
- **lists** - Curated collections (List, Entry)
- **profiles** - Game-specific deep tracking
  - ffxiv - Final Fantasy XIV (XIVAPI)
  - destiny - Destiny 2 (Bungie API)
  - poe - Path of Exile
  - umamusume - Manual tracking

## API Endpoints

```
GET  /api/games/                    # List games
GET  /api/games/{slug}/             # Single game
POST /api/games/                    # Add game (IGDB lookup)

GET  /api/games/{slug}/playthroughs/
POST /api/games/{slug}/playthroughs/

GET  /api/lists/
GET  /api/lists/{slug}/
POST /api/lists/{slug}/entries/

GET  /api/profiles/ffxiv/
GET  /api/profiles/destiny/
GET  /api/profiles/poe/

GET  /api/stats/
```

## Environment Variables

```
DATABASE_URL=postgresql://questlog:questlog@db:5432/questlog
REDIS_URL=redis://redis:6379/0
SECRET_KEY=your-secret-key
DEBUG=True
IGDB_CLIENT_ID=your-twitch-client-id
IGDB_CLIENT_SECRET=your-twitch-client-secret
```

## Related Projects

- **Omnyist** - Astro frontend that consumes this API
- **Synthform** - Streaming overlay system (separate concern)
