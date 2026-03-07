from __future__ import annotations

from datetime import datetime

from django.db.models import Count
from django.db.models import Q
from ninja import Router
from ninja import Schema

from config.auth import ApiKeyAuth

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
    entered: int
    survived: int
    survival_rate: float


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


# Helpers
def _resolve_challenge(slug: str | None) -> Challenge | None:
    """Look up a challenge by slug, or fall back to the first one."""
    if slug:
        try:
            return Challenge.objects.get(slug=slug)
        except Challenge.DoesNotExist:
            return None
    return Challenge.objects.first()


def _compute_checkpoint_stats(
    challenge: Challenge, total_runs: int
) -> list[CheckpointStatSchema]:
    """Compute entered/survived/survival_rate for all checkpoints in one query.

    "entered" = runs that entered this stage (cleared the previous checkpoint,
    or all runs for the first checkpoint).
    "survived" = runs that cleared this checkpoint.
    """
    checkpoints = (
        Checkpoint.objects.filter(challenge=challenge)
        .annotate(
            survived=Count(
                "results",
                filter=Q(results__run__challenge=challenge, results__cleared=True),
            )
        )
        .order_by("order")
    )
    stats = []
    prev_survived = total_runs
    for cp in checkpoints:
        entered = prev_survived
        stats.append(
            CheckpointStatSchema(
                order=cp.order,
                name=cp.name,
                trainer=cp.trainer,
                entered=entered,
                survived=cp.survived,
                survival_rate=cp.survived / entered if entered > 0 else 0,
            )
        )
        prev_survived = cp.survived
    return stats


# Endpoints
@router.get("/ironmon/stats", response={200: StatsSchema, 404: dict})
def get_stats(request, challenge: str | None = None):
    """Aggregate stats: total seeds, victories, clear rates per checkpoint."""
    ch = _resolve_challenge(challenge)

    if not ch:
        if challenge:
            return 404, {"detail": f"Challenge '{challenge}' not found"}
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

    return StatsSchema(
        challenge=ch.name,
        total_runs=total_runs,
        victories=victories,
        victory_rate=victories / total_runs if total_runs > 0 else 0,
        runs_with_results=runs_with_results,
        checkpoints=_compute_checkpoint_stats(ch, total_runs),
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


@router.get("/ironmon/checkpoints/stats", response={200: list[CheckpointStatSchema], 404: dict})
def checkpoint_stats(request, challenge: str | None = None):
    """Clear rates per checkpoint - the 'wall' chart."""
    ch = _resolve_challenge(challenge)

    if not ch:
        if challenge:
            return 404, {"detail": f"Challenge '{challenge}' not found"}
        return []

    total_runs = Run.objects.filter(challenge=ch).count()
    return _compute_checkpoint_stats(ch, total_runs)


# --- Read endpoint for challenge details ---


class CheckpointDetailSchema(Schema):
    id: int
    name: str
    trainer: str
    order: int


class ChallengeDetailSchema(Schema):
    id: int
    slug: str
    name: str
    checkpoints: list[CheckpointDetailSchema]


@router.get("/ironmon/challenges/{slug}", response={200: ChallengeDetailSchema, 404: dict})
def get_challenge(request, slug: str):
    """Challenge with its checkpoints, used by Synthfunc on service start."""
    try:
        ch = Challenge.objects.get(slug=slug)
    except Challenge.DoesNotExist:
        return 404, {"detail": "Challenge not found"}
    return ChallengeDetailSchema(
        id=ch.id,
        slug=ch.slug,
        name=ch.name,
        checkpoints=[
            CheckpointDetailSchema(
                id=cp.id,
                name=cp.name,
                trainer=cp.trainer,
                order=cp.order,
            )
            for cp in ch.checkpoints.all()
        ],
    )


# --- Write endpoints (auth required) ---


class CreateRunSchema(Schema):
    seed_number: int
    challenge_slug: str


class RunResponseSchema(Schema):
    seed_number: int
    challenge: str
    created: bool


@router.post("/ironmon/runs", response={200: RunResponseSchema, 404: dict}, auth=ApiKeyAuth())
def create_run(request, payload: CreateRunSchema):
    """Create or get a run. Idempotent by seed_number."""
    try:
        ch = Challenge.objects.get(slug=payload.challenge_slug)
    except Challenge.DoesNotExist:
        return 404, {"detail": f"Challenge '{payload.challenge_slug}' not found"}
    run, created = Run.objects.get_or_create(
        seed_number=payload.seed_number,
        defaults={"challenge": ch},
    )
    return RunResponseSchema(
        seed_number=run.seed_number,
        challenge=ch.name,
        created=created,
    )


class RecordCheckpointSchema(Schema):
    checkpoint_name: str


class CheckpointResultResponseSchema(Schema):
    seed_number: int
    checkpoint: str
    checkpoint_order: int
    cleared: bool
    created: bool


@router.post(
    "/ironmon/runs/{seed_number}/results",
    response={200: CheckpointResultResponseSchema, 404: dict},
    auth=ApiKeyAuth(),
)
def record_checkpoint(request, seed_number: int, payload: RecordCheckpointSchema):
    """Record a checkpoint clear for a run. Updates highest_checkpoint."""
    try:
        run = Run.objects.select_related("challenge", "highest_checkpoint").get(
            seed_number=seed_number,
        )
    except Run.DoesNotExist:
        return 404, {"detail": f"Run {seed_number} not found"}
    try:
        checkpoint = Checkpoint.objects.get(
            challenge=run.challenge,
            name=payload.checkpoint_name,
        )
    except Checkpoint.DoesNotExist:
        return 404, {"detail": f"Checkpoint '{payload.checkpoint_name}' not found"}
    result, created = CheckpointResult.objects.get_or_create(
        run=run,
        checkpoint=checkpoint,
        defaults={"cleared": True},
    )

    # Update denormalized highest_checkpoint if this one is further
    if run.highest_checkpoint is None or checkpoint.order > run.highest_checkpoint.order:
        run.highest_checkpoint = checkpoint
        run.save(update_fields=["highest_checkpoint"])

    return CheckpointResultResponseSchema(
        seed_number=run.seed_number,
        checkpoint=checkpoint.name,
        checkpoint_order=checkpoint.order,
        cleared=result.cleared,
        created=created,
    )
