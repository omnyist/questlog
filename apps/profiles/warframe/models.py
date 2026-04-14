from __future__ import annotations

import uuid

from django.db import models


class Profile(models.Model):
    """Warframe profile — root of the archive for one account."""

    PLATFORMS = [
        ("pc", "PC"),
        ("ps", "PlayStation"),
        ("xbox", "Xbox"),
        ("switch", "Switch"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    work = models.OneToOneField(
        "library.Work",
        on_delete=models.CASCADE,
        related_name="warframe_profile",
    )

    account_id = models.CharField(max_length=24, unique=True, db_index=True)
    steam_id = models.CharField(max_length=20, blank=True, db_index=True)
    display_name = models.CharField(max_length=100, blank=True)
    platform = models.CharField(max_length=10, choices=PLATFORMS, default="pc")

    wf_created_at = models.DateTimeField(null=True, blank=True)
    mastery_rank = models.IntegerField(default=0)
    player_level = models.IntegerField(default=0)
    title = models.CharField(max_length=255, blank=True)

    missions_completed = models.IntegerField(default=0)
    missions_quit = models.IntegerField(default=0)
    missions_failed = models.IntegerField(default=0)
    missions_interrupted = models.IntegerField(default=0)
    missions_dumped = models.IntegerField(default=0)

    time_played_seconds = models.BigIntegerField(default=0)
    pickup_count = models.BigIntegerField(default=0)
    daily_focus = models.IntegerField(default=0)
    migrated_to_console = models.BooleanField(default=False)

    profile_data = models.JSONField(default=dict, blank=True)
    stats_data = models.JSONField(default=dict, blank=True)

    last_synced = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        if self.display_name:
            return self.display_name
        return f"Warframe Profile ({self.account_id})"


class WeaponStat(models.Model):
    """Per-weapon cumulative stats. Updated in place on each sync."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    profile = models.ForeignKey(
        Profile,
        on_delete=models.CASCADE,
        related_name="weapons",
    )

    weapon_path = models.CharField(max_length=255)
    weapon_name = models.CharField(max_length=100, blank=True)

    fired = models.BigIntegerField(default=0)
    hits = models.BigIntegerField(default=0)
    kills = models.BigIntegerField(default=0)
    headshots = models.BigIntegerField(default=0)
    assists = models.BigIntegerField(default=0)
    equip_time_seconds = models.FloatField(default=0)
    xp = models.BigIntegerField(default=0)

    accuracy = models.FloatField(default=0)
    headshot_rate = models.FloatField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("profile", "weapon_path")]
        indexes = [
            models.Index(fields=["profile", "-kills"]),
            models.Index(fields=["profile", "-equip_time_seconds"]),
        ]
        ordering = ["-kills"]

    def __str__(self):
        return f"{self.weapon_name or self.weapon_path} ({self.kills}K)"


class MissionStat(models.Model):
    """Per-node mission completion counts."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    profile = models.ForeignKey(
        Profile,
        on_delete=models.CASCADE,
        related_name="missions",
    )

    node_tag = models.CharField(max_length=50)
    completes = models.IntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("profile", "node_tag")]
        ordering = ["-completes"]

    def __str__(self):
        return f"{self.node_tag}: {self.completes}"


class Affiliation(models.Model):
    """Per-syndicate standing and title rank."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    profile = models.ForeignKey(
        Profile,
        on_delete=models.CASCADE,
        related_name="affiliations",
    )

    syndicate_tag = models.CharField(max_length=50)
    standing = models.IntegerField(default=0)
    title_rank = models.IntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("profile", "syndicate_tag")]
        ordering = ["syndicate_tag"]

    def __str__(self):
        return f"{self.syndicate_tag}: {self.standing}"


class Snapshot(models.Model):
    """Timestamped snapshot of cumulative stats — for progression tracking."""

    TRIGGERS = [
        ("manual", "Manual"),
        ("session_end", "Session End"),
        ("scheduled", "Scheduled"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    profile = models.ForeignKey(
        Profile,
        on_delete=models.CASCADE,
        related_name="snapshots",
    )
    captured_at = models.DateTimeField(auto_now_add=True, db_index=True)
    trigger = models.CharField(max_length=20, choices=TRIGGERS, default="manual")

    mastery_rank = models.IntegerField(default=0)
    time_played_seconds = models.BigIntegerField(default=0)
    missions_completed = models.IntegerField(default=0)
    pickup_count = models.BigIntegerField(default=0)
    total_weapon_kills = models.BigIntegerField(default=0)
    weapons_tracked = models.IntegerField(default=0)

    raw_profile = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-captured_at"]

    def __str__(self):
        return f"{self.profile.display_name or self.profile.account_id} @ {self.captured_at:%Y-%m-%d}"
