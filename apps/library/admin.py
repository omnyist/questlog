from __future__ import annotations

from django.contrib import admin

from .models import Edition, Franchise, Genre, Work


@admin.register(Genre)
class GenreAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "parent", "igdb_id"]
    list_filter = ["parent"]
    search_fields = ["name"]
    prepopulated_fields = {"slug": ("name",)}
    autocomplete_fields = ["parent"]


@admin.register(Franchise)
class FranchiseAdmin(admin.ModelAdmin):
    list_display = ["name", "slug"]
    search_fields = ["name"]
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Work)
class WorkAdmin(admin.ModelAdmin):
    list_display = ["name", "franchise", "primary_genre", "original_release_year"]
    list_filter = ["franchise", "primary_genre", "genres", "relationship_type"]
    search_fields = ["name", "slug"]
    readonly_fields = ["id", "created_at", "updated_at"]
    prepopulated_fields = {"slug": ("name",)}
    autocomplete_fields = ["franchise", "parent_work", "primary_genre"]
    filter_horizontal = ["genres"]


@admin.register(Edition)
class EditionAdmin(admin.ModelAdmin):
    list_display = ["name", "work", "edition_type", "release_date", "igdb_id"]
    list_filter = ["edition_type", "work__franchise"]
    search_fields = ["name", "slug", "work__name"]
    readonly_fields = ["id", "created_at", "updated_at", "last_synced"]
    prepopulated_fields = {"slug": ("name",)}
    autocomplete_fields = ["work"]
