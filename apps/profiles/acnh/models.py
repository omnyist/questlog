from __future__ import annotations

import uuid

from django.db import models


class Profile(models.Model):
    """ACNH profile linking to the Work record."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    work = models.OneToOneField(
        "library.Work",
        on_delete=models.CASCADE,
        related_name="acnh_profile",
    )
    island_name = models.CharField(max_length=100, blank=True)
    player_name = models.CharField(max_length=100, blank=True)
    hemisphere = models.CharField(
        max_length=10,
        choices=[("north", "Northern"), ("south", "Southern")],
        blank=True,
    )
    native_fruit = models.CharField(max_length=50, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        if self.island_name:
            return f"{self.island_name} Island"
        return "ACNH Profile"
