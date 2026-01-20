from __future__ import annotations

import uuid

from django.db import models


class Playthrough(models.Model):
    """
    A record of playing/beating an Edition.

    One Playthrough per run - if you beat FF4 on SNES in 1995
    and the DS remake in 2008, that's two Playthrough records
    (potentially of different Editions of the same Work).
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    edition = models.ForeignKey(
        "library.Edition",
        on_delete=models.CASCADE,
        related_name="playthroughs",
    )

    platform = models.CharField(max_length=100, blank=True)
    started_at = models.DateField(null=True, blank=True)
    completed_at = models.DateField(null=True, blank=True)
    playtime_hours = models.IntegerField(null=True, blank=True)
    rating = models.IntegerField(null=True, blank=True)
    notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-completed_at", "-created_at"]

    def __str__(self):
        platform_str = f" ({self.platform})" if self.platform else ""
        return f"{self.edition.work.name}{platform_str}"

    @property
    def is_completed(self):
        return self.completed_at is not None

    @property
    def work(self):
        """Convenience accessor for the Work."""
        return self.edition.work
