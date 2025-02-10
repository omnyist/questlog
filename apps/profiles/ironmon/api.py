from __future__ import annotations

from datetime import datetime

from django.db.models import Count
from django.db.models import Q
from ninja import Router
from ninja import Schema

from .models import Challenge
from .models import Checkpoint
from .models import CheckpointResult
from .models import Run

router = Router(tags=["IronMON"])


# Schemas
class CheckpointStatSchema(Schema):
    order: int
    name: str
    trainer: str
    attempts: int
    clears: int
    clear_rate: float


class StatsSchema(Schema):
    challenge: str
    total_runs: int
    victories: int
    victory_rate: float
    runs_with_results: int
    checkpoints: list[CheckpointStatSchema]


class RunSchema(Schema):
    seed_number: int
    challenge: str
    highest_checkpoint: str | None
    highest_checkpoint_order: int | None
    is_victory: bool
    started_at: datetime


class RunListSchema(Schema):
    runs: list[RunSchema]
    total: int


# Endpoints
@router.get("/ironmon/stats", response=StatsSchema)
def get_stats(request, challenge: str | None = None):
    """Aggregate stats: total seeds, victories, clear rates per checkpoint."""
    # Get challenge
    if challenge:
        ch = Challenge.objects.get(slug=challenge)
    else:
        ch = Challenge.objects.first()

    if not ch:
        return StatsSchema(
            challenge="",
            total_runs=0,
            victories=0,
            victory_rate=0,
            runs_with_results=0,
            checkpoints=[],
        )

    runs = Run.objects.filter(challenge=ch)
    total_runs = runs.count()
    victories = runs.filter(is_victory=True).count()
    runs_with_results = runs.filter(highest_checkpoint__isnull=False).count()

    # Checkpoint stats
    checkpoint_stats = []
    for cp in ch.checkpoints.all():
        results = cp.results.filter(run__challenge=ch)
        attempts = results.count()
        clears = results.filter(cleared=True).count()
        checkpoint_stats.append(
            CheckpointStatSchema(
                order=cp.order,
                name=cp.name,
                trainer=cp.trainer,
                attempts=attempts,
                clears=clears,
                clear_rate=clears / attempts if attempts > 0 else 0,
            )
        )

    return StatsSchema(
        challenge=ch.name,
        total_runs=total_runs,
        victories=victories,
        victory_rate=victories / total_runs if total_runs > 0 else 0,
        runs_with_results=runs_with_results,
        checkpoints=checkpoint_stats,
    )


@router.get("/ironmon/runs", response=RunListSchema)
def list_runs(request, challenge: str | None = None, limit: int = 50, offset: int = 0):
    """Recent runs with highest checkpoint reached."""
    runs = Run.objects.select_related("challenge", "highest_checkpoint")

    if challenge:
        runs = runs.filter(challenge__slug=challenge)

    total = runs.count()
    runs = runs[offset : offset + limit]

    return RunListSchema(
        runs=[
            RunSchema(
                seed_number=run.seed_number,
                challenge=run.challenge.name,
                highest_checkpoint=run.highest_checkpoint.name if run.highest_checkpoint else None,
                highest_checkpoint_order=run.highest_checkpoint.order if run.highest_checkpoint else None,
                is_victory=run.is_victory,
                started_at=run.started_at,
            )
            for run in runs
        ],
        total=total,
    )


@router.get("/ironmon/checkpoints/stats", response=list[CheckpointStatSchema])
def checkpoint_stats(request, challenge: str | None = None):
    """Clear rates per checkpoint - the 'wall' chart."""
    if challenge:
        ch = Challenge.objects.get(slug=challenge)
    else:
        ch = Challenge.objects.first()

    if not ch:
        return []

    stats = []
    for cp in ch.checkpoints.all():
        results = cp.results.filter(run__challenge=ch)
        attempts = results.count()
        clears = results.filter(cleared=True).count()
        stats.append(
            CheckpointStatSchema(
                order=cp.order,
                name=cp.name,
                trainer=cp.trainer,
                attempts=attempts,
                clears=clears,
                clear_rate=clears / attempts if attempts > 0 else 0,
            )
        )

    return stats
