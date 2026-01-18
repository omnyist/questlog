from __future__ import annotations

from django.contrib import admin

from .models import Horse
from .models import Profile


class HorseInline(admin.TabularInline):
    model = Horse
    extra = 1


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ["__str__", "horse_count"]
    readonly_fields = ["id", "created_at", "updated_at"]
    inlines = [HorseInline]

    @admin.display(description="Horses")
    def horse_count(self, obj):
        return obj.horses.count()


@admin.register(Horse)
class HorseAdmin(admin.ModelAdmin):
    list_display = ["name", "profile"]
    search_fields = ["name"]
    readonly_fields = ["id", "created_at", "updated_at"]
