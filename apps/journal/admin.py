from __future__ import annotations

from django.contrib import admin

from .models import Playthrough


@admin.register(Playthrough)
class PlaythroughAdmin(admin.ModelAdmin):
    list_display = ["game", "platform", "started_at", "completed_at", "rating"]
    list_filter = ["platform", "completed_at"]
    search_fields = ["game__name", "notes"]
    readonly_fields = ["id", "created_at", "updated_at"]
    autocomplete_fields = ["game"]
