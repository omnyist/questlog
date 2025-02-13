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

### ACNH Villager Hunting ✓

- Villager model synced from ACNH API (391 villagers)
- VillagerHunt and Encounter models for tracking mystery island visits
- Profile linked to Work for game-specific data
- Admin with autocomplete for villager selection
- Images served via GitHub raw URLs (external dependency)

## In Progress

### IronMON Profile (Synthform Integration)

**Priority: HIGH** - First integration between Questlog and Synthform. Data export already completed.

IronMON is a Pokemon ROM hack challenge mode. Synthform currently stores run data, but Questlog should be the source of truth for historical tracking. Synthform will become a real-time relay that forwards events to Questlog.

**Data already exported:** `data/ironmon_export.json` (24,826 lines)
- 2 Challenges (Kaizo, Super Kaizo)
- 23 Checkpoints (Rival battles, gym leaders, E4, Champion)
- 2,236 Seeds (individual run attempts)
- 992 Results (checkpoint pass/fail records)

#### Models to Create

Create `apps/profiles/ironmon/`:

```python
# models.py

class Challenge(models.Model):
    """The challenge ruleset (Kaizo, Super Kaizo, Ultimate, etc.)."""
    slug = models.SlugField(unique=True)
    name = models.TextField()  # "Kaizo", "Super Kaizo"
    edition = models.ForeignKey(
        "library.Edition", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="ironmon_challenges"
    )


class Checkpoint(models.Model):
    """A checkpoint within a challenge (gym leaders, rival battles, E4, etc.)."""
    challenge = models.ForeignKey(Challenge, on_delete=models.CASCADE, related_name="checkpoints")
    name = models.TextField()  # "Brock", "Rival 3", "Champion"
    trainer = models.TextField()
    order = models.IntegerField()

    class Meta:
        ordering = ["order"]
        unique_together = ["challenge", "order"]


class Run(models.Model):
    """A single IronMON attempt (maps to Synthform's Seed)."""
    seed_number = models.IntegerField(primary_key=True)  # Comes from IronMON plugin
    challenge = models.ForeignKey(Challenge, on_delete=models.CASCADE, related_name="runs")
    started_at = models.DateTimeField(auto_now_add=True)

    # Denormalized for quick queries
    highest_checkpoint = models.ForeignKey(
        Checkpoint, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="+"
    )
    is_victory = models.BooleanField(default=False)

    class Meta:
        ordering = ["-seed_number"]


class CheckpointResult(models.Model):
    """Result of a checkpoint attempt (maps to Synthform's Result)."""
    run = models.ForeignKey(Run, on_delete=models.CASCADE, related_name="results")
    checkpoint = models.ForeignKey(Checkpoint, on_delete=models.CASCADE, related_name="results")
    cleared = models.BooleanField()
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ["run", "checkpoint"]
        ordering = ["checkpoint__order"]
```

#### Import Script

Create `data/import_ironmon.py`:

```python
"""
Import IronMON data from Synthform export.

Usage: python data/import_ironmon.py

Reads: data/ironmon_export.json (Django dumpdata format)
Maps:
  - ironmon.challenge → Challenge
  - ironmon.checkpoint → Checkpoint
  - ironmon.seed → Run
  - ironmon.result → CheckpointResult
"""
import json
import os
import sys

import django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
sys.path.insert(0, str(Path(__file__).parent.parent))
django.setup()

from apps.profiles.ironmon.models import Challenge, Checkpoint, Run, CheckpointResult


def import_ironmon():
    with open("data/ironmon_export.json") as f:
        data = json.load(f)

    # Group by model type
    challenges = [d for d in data if d["model"] == "ironmon.challenge"]
    checkpoints = [d for d in data if d["model"] == "ironmon.checkpoint"]
    seeds = [d for d in data if d["model"] == "ironmon.seed"]
    results = [d for d in data if d["model"] == "ironmon.result"]

    # Map old PKs to new objects
    challenge_map = {}
    checkpoint_map = {}

    # Import challenges → Challenge
    for c in challenges:
        challenge, _ = Challenge.objects.get_or_create(
            slug=c["fields"]["name"].lower().replace(" ", "-"),
            defaults={"name": c["fields"]["name"]}
        )
        challenge_map[c["pk"]] = challenge

    # Import checkpoints
    for cp in checkpoints:
        checkpoint, _ = Checkpoint.objects.get_or_create(
            challenge=challenge_map[cp["fields"]["challenge"]],
            order=cp["fields"]["order"],
            defaults={
                "name": cp["fields"]["name"],
                "trainer": cp["fields"]["trainer"],
            }
        )
        checkpoint_map[cp["pk"]] = checkpoint

    # Import seeds → Run (bulk for performance)
    runs_to_create = []
    for s in seeds:
        runs_to_create.append(Run(
            seed_number=s["pk"],
            challenge=challenge_map[s["fields"]["challenge"]],
        ))
    Run.objects.bulk_create(runs_to_create, ignore_conflicts=True)

    # Import results (bulk)
    results_to_create = []
    for r in results:
        results_to_create.append(CheckpointResult(
            run_id=r["fields"]["seed"],
            checkpoint=checkpoint_map[r["fields"]["checkpoint"]],
            cleared=r["fields"]["result"],
        ))
    CheckpointResult.objects.bulk_create(results_to_create, ignore_conflicts=True)

    # Update denormalized fields
    for run in Run.objects.prefetch_related("results__checkpoint"):
        cleared = run.results.filter(cleared=True).order_by("-checkpoint__order").first()
        if cleared:
            run.highest_checkpoint = cleared.checkpoint
            run.is_victory = cleared.checkpoint.order == 23  # Champion
            run.save(update_fields=["highest_checkpoint", "is_victory"])


if __name__ == "__main__":
    import_ironmon()
```

#### API Endpoints

```python
# api.py
router = Router(tags=["IronMON"])

@router.get("/ironmon/stats")
def get_stats(request, challenge: str = None):
    """Aggregate stats: total seeds, victories, clear rates per checkpoint."""

@router.get("/ironmon/runs")
def list_runs(request, challenge: str = None, limit: int = 50):
    """Recent runs with highest checkpoint reached."""

@router.get("/ironmon/checkpoints/stats")
def checkpoint_stats(request, challenge: str = None):
    """Clear rates per checkpoint - the 'wall' chart."""
```

#### Synthform Integration (Phase 2)

After import, update Synthform to:
1. Remove local IronMON models
2. Publish events to Redis `events:questlog` channel on checkpoint results
3. Query Questlog API for overlay stats display

See CLAUDE.md "WebSocket Support for Synthform Integration" section for Redis pub/sub pattern.

## Planned Features

### ACNH Local Image Storage

Store villager images locally instead of depending on external GitHub URLs:
- Configure Django media storage (local or S3)
- Download 391 villager icons and images (~50-100MB)
- Add ImageField to Villager model
- Serve via whitenoise or CDN

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
