from __future__ import annotations

import uuid

from django.db import models


class Villager(models.Model):
    """An Animal Crossing villager from the ACNH API."""

    PERSONALITIES = [
        ("cranky", "Cranky"),
        ("jock", "Jock"),
        ("lazy", "Lazy"),
        ("normal", "Normal"),
        ("peppy", "Peppy"),
        ("smug", "Smug"),
        ("snooty", "Snooty"),
        ("uchi", "Uchi"),
    ]

    GENDERS = [
        ("male", "Male"),
        ("female", "Female"),
    ]

    id = models.PositiveIntegerField(primary_key=True, help_text="ACNH API ID")
    name = models.CharField(max_length=100, db_index=True)
    personality = models.CharField(max_length=20, choices=PERSONALITIES)
    species = models.CharField(max_length=50, db_index=True)
    gender = models.CharField(max_length=10, choices=GENDERS)
    birthday = models.CharField(max_length=10, blank=True)
    catchphrase = models.CharField(max_length=100, blank=True)
    hobby = models.CharField(max_length=50, blank=True)
    saying = models.TextField(blank=True)
    icon_url = models.URLField(blank=True)
    image_url = models.URLField(blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.species})"


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
    target_villager = models.ForeignKey(
        Villager,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="hunts_targeted",
        help_text="Who you were hoping to find",
    )
    result_villager = models.ForeignKey(
        Villager,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="hunts_recruited",
        help_text="Who you ended up recruiting",
    )
    notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date"]

    def __str__(self):
        if self.result_villager:
            target = self.target_villager.name if self.target_villager else "?"
            return f"Hunt for {target} → {self.result_villager.name}"
        return f"Hunt on {self.date}"

    @property
    def encounter_count(self):
        return self.encounters.count()

    @property
    def islands_visited(self):
        """Alias for encounter_count (NMT islands visited)."""
        return self.encounter_count


class Encounter(models.Model):
    """A single mystery island visit during a hunt."""

    PERSONALITIES = [
        ("cranky", "Cranky"),
        ("jock", "Jock"),
        ("lazy", "Lazy"),
        ("normal", "Normal"),
        ("peppy", "Peppy"),
        ("smug", "Smug"),
        ("snooty", "Snooty"),
        ("uchi", "Uchi"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    hunt = models.ForeignKey(
        VillagerHunt,
        on_delete=models.CASCADE,
        related_name="encounters",
    )
    villager_name = models.CharField(max_length=100)
    personality = models.CharField(max_length=20, choices=PERSONALITIES)
    species = models.CharField(max_length=50)
    timestamp = models.DateTimeField()
    bonus_item = models.CharField(max_length=255, blank=True)
    notes = models.TextField(blank=True, help_text="Internal monologue")
    seen_before = models.BooleanField(default=False)
    recruited = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-timestamp"]

    def __str__(self):
        recruited = " ✓" if self.recruited else ""
        return f"{self.villager_name} ({self.species}){recruited}"
