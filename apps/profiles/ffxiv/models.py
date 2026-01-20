from __future__ import annotations

import uuid

from django.db import models


class Profile(models.Model):
    """FFXIV profile linking to the Work record."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    work = models.OneToOneField(
        "library.Work",
        on_delete=models.CASCADE,
        related_name="ffxiv_profile",
    )
    lodestone_id = models.CharField(max_length=50, blank=True)
    last_synced = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return "FFXIV Profile"


class Character(models.Model):
    """An FFXIV character."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    profile = models.ForeignKey(
        Profile,
        on_delete=models.CASCADE,
        related_name="characters",
    )
    name = models.CharField(max_length=255)
    server = models.CharField(max_length=100)
    data = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} @ {self.server}"
