from __future__ import annotations

import uuid

from django.db import models


class List(models.Model):
    """A curated collection of Works - 'Top 25 RPGs', 'FF Favorites', etc."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    slug = models.SlugField(unique=True, max_length=255)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    is_ranked = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Entry(models.Model):
    """A Work's membership in a list."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    list = models.ForeignKey(
        List,
        on_delete=models.CASCADE,
        related_name="entries",
    )
    work = models.ForeignKey(
        "library.Work",
        on_delete=models.CASCADE,
        related_name="list_entries",
    )
    position = models.IntegerField(null=True, blank=True)
    notes = models.TextField(blank=True)

    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ["list", "work"]
        ordering = ["position", "-added_at"]
        verbose_name_plural = "entries"

    def __str__(self):
        pos = f"#{self.position} " if self.position else ""
        return f"{pos}{self.work.name} in {self.list.name}"


class ListActivity(models.Model):
    """Tracks changes to a list over time, like gist revision history."""

    VERBS = [
        ("created", "Created"),
        ("added", "Added"),
        ("removed", "Removed"),
        ("reordered", "Reordered"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    list = models.ForeignKey(
        List,
        on_delete=models.CASCADE,
        related_name="activity",
    )
    timestamp = models.DateTimeField(auto_now_add=True)
    verb = models.CharField(max_length=20, choices=VERBS)
    entries = models.JSONField(default=lambda: [], blank=True)  # Work slugs affected
    metadata = models.JSONField(default=dict, blank=True)  # Extra context

    class Meta:
        ordering = ["-timestamp"]
        verbose_name_plural = "list activities"

    def __str__(self):
        count = len(self.entries)
        if count == 1:
            return f"{self.verb} {self.entries[0]} in {self.list.name}"
        return f"{self.verb} {count} entries in {self.list.name}"
