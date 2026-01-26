# Questlog Roadmap

## Current State

Questlog is a personal gaming data backend with:
- **Library**: Franchise, Genre, Work, Edition models for game metadata
- **Journal**: Playthrough tracking linked to Editions
- **Lists**: Curated collections linked to Works
- **Profiles**: Game-specific integrations (FFXIV, Destiny, PoE, Umamusume)
- **Bulk Import**: API endpoint for importing games with IGDB data

## Completed

### API Documentation ✓

OpenAPI/Swagger docs available at:
```
https://questlog.omnyist.com/api/docs
```

### List Activity / Revision History ✓

Track changes to each list over time, similar to gist revision history. Scoped to individual lists, not a global feed.

```
GET /api/lists/{slug}/activity
```

- ListActivity model with verb (added/removed/reordered), entries, metadata
- Signals auto-log Entry create/delete
- Read-only admin interface

### API Contract Tests ✓

33 tests covering library and lists endpoints with proper 404 handling.

### IGDB Rate Limiting & Caching ✓

- Token bucket rate limiter (4 req/sec for free tier)
- OAuth token cached in Redis
- Game data cached for 24 hours

## Planned Features

### Hierarchical Genre Queries

The Genre model has a `parent` field for future hierarchy support:

```
RPG
├── JRPG
├── Action RPG
├── Tactical RPG
└── MMORPG
Action-Adventure
├── Metroidvania
└── Zelda-like
```

**To implement:**
- Add helper methods to Genre model (`get_ancestors()`, `get_descendants()`)
- Consider django-mptt or django-treebeard for efficient tree queries
- Add API endpoints for hierarchical genre filtering
- Backfill existing Works with genre assignments

### Profile Integrations

- **FFXIV**: XIVAPI integration for character/achievement data
- **Destiny**: Bungie API for historical stats
- **Path of Exile**: PoE API for builds/characters
- **Umamusume**: Manual tracking schema

### Journal Enhancements

- Playthrough status (in-progress, completed, dropped, on-hold)
- Rating system
- Playtime tracking
- Notes and journaling

### Lists Features

- Public/private lists
- Ranked vs unranked lists
- List sharing/export

### Stats & Analytics

- Completion stats by franchise, genre, year
- Playtime aggregation
- Personal gaming trends
