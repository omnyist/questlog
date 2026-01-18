from __future__ import annotations

from django.contrib import admin

from .models import Game


@admin.register(Game)
class GameAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "release_date", "igdb_id", "last_synced"]
    list_filter = ["release_date"]
    search_fields = ["name", "slug"]
    readonly_fields = ["id", "created_at", "updated_at", "last_synced"]
    prepopulated_fields = {"slug": ("name",)}
