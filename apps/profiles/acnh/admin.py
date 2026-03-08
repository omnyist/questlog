from __future__ import annotations

from django.contrib import admin
from django.db.models import Count

from .models import Encounter
from .models import Profile
from .models import Villager
from .models import VillagerHunt


@admin.register(Villager)
class VillagerAdmin(admin.ModelAdmin):
    list_display = ["name", "species", "personality", "gender", "birthday"]
    list_filter = ["personality", "species", "gender"]
    search_fields = ["name", "species"]
    readonly_fields = ["id"]
    ordering = ["name"]


class VillagerHuntInline(admin.TabularInline):
    model = VillagerHunt
    extra = 0
    show_change_link = True
    fields = ["date", "target_villager", "result_villager", "encounter_count"]
    readonly_fields = ["encounter_count"]
    autocomplete_fields = ["target_villager", "result_villager"]

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .annotate(_encounter_count=Count("encounters"))
            .select_related("target_villager", "result_villager")
        )

    @admin.display(description="Islands")
    def encounter_count(self, obj):
        return obj._encounter_count


class EncounterInline(admin.TabularInline):
    model = Encounter
    extra = 1
    fields = ["villager", "timestamp", "bonus_item", "recruited"]
    autocomplete_fields = ["villager"]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("villager")


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ["__str__", "island_name", "player_name", "hemisphere"]
    readonly_fields = ["id", "created_at", "updated_at"]
    autocomplete_fields = ["residents"]
    inlines = [VillagerHuntInline]


@admin.register(VillagerHunt)
class VillagerHuntAdmin(admin.ModelAdmin):
    list_display = ["__str__", "date", "encounter_count", "profile"]
    list_filter = ["profile", "date"]
    list_select_related = ["target_villager", "result_villager", "profile"]
    search_fields = ["target_villager__name", "result_villager__name"]
    readonly_fields = ["id", "created_at", "updated_at"]
    autocomplete_fields = ["target_villager", "result_villager"]
    inlines = [EncounterInline]

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .annotate(_encounter_count=Count("encounters"))
        )

    @admin.display(description="Islands Visited", ordering="_encounter_count")
    def encounter_count(self, obj):
        return obj._encounter_count


@admin.register(Encounter)
class EncounterAdmin(admin.ModelAdmin):
    list_display = ["villager", "timestamp", "recruited", "hunt"]
    list_filter = ["villager__personality", "villager__species", "recruited"]
    list_select_related = ["villager", "hunt__target_villager", "hunt__result_villager"]
    search_fields = ["villager__name", "villager__species", "notes"]
    readonly_fields = ["id", "created_at"]
    autocomplete_fields = ["hunt", "villager"]
