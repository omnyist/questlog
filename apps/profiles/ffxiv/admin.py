from __future__ import annotations

from django.contrib import admin

from .models import Character
from .models import Profile


class CharacterInline(admin.TabularInline):
    model = Character
    extra = 1


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ["__str__", "lodestone_id", "last_synced"]
    readonly_fields = ["id", "created_at", "updated_at", "last_synced"]
    inlines = [CharacterInline]


@admin.register(Character)
class CharacterAdmin(admin.ModelAdmin):
    list_display = ["name", "server", "profile"]
    search_fields = ["name", "server"]
    readonly_fields = ["id", "created_at", "updated_at"]
