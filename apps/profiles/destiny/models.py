from __future__ import annotations

import uuid

from django.db import models


class Profile(models.Model):
    """Destiny 2 profile — the root archival record."""

    MEMBERSHIP_TYPES = [
        (1, "Xbox"),
        (2, "PSN"),
        (3, "Steam"),
        (4, "Blizzard"),
        (5, "Stadia"),
        (6, "EpicGames"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    work = models.OneToOneField(
        "library.Work",
        on_delete=models.CASCADE,
        related_name="destiny_profile",
    )

    bungie_name = models.CharField(max_length=100, blank=True)
    bungie_name_code = models.IntegerField(null=True, blank=True)
    membership_type = models.IntegerField(choices=MEMBERSHIP_TYPES, default=3)
    membership_id = models.CharField(max_length=30, blank=True, db_index=True)

    profile_data = models.JSONField(default=dict, blank=True)
    metrics_data = models.JSONField(default=dict, blank=True)
    collectibles_data = models.JSONField(default=dict, blank=True)
    records_data = models.JSONField(default=dict, blank=True)

    last_synced = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        if self.bungie_name and self.bungie_name_code:
            return f"{self.bungie_name}#{self.bungie_name_code:04d}"
        return "Destiny 2 Profile"


class Character(models.Model):
    """A Destiny 2 character (Titan, Hunter, or Warlock)."""

    CLASSES = [
        ("titan", "Titan"),
        ("hunter", "Hunter"),
        ("warlock", "Warlock"),
    ]
    RACES = [
        ("human", "Human"),
        ("awoken", "Awoken"),
        ("exo", "Exo"),
    ]
    GENDERS = [
        ("male", "Male"),
        ("female", "Female"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    profile = models.ForeignKey(
        Profile,
        on_delete=models.CASCADE,
        related_name="characters",
    )
    character_id = models.CharField(max_length=30, unique=True, db_index=True)

    character_class = models.CharField(max_length=10, choices=CLASSES, blank=True)
    race = models.CharField(max_length=10, choices=RACES, blank=True)
    gender = models.CharField(max_length=10, choices=GENDERS, blank=True)
    light_level = models.IntegerField(default=0)
    minutes_played = models.BigIntegerField(default=0)
    date_last_played = models.DateTimeField(null=True, blank=True)
    emblem_path = models.CharField(max_length=255, blank=True)
    emblem_background_path = models.CharField(max_length=255, blank=True)
    is_deleted = models.BooleanField(default=False)

    raw_data = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-light_level"]

    def __str__(self):
        return f"{self.get_character_class_display()} ({self.light_level})"


class AggregateStats(models.Model):
    """Aggregate lifetime stats for a mode, account-wide or per-character."""

    SCOPES = [
        ("account", "Account (All Characters)"),
        ("account_deleted", "Account (Deleted Characters)"),
        ("character", "Per-Character"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    profile = models.ForeignKey(
        Profile,
        on_delete=models.CASCADE,
        related_name="aggregate_stats",
    )
    character = models.ForeignKey(
        Character,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="aggregate_stats",
    )
    scope = models.CharField(max_length=20, choices=SCOPES)
    mode = models.CharField(max_length=50, db_index=True)

    activities_entered = models.IntegerField(default=0)
    activities_won = models.IntegerField(default=0)
    activities_cleared = models.IntegerField(default=0)
    kills = models.IntegerField(default=0)
    deaths = models.IntegerField(default=0)
    assists = models.IntegerField(default=0)
    precision_kills = models.IntegerField(default=0)
    suicides = models.IntegerField(default=0)
    best_single_game_kills = models.IntegerField(default=0)
    longest_kill_spree = models.IntegerField(default=0)
    longest_single_life = models.FloatField(default=0)
    orbs_dropped = models.IntegerField(default=0)
    resurrections_performed = models.IntegerField(default=0)
    resurrections_received = models.IntegerField(default=0)
    seconds_played = models.BigIntegerField(default=0)
    average_lifespan = models.FloatField(default=0)
    kd_ratio = models.FloatField(default=0)
    kda_ratio = models.FloatField(default=0)
    efficiency = models.FloatField(default=0)
    best_single_game_score = models.IntegerField(default=0)
    fastest_completion = models.FloatField(default=0)
    longest_kill_distance = models.FloatField(default=0)
    total_kill_distance = models.FloatField(default=0)
    highest_light_level = models.IntegerField(default=0)
    combat_rating = models.FloatField(default=0)

    raw_stats = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "aggregate stats"
        unique_together = [("profile", "character", "scope", "mode")]
        ordering = ["scope", "mode"]

    def __str__(self):
        label = str(self.character) if self.character else self.get_scope_display()
        return f"{label} / {self.mode}"


class Activity(models.Model):
    """A single activity instance played (raid, strike, crucible match, etc.)."""

    MODE_CATEGORIES = [
        ("raid", "Raid"),
        ("dungeon", "Dungeon"),
        ("nightfall", "Nightfall"),
        ("strike", "Strike"),
        ("crucible", "Crucible"),
        ("trials", "Trials of Osiris"),
        ("ironbanner", "Iron Banner"),
        ("gambit", "Gambit"),
        ("story", "Story"),
        ("patrol", "Patrol"),
        ("social", "Social"),
        ("other", "Other"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    profile = models.ForeignKey(
        Profile,
        on_delete=models.CASCADE,
        related_name="activities",
    )
    character = models.ForeignKey(
        Character,
        on_delete=models.CASCADE,
        related_name="activities",
    )
    instance_id = models.CharField(max_length=30, unique=True, db_index=True)

    activity_hash = models.BigIntegerField(db_index=True)
    activity_type_hash = models.BigIntegerField(default=0)
    director_activity_hash = models.BigIntegerField(default=0)

    activity_name = models.CharField(max_length=255, blank=True)
    mode = models.IntegerField(default=0)
    mode_name = models.CharField(max_length=100, blank=True)
    mode_category = models.CharField(
        max_length=20,
        choices=MODE_CATEGORIES,
        default="other",
        db_index=True,
    )

    period = models.DateTimeField(db_index=True)
    duration_seconds = models.IntegerField(default=0)

    completed = models.BooleanField(default=False)
    standing = models.IntegerField(null=True, blank=True)

    kills = models.IntegerField(default=0)
    deaths = models.IntegerField(default=0)
    assists = models.IntegerField(default=0)
    score = models.IntegerField(default=0)
    team_score = models.IntegerField(default=0)
    kd_ratio = models.FloatField(default=0)
    efficiency = models.FloatField(default=0)
    completion_reason = models.IntegerField(default=0)

    raw_values = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "activities"
        ordering = ["-period"]
        indexes = [
            models.Index(fields=["mode_category", "-period"]),
            models.Index(fields=["character", "-period"]),
        ]

    def __str__(self):
        label = self.activity_name or f"Activity {self.activity_hash}"
        return f"{label} ({self.period.date()})"


class CarnageReport(models.Model):
    """Post-Game Carnage Report (PGCR) for a single activity instance."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    activity = models.OneToOneField(
        Activity,
        on_delete=models.CASCADE,
        related_name="carnage_report",
    )
    instance_id = models.CharField(max_length=30, unique=True, db_index=True)

    activity_hash = models.BigIntegerField(default=0)
    activity_name = models.CharField(max_length=255, blank=True)
    period = models.DateTimeField()
    is_private = models.BooleanField(default=False)
    starting_phase_index = models.IntegerField(default=0)

    raw_data = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-period"]

    def __str__(self):
        return f"PGCR: {self.activity_name or self.instance_id}"


class CarnageReportEntry(models.Model):
    """One player's performance in a PGCR."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    report = models.ForeignKey(
        CarnageReport,
        on_delete=models.CASCADE,
        related_name="entries",
    )

    membership_id = models.CharField(max_length=30, db_index=True)
    membership_type = models.IntegerField(default=0)
    display_name = models.CharField(max_length=100, blank=True)
    character_id = models.CharField(max_length=30, blank=True)
    character_class = models.CharField(max_length=10, blank=True)
    light_level = models.IntegerField(default=0)
    is_self = models.BooleanField(default=False, db_index=True)

    kills = models.IntegerField(default=0)
    deaths = models.IntegerField(default=0)
    assists = models.IntegerField(default=0)
    score = models.IntegerField(default=0)
    completed = models.BooleanField(default=False)
    time_played_seconds = models.IntegerField(default=0)

    raw_values = models.JSONField(default=dict, blank=True)

    class Meta:
        verbose_name_plural = "carnage report entries"
        ordering = ["-kills"]

    def __str__(self):
        return f"{self.display_name} ({self.kills}K/{self.deaths}D)"


class ManifestCache(models.Model):
    """Tracks the downloaded Bungie manifest version on disk."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    version = models.CharField(max_length=100, unique=True)
    locale = models.CharField(max_length=10, default="en")
    file_path = models.CharField(max_length=500, blank=True)
    downloaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-downloaded_at"]

    def __str__(self):
        return f"Manifest {self.version} ({self.locale})"
