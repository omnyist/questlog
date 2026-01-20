from __future__ import annotations

from django.contrib import admin

from .models import Edition, Franchise, Work


@admin.register(Franchise)
class FranchiseAdmin(admin.ModelAdmin):
    list_display = ["name", "slug"]
    search_fields = ["name"]
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Work)
class WorkAdmin(admin.ModelAdmin):
    list_display = ["name", "franchise", "original_release_year", "parent_work"]
    list_filter = ["franchise", "relationship_type"]
    search_fields = ["name", "slug"]
    readonly_fields = ["id", "created_at", "updated_at"]
    prepopulated_fields = {"slug": ("name",)}
    autocomplete_fields = ["franchise", "parent_work"]


@admin.register(Edition)
class EditionAdmin(admin.ModelAdmin):
    list_display = ["name", "work", "edition_type", "release_date", "igdb_id"]
    list_filter = ["edition_type", "work__franchise"]
    search_fields = ["name", "slug", "work__name"]
    readonly_fields = ["id", "created_at", "updated_at", "last_synced"]
    prepopulated_fields = {"slug": ("name",)}
    autocomplete_fields = ["work"]
