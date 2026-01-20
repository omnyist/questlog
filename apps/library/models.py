from __future__ import annotations

import uuid

from django.db import models


class Franchise(models.Model):
    """Optional grouping for related Works (e.g., 'Final Fantasy', 'Xenoblade')."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    slug = models.SlugField(unique=True, max_length=255)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "franchises"

    def __str__(self):
        return self.name


class Work(models.Model):
    """
    A discrete beatable game experience.

    This represents the conceptual game - 'Final Fantasy VII', 'Torna ~ The Golden Country'.
    Different releases (PS1, Remake, Remaster) are Editions of a Work.
    """

    RELATIONSHIP_TYPES = [
        ("sequel", "Sequel"),
        ("prequel", "Prequel"),
        ("spinoff", "Spinoff"),
        ("epilogue", "Epilogue"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    slug = models.SlugField(unique=True, max_length=255)

    franchise = models.ForeignKey(
        Franchise,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="works",
    )
    parent_work = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="related_works",
    )
    relationship_type = models.CharField(
        max_length=20,
        blank=True,
        choices=RELATIONSHIP_TYPES,
    )

    original_release_year = models.IntegerField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Edition(models.Model):
    """
    A specific release of a Work.

    This is where IGDB data lives. A Work like 'Final Fantasy Tactics' might have
    Editions for the PS1 original, War of the Lions (PSP), and mobile ports.
    """

    EDITION_TYPES = [
        ("original", "Original"),
        ("port", "Port"),
        ("remaster", "Remaster"),
        ("enhanced", "Enhanced"),
        ("remake", "Remake"),
        ("definitive", "Definitive"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    work = models.ForeignKey(Work, on_delete=models.CASCADE, related_name="editions")
    name = models.CharField(max_length=255)
    slug = models.SlugField(unique=True, max_length=255)

    edition_type = models.CharField(
        max_length=20,
        default="original",
        choices=EDITION_TYPES,
    )

    # IGDB data
    igdb_id = models.IntegerField(unique=True, null=True, blank=True)
    cover_url = models.URLField(blank=True)
    release_date = models.DateField(null=True, blank=True)
    summary = models.TextField(blank=True)
    platforms = models.JSONField(default=list, blank=True)
    igdb_data = models.JSONField(default=dict, blank=True)
    last_synced = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["work__name", "release_date"]

    def __str__(self):
        if self.name == self.work.name:
            return self.name
        return f"{self.name} ({self.work.name})"
