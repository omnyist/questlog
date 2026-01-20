from __future__ import annotations

from django.contrib import admin

from .models import Playthrough


@admin.register(Playthrough)
class PlaythroughAdmin(admin.ModelAdmin):
    list_display = ["edition", "platform", "started_at", "completed_at", "rating"]
    list_filter = ["platform", "completed_at", "edition__work__franchise"]
    search_fields = ["edition__name", "edition__work__name", "notes"]
    readonly_fields = ["id", "created_at", "updated_at"]
    autocomplete_fields = ["edition"]
