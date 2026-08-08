from __future__ import annotations

import uuid

from django.db import models
from django.utils import timezone


class TimestampedModel(models.Model):
    """Shared timestamps.

    Explicit defaults rather than auto_now/auto_now_add: those ignore assigned
    values, which breaks the screenshot backfill (records are created now but
    describe runs from months ago).
    """

    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    updated_at = models.DateTimeField(default=timezone.now)

    class Meta:
        abstract = True


class Profile(TimestampedModel):
    """Umamusume profile linking to the Work record."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    work = models.OneToOneField(
        "library.Work",
        on_delete=models.CASCADE,
        related_name="umamusume_profile",
    )
    data = models.JSONField(default=dict, blank=True)

    def __str__(self):
        return "Umamusume Profile"


class Character(TimestampedModel):
    """A base umamusume character — the Hall of Fame entry (e.g. "Gold Ship").

    Outfits of the same character group under one entry, so every El Condor
    Pasa run sits together regardless of which version was trained.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    profile = models.ForeignKey(
        Profile,
        on_delete=models.CASCADE,
        related_name="characters",
    )
    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=100, unique=True)

    # `chara_data.id` from the game's master.mdb, as exposed by community
    # databases (umapyoi.net, GameTora). Lets this archive join to their data
    # for art and metadata instead of matching on names. Backfilled later.
    game_chara_id = models.IntegerField(null=True, blank=True, unique=True, db_index=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Outfit(TimestampedModel):
    """A specific trainable version of a character — `card_data` in the game's
    master.mdb, which keys cards to characters exactly as this does.

    `title` is the bracketed prefix — "Starlight Beat" for [Starlight Beat]
    Oguri Cap — and is blank for a character's base version. The game's own data
    separates CardName (the character) from CardTitle (this), hence `title`
    rather than `name`. Runs attach here, not to the character, because separate
    versions are genuinely different units to train.

    Note: the live game also has an unrelated cosmetic costume system players
    call "outfits". That's a different mechanic and isn't modeled here.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    character = models.ForeignKey(
        Character,
        on_delete=models.CASCADE,
        related_name="outfits",
    )
    title = models.CharField(max_length=100, blank=True)
    slug = models.SlugField(max_length=150, unique=True)
    image_url = models.URLField(blank=True)

    # `card_data.id` from master.mdb — see Character.game_chara_id.
    game_card_id = models.IntegerField(null=True, blank=True, unique=True, db_index=True)

    class Meta:
        ordering = ["character__name", "title"]
        constraints = [
            models.UniqueConstraint(
                fields=["character", "title"],
                name="unique_outfit_per_character",
            )
        ]

    def __str__(self):
        return f"[{self.title}] {self.character.name}" if self.title else self.character.name


class CareerRun(TimestampedModel):
    """One completed career run, reconstructed from its end-of-run screenshots.

    A run's data is spread across several screens (Details carries the raw
    stats; Result carries the career record and major wins), so one record is
    merged from a burst of screenshots taken within a few minutes.
    """

    PLATFORM_CHOICES = [("steam", "Steam"), ("ios", "iOS")]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    outfit = models.ForeignKey(
        Outfit,
        on_delete=models.CASCADE,
        related_name="runs",
    )

    # When the run was completed, taken from the screenshot capture time —
    # never the file mtime, which is when the images were copied here.
    run_date = models.DateTimeField(db_index=True)
    platform = models.CharField(max_length=10, choices=PLATFORM_CHOICES)

    # Headline result.
    # `rank` is the letter tier derived from the numeric `rating` — the game
    # treats these as two separate things, so this archive does too.
    rank = models.CharField(max_length=4, blank=True)  # S+, A, B+, ...
    rating = models.IntegerField(null=True, blank=True)
    # The game's swappable display "Title" earned on this run ("The GOAT").
    # Named `earned_title` to keep it distinct from Outfit.title.
    earned_title = models.CharField(max_length=100, blank=True)

    # Final stats. Explicit columns because these are the Hall of Fame sort keys.
    speed = models.IntegerField(null=True, blank=True)
    stamina = models.IntegerField(null=True, blank=True)
    power = models.IntegerField(null=True, blank=True)
    guts = models.IntegerField(null=True, blank=True)
    wit = models.IntegerField(null=True, blank=True)

    fans = models.IntegerField(null=True, blank=True)
    races = models.IntegerField(null=True, blank=True)
    wins = models.IntegerField(null=True, blank=True)

    # Aptitude grades keyed by track/distance/style (e.g. {"turf": "A", "dirt": "B"}).
    # Run-scoped rather than outfit-scoped — aptitudes can be raised during a run.
    aptitudes = models.JSONField(default=dict, blank=True)
    major_wins = models.JSONField(default=list, blank=True)

    # Setup that produced the run. Steam screenshots show the Career Profile
    # side panel; iOS ones don't, so these are empty for iOS-sourced runs.
    support_cards = models.JSONField(default=list, blank=True)
    legacy = models.JSONField(default=dict, blank=True)

    # Provenance: which screenshots this was built from, and the raw extraction.
    source_images = models.JSONField(default=list, blank=True)
    raw = models.JSONField(default=dict, blank=True)

    # Content hash over the identifying fields, so re-importing the same run —
    # or re-screenshotting it later — updates rather than duplicates.
    fingerprint = models.CharField(max_length=64, unique=True)

    class Meta:
        ordering = ["-run_date"]
        indexes = [
            models.Index(fields=["-rating"]),
            models.Index(fields=["outfit", "-rating"]),
        ]

    def __str__(self):
        return f"{self.outfit} — {self.rank} ({self.rating})"

    @property
    def is_perfect(self) -> bool:
        """Won every race entered — the 42/42 kind of run."""
        return bool(self.races) and self.races == self.wins
