from __future__ import annotations

from django.contrib import admin

from .models import Profile


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ["__str__", "bungie_id", "last_synced"]
    readonly_fields = ["id", "created_at", "updated_at", "last_synced"]
