from __future__ import annotations

from django.contrib import admin

from .models import Entry
from .models import List


class EntryInline(admin.TabularInline):
    model = Entry
    extra = 1
    autocomplete_fields = ["game"]


@admin.register(List)
class ListAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "is_ranked", "entry_count"]
    search_fields = ["name", "slug"]
    readonly_fields = ["id", "created_at", "updated_at"]
    prepopulated_fields = {"slug": ("name",)}
    inlines = [EntryInline]

    @admin.display(description="Entries")
    def entry_count(self, obj):
        return obj.entries.count()


@admin.register(Entry)
class EntryAdmin(admin.ModelAdmin):
    list_display = ["game", "list", "position", "added_at"]
    list_filter = ["list"]
    search_fields = ["game__name", "list__name"]
    readonly_fields = ["id", "added_at"]
    autocomplete_fields = ["game", "list"]
