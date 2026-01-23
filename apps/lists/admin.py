from __future__ import annotations

from django.contrib import admin

from .models import Entry, List, ListActivity


class EntryInline(admin.TabularInline):
    model = Entry
    extra = 1
    autocomplete_fields = ["work"]


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
    list_display = ["work", "list", "position", "added_at"]
    list_filter = ["list", "work__franchise"]
    search_fields = ["work__name", "list__name"]
    readonly_fields = ["id", "added_at"]
    autocomplete_fields = ["work", "list"]


@admin.register(ListActivity)
class ListActivityAdmin(admin.ModelAdmin):
    list_display = ["list", "verb", "entry_summary", "timestamp"]
    list_filter = ["list", "verb"]
    search_fields = ["list__name", "entries"]
    readonly_fields = ["id", "list", "timestamp", "verb", "entries", "metadata"]
    ordering = ["-timestamp"]

    @admin.display(description="Entries")
    def entry_summary(self, obj):
        count = len(obj.entries)
        if count == 1:
            return obj.entries[0]
        return f"{count} entries"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
