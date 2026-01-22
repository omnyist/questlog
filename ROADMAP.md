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

### List Activity / Revision History

Track changes to each list over time, similar to gist revision history. Scoped to individual lists, not a global feed.

```
GET /api/lists/completed-rpgs/activity

Jan 21, 2026
  + Added ".hack//Infection"

Jan 21, 2026
  + Created list with 91 entries
```

**Model sketch:**
```python
class ListActivity(models.Model):
    list = models.ForeignKey(List, on_delete=models.CASCADE, related_name="activity")
    timestamp = models.DateTimeField(auto_now_add=True)
    verb = models.CharField(max_length=20)  # created, added, removed, reordered
    entries = models.JSONField(default=list)  # Work slugs affected
    metadata = models.JSONField(default=dict)  # count, positions, notes
```

**To implement:**
- Add ListActivity model to lists app
- Log on Entry create/delete via signals
- Log bulk operations explicitly
- API endpoint: `GET /api/lists/{slug}/activity`

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
