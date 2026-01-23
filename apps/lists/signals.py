from __future__ import annotations

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .models import Entry, ListActivity


@receiver(post_save, sender=Entry)
def log_entry_added(sender, instance, created, **kwargs):
    """Log when an entry is added to a list."""
    if created:
        ListActivity.objects.create(
            list=instance.list,
            verb="added",
            entries=[instance.work.slug],
        )


@receiver(post_delete, sender=Entry)
def log_entry_removed(sender, instance, **kwargs):
    """Log when an entry is removed from a list."""
    ListActivity.objects.create(
        list=instance.list,
        verb="removed",
        entries=[instance.work.slug],
    )