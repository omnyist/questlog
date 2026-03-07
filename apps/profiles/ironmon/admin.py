from __future__ import annotations

from django.contrib import admin
from django.db.models import Count
from django.db.models import Q

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
    list_select_related = ["edition"]
    prepopulated_fields = {"slug": ("name",)}
    inlines = [CheckpointInline]

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .annotate(
                _run_count=Count("runs", distinct=True),
                _checkpoint_count=Count("checkpoints", distinct=True),
            )
        )

    @admin.display(description="Runs", ordering="_run_count")
    def run_count(self, obj):
        return obj._run_count

    @admin.display(description="Checkpoints", ordering="_checkpoint_count")
    def checkpoint_count(self, obj):
        return obj._checkpoint_count


@admin.register(Checkpoint)
class CheckpointAdmin(admin.ModelAdmin):
    list_display = ["order", "name", "trainer", "challenge", "clear_rate"]
    list_filter = ["challenge"]
    list_select_related = ["challenge"]
    ordering = ["challenge", "order"]

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .annotate(
                _total_results=Count("results"),
                _cleared_results=Count("results", filter=Q(results__cleared=True)),
            )
        )

    @admin.display(description="Clear Rate")
    def clear_rate(self, obj):
        if obj._total_results == 0:
            return "—"
        rate = 100 * obj._cleared_results / obj._total_results
        return f"{obj._cleared_results}/{obj._total_results} ({rate:.1f}%)"


@admin.register(Run)
class RunAdmin(admin.ModelAdmin):
    list_display = ["seed_number", "challenge", "highest_checkpoint", "is_victory", "started_at"]
    list_filter = ["challenge", "is_victory"]
    list_select_related = ["challenge", "highest_checkpoint"]
    search_fields = ["seed_number"]
    readonly_fields = ["seed_number", "started_at"]
    inlines = [CheckpointResultInline]


@admin.register(CheckpointResult)
class CheckpointResultAdmin(admin.ModelAdmin):
    list_display = ["run", "checkpoint", "cleared", "timestamp"]
    list_filter = ["cleared", "checkpoint__challenge", "checkpoint"]
    list_select_related = ["run__highest_checkpoint", "checkpoint"]
    search_fields = ["run__seed_number"]
    readonly_fields = ["timestamp"]
