from __future__ import annotations

from django.contrib import admin

from .models import Affiliation
from .models import MissionStat
from .models import Profile
from .models import Snapshot
from .models import WeaponStat


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = [
        "display_name",
        "platform",
        "mastery_rank",
        "time_played_seconds",
        "missions_completed",
        "last_synced",
    ]
    list_filter = ["platform"]
    search_fields = ["display_name", "account_id", "steam_id"]
    readonly_fields = [
        "id",
        "account_id",
        "wf_created_at",
        "created_at",
        "updated_at",
        "last_synced",
    ]


@admin.register(WeaponStat)
class WeaponStatAdmin(admin.ModelAdmin):
    list_display = [
        "weapon_name",
        "kills",
        "headshots",
        "fired",
        "hits",
        "accuracy",
        "equip_time_seconds",
        "xp",
    ]
    list_filter = ["profile"]
    search_fields = ["weapon_name", "weapon_path"]
    readonly_fields = ["id", "created_at", "updated_at"]
    list_select_related = ["profile"]
    list_per_page = 50


@admin.register(MissionStat)
class MissionStatAdmin(admin.ModelAdmin):
    list_display = ["node_tag", "completes", "profile"]
    search_fields = ["node_tag"]
    readonly_fields = ["id", "created_at", "updated_at"]
    list_select_related = ["profile"]
    list_per_page = 50


@admin.register(Affiliation)
class AffiliationAdmin(admin.ModelAdmin):
    list_display = ["syndicate_tag", "standing", "title_rank", "profile"]
    search_fields = ["syndicate_tag"]
    readonly_fields = ["id", "created_at", "updated_at"]
    list_select_related = ["profile"]


@admin.register(Snapshot)
class SnapshotAdmin(admin.ModelAdmin):
    list_display = [
        "captured_at",
        "trigger",
        "mastery_rank",
        "time_played_seconds",
        "missions_completed",
        "total_weapon_kills",
        "profile",
    ]
    list_filter = ["trigger"]
    readonly_fields = [
        "id",
        "captured_at",
        "mastery_rank",
        "time_played_seconds",
        "missions_completed",
        "pickup_count",
        "total_weapon_kills",
        "weapons_tracked",
    ]
    date_hierarchy = "captured_at"
    list_select_related = ["profile"]
