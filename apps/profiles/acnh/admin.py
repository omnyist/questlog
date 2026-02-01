from __future__ import annotations

from django.contrib import admin

from .models import Encounter
from .models import Profile
from .models import VillagerHunt


class VillagerHuntInline(admin.TabularInline):
    model = VillagerHunt
    extra = 0
    show_change_link = True
    fields = ["date", "target_villager", "result_villager", "encounter_count"]
    readonly_fields = ["encounter_count"]

    @admin.display(description="Islands")
    def encounter_count(self, obj):
        return obj.encounters.count()


class EncounterInline(admin.TabularInline):
    model = Encounter
    extra = 1
    fields = [
        "villager_name",
        "personality",
        "species",
        "timestamp",
        "bonus_item",
        "seen_before",
        "recruited",
    ]


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ["__str__", "island_name", "player_name", "hemisphere"]
    readonly_fields = ["id", "created_at", "updated_at"]
    inlines = [VillagerHuntInline]


@admin.register(VillagerHunt)
class VillagerHuntAdmin(admin.ModelAdmin):
    list_display = ["__str__", "date", "encounter_count", "profile"]
    list_filter = ["profile", "date"]
    search_fields = ["target_villager", "result_villager"]
    readonly_fields = ["id", "created_at", "updated_at"]
    inlines = [EncounterInline]

    @admin.display(description="Islands Visited")
    def encounter_count(self, obj):
        return obj.encounters.count()
