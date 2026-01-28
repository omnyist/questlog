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


class VillagerHunt(models.Model):
    """A villager hunting session (filling one open plot)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    profile = models.ForeignKey(
        Profile,
        on_delete=models.CASCADE,
        related_name="hunts",
    )
    date = models.DateField()
    target_villager = models.CharField(
        max_length=100,
        blank=True,
        help_text="Who you were hoping to find",
    )
    result_villager = models.CharField(
        max_length=100,
        blank=True,
        help_text="Who you ended up recruiting",
    )
    notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date"]

    def __str__(self):
        if self.result_villager:
            return f"Hunt for {self.target_villager or '?'} → {self.result_villager}"
        return f"Hunt on {self.date}"

    @property
    def encounter_count(self):
        return self.encounters.count()

    @property
    def islands_visited(self):
        """Alias for encounter_count (NMT islands visited)."""
        return self.encounter_count
