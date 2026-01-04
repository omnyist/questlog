from __future__ import annotations

import uuid

from django.db import models


class Game(models.Model):
    """
    IGDB-backed game metadata, cached locally.

    This is the anchor for all game-related data. PlayedGame, ListEntry,
    and game-specific profiles all link back to this model.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    igdb_id = models.IntegerField(unique=True, null=True, blank=True)
    slug = models.SlugField(unique=True, max_length=255)
    name = models.CharField(max_length=255)
    cover_url = models.URLField(blank=True)
    release_date = models.DateField(null=True, blank=True)
    summary = models.TextField(blank=True)

    # Full IGDB response for additional data as needed
    igdb_data = models.JSONField(default=dict, blank=True)
    last_synced = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name
