from __future__ import annotations

import uuid

from django.db import models


class Profile(models.Model):
    """Path of Exile profile linking to the Work record."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    work = models.OneToOneField(
        "library.Work",
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
