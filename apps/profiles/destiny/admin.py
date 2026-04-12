from __future__ import annotations

from django.contrib import admin

from .models import Activity
from .models import AggregateStats
from .models import CarnageReport
from .models import CarnageReportEntry
from .models import Character
from .models import ManifestCache
from .models import Profile


class CharacterInline(admin.TabularInline):
    model = Character
    extra = 0
    readonly_fields = [
        "character_id",
        "character_class",
        "race",
        "gender",
        "light_level",
        "minutes_played",
        "date_last_played",
        "is_deleted",
    ]
    fields = readonly_fields
    can_delete = False
    show_change_link = True


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ["__str__", "membership_type", "membership_id", "last_synced"]
    list_filter = ["membership_type"]
    search_fields = ["bungie_name", "membership_id"]
    readonly_fields = ["id", "created_at", "updated_at", "last_synced"]
    inlines = [CharacterInline]


@admin.register(Character)
class CharacterAdmin(admin.ModelAdmin):
    list_display = [
        "character_class",
        "race",
        "gender",
        "light_level",
        "minutes_played",
        "date_last_played",
        "is_deleted",
    ]
    list_filter = ["character_class", "race", "is_deleted"]
    search_fields = ["character_id"]
    readonly_fields = ["id", "character_id", "created_at", "updated_at"]
    list_select_related = ["profile"]


@admin.register(AggregateStats)
class AggregateStatsAdmin(admin.ModelAdmin):
    list_display = [
        "mode",
        "scope",
        "character",
        "activities_entered",
        "kills",
        "deaths",
        "kd_ratio",
        "seconds_played",
    ]
    list_filter = ["scope", "mode"]
    search_fields = ["mode"]
    readonly_fields = ["id", "created_at", "updated_at"]
    list_select_related = ["character", "profile"]


@admin.register(Activity)
class ActivityAdmin(admin.ModelAdmin):
    list_display = [
        "activity_name",
        "mode_category",
        "period",
        "completed",
        "kills",
        "deaths",
        "assists",
        "duration_seconds",
    ]
    list_filter = ["mode_category", "completed"]
    search_fields = ["activity_name", "instance_id"]
    date_hierarchy = "period"
    readonly_fields = ["id", "instance_id", "created_at"]
    list_select_related = ["character", "profile"]
    list_per_page = 50


class CarnageReportEntryInline(admin.TabularInline):
    model = CarnageReportEntry
    extra = 0
    readonly_fields = [
        "display_name",
        "character_class",
        "light_level",
        "is_self",
        "kills",
        "deaths",
        "assists",
        "score",
        "completed",
        "time_played_seconds",
    ]
    fields = readonly_fields
    can_delete = False


@admin.register(CarnageReport)
class CarnageReportAdmin(admin.ModelAdmin):
    list_display = ["activity_name", "period", "is_private"]
    list_filter = ["is_private"]
    search_fields = ["activity_name", "instance_id"]
    readonly_fields = ["id", "instance_id", "created_at"]
    date_hierarchy = "period"
    inlines = [CarnageReportEntryInline]


@admin.register(CarnageReportEntry)
class CarnageReportEntryAdmin(admin.ModelAdmin):
    list_display = [
        "display_name",
        "character_class",
        "light_level",
        "is_self",
        "kills",
        "deaths",
        "assists",
        "completed",
    ]
    list_filter = ["is_self", "character_class", "completed"]
    search_fields = ["display_name", "membership_id"]
    list_select_related = ["report"]


@admin.register(ManifestCache)
class ManifestCacheAdmin(admin.ModelAdmin):
    list_display = ["version", "locale", "downloaded_at", "file_path"]
    readonly_fields = ["id", "downloaded_at"]
