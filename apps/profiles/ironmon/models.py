from __future__ import annotations

from django.db import models


class Challenge(models.Model):
    """The challenge ruleset (Kaizo, Super Kaizo, Ultimate, etc.)."""

    slug = models.SlugField(unique=True)
    name = models.TextField()  # "Kaizo", "Super Kaizo"
    edition = models.ForeignKey(
        "library.Edition",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="ironmon_challenges",
    )

    def __str__(self):
        return self.name


class Checkpoint(models.Model):
    """A checkpoint within a challenge (gym leaders, rival battles, E4, etc.)."""

    challenge = models.ForeignKey(
        Challenge,
        on_delete=models.CASCADE,
        related_name="checkpoints",
    )
    name = models.TextField()
    trainer = models.TextField()
    order = models.IntegerField()

    class Meta:
        ordering = ["order"]
        unique_together = ["challenge", "order"]

    def __str__(self):
        return f"{self.order}. {self.name}"


class Run(models.Model):
    """A single IronMON attempt (maps to Synthform's Seed)."""

    seed_number = models.IntegerField(primary_key=True)
    challenge = models.ForeignKey(
        Challenge,
        on_delete=models.CASCADE,
        related_name="runs",
    )
    started_at = models.DateTimeField(auto_now_add=True)

    # Denormalized for quick queries
    highest_checkpoint = models.ForeignKey(
        Checkpoint,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    is_victory = models.BooleanField(default=False)

    class Meta:
        ordering = ["-seed_number"]

    def __str__(self):
        if self.is_victory:
            return f"Seed {self.seed_number} ✓"
        if self.highest_checkpoint:
            return f"Seed {self.seed_number} → {self.highest_checkpoint.name}"
        return f"Seed {self.seed_number}"


class CheckpointResult(models.Model):
    """Result of a checkpoint attempt (maps to Synthform's Result)."""

    run = models.ForeignKey(
        Run,
        on_delete=models.CASCADE,
        related_name="results",
    )
    checkpoint = models.ForeignKey(
        Checkpoint,
        on_delete=models.CASCADE,
        related_name="results",
    )
    cleared = models.BooleanField()
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ["run", "checkpoint"]
        ordering = ["checkpoint__order"]

    def __str__(self):
        status = "✓" if self.cleared else "✗"
        return f"{self.checkpoint.name}: {status}"
