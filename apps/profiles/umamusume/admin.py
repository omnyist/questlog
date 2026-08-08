from __future__ import annotations

from django.contrib import admin

from .models import CareerRun
from .models import Character
from .models import Outfit
from .models import Profile


class OutfitInline(admin.TabularInline):
    model = Outfit
    extra = 0
    prepopulated_fields = {"slug": ("title",)}


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ["__str__", "character_count"]
    readonly_fields = ["id", "created_at", "updated_at"]

    @admin.display(description="Characters")
    def character_count(self, obj):
        return obj.characters.count()


@admin.register(Character)
class CharacterAdmin(admin.ModelAdmin):
    list_display = ["name", "outfit_count", "run_count", "best_rating"]
    search_fields = ["name"]
    prepopulated_fields = {"slug": ("name",)}
    readonly_fields = ["id", "created_at", "updated_at"]
    inlines = [OutfitInline]

    @admin.display(description="Outfits")
    def outfit_count(self, obj):
        return obj.outfits.count()

    @admin.display(description="Runs")
    def run_count(self, obj):
        return CareerRun.objects.filter(outfit__character=obj).count()

    @admin.display(description="Best rating")
    def best_rating(self, obj):
        best = (
            CareerRun.objects.filter(outfit__character=obj)
            .order_by("-rating")
            .values_list("rating", flat=True)
            .first()
        )
        return best or "—"


@admin.register(Outfit)
class OutfitAdmin(admin.ModelAdmin):
    list_display = ["__str__", "character", "run_count"]
    list_filter = ["character"]
    search_fields = ["title", "character__name"]
    prepopulated_fields = {"slug": ("title",)}
    readonly_fields = ["id", "created_at", "updated_at"]

    @admin.display(description="Runs")
    def run_count(self, obj):
        return obj.runs.count()


@admin.register(CareerRun)
class CareerRunAdmin(admin.ModelAdmin):
    list_display = ["outfit", "rank", "rating", "races", "wins", "run_date", "platform"]
    list_filter = ["platform", "rank", "outfit__character"]
    search_fields = ["outfit__title", "outfit__character__name", "earned_title"]
    date_hierarchy = "run_date"
    readonly_fields = ["id", "fingerprint", "created_at", "updated_at"]
