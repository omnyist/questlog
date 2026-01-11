from __future__ import annotations

import uuid

from django.db import models


class Profile(models.Model):
    """Path of Exile profile linking to the base Game record."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    game = models.OneToOneField(
        "library.Game",
        on_delete=models.CASCADE,
        related_name="poe_profile",
    )
    account_name = models.CharField(max_length=100, blank=True)
    data = models.JSONField(default=dict, blank=True)
    last_synced = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return "Path of Exile Profile"
