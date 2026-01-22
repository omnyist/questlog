# Questlog Roadmap

## Current State

Questlog is a personal gaming data backend with:
- **Library**: Franchise, Genre, Work, Edition models for game metadata
- **Journal**: Playthrough tracking linked to Editions
- **Lists**: Curated collections linked to Works
- **Profiles**: Game-specific integrations (FFXIV, Destiny, PoE, Umamusume)
- **Bulk Import**: API endpoint for importing games with IGDB data

## Priority: API Documentation

OpenAPI/Swagger docs are needed for Multiverse (Omnyist) and Synthform integration.

Django Ninja has built-in OpenAPI support. Enable at:
```
https://questlog.omnyist.com/api/docs
```

**To implement:**
- Ensure all endpoints have proper response schemas
- Add descriptions to endpoints and schemas
- Document query parameters and filters
- Add authentication docs when auth is added

## Planned Features

### Activity Stream / Changelog

Track changes to the library over time, similar to gist revision history:

```
Jan 21, 2026
  + Added "Completed RPGs" list (92 entries)

Jan 20, 2026
  + Imported 100 works from gist
  + Added 26 franchises

Dec 15, 2025
  ~ Marked "Elden Ring" as completed
  + Added "Final Fantasy VII Rebirth" to library
```

**Model sketch:**
```python
class Activity(models.Model):
    timestamp = models.DateTimeField(auto_now_add=True)
    verb = models.CharField(max_length=20)  # added, updated, completed, started
    subject = models.CharField(max_length=255)  # "Final Fantasy VII Rebirth"
    subject_type = models.CharField(max_length=50)  # work, list, playthrough
    subject_slug = models.CharField(max_length=255, blank=True)
    context = models.CharField(max_length=255, blank=True)  # "to Completed RPGs"
    metadata = models.JSONField(default=dict)  # count, diff, etc.
```

**To implement:**
- Create Activity model in new `activity` app
- Add Django signals to auto-log model changes
- Add explicit logging for bulk operations
- API endpoint for querying timeline (`GET /api/activity`)

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

## Technical Debt

- Add comprehensive test coverage
- API documentation with OpenAPI/Swagger
- Rate limiting for external API calls
- Caching layer for IGDB data
