from __future__ import annotations

from django.contrib import admin

from .models import Challenge
from .models import Checkpoint
from .models import CheckpointResult
from .models import Run


class CheckpointInline(admin.TabularInline):
    model = Checkpoint
    extra = 0
    fields = ["order", "name", "trainer"]
    ordering = ["order"]


class CheckpointResultInline(admin.TabularInline):
    model = CheckpointResult
    extra = 0
    fields = ["checkpoint", "cleared", "timestamp"]
    readonly_fields = ["timestamp"]
    ordering = ["checkpoint__order"]


@admin.register(Challenge)
class ChallengeAdmin(admin.ModelAdmin):
    list_display = ["name", "edition", "run_count", "checkpoint_count"]
    prepopulated_fields = {"slug": ("name",)}
    inlines = [CheckpointInline]

    @admin.display(description="Runs")
    def run_count(self, obj):
        return obj.runs.count()

    @admin.display(description="Checkpoints")
    def checkpoint_count(self, obj):
        return obj.checkpoints.count()


@admin.register(Checkpoint)
class CheckpointAdmin(admin.ModelAdmin):
    list_display = ["order", "name", "trainer", "challenge", "clear_rate"]
    list_filter = ["challenge"]
    ordering = ["challenge", "order"]

    @admin.display(description="Clear Rate")
    def clear_rate(self, obj):
        total = obj.results.count()
        if total == 0:
            return "—"
        cleared = obj.results.filter(cleared=True).count()
        return f"{cleared}/{total} ({100 * cleared / total:.1f}%)"


@admin.register(Run)
class RunAdmin(admin.ModelAdmin):
    list_display = ["seed_number", "challenge", "highest_checkpoint", "is_victory", "started_at"]
    list_filter = ["challenge", "is_victory"]
    search_fields = ["seed_number"]
    readonly_fields = ["seed_number", "started_at"]
    inlines = [CheckpointResultInline]


@admin.register(CheckpointResult)
class CheckpointResultAdmin(admin.ModelAdmin):
    list_display = ["run", "checkpoint", "cleared", "timestamp"]
    list_filter = ["cleared", "checkpoint__challenge", "checkpoint"]
    search_fields = ["run__seed_number"]
    readonly_fields = ["timestamp"]
