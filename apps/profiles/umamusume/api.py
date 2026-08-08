from __future__ import annotations

from datetime import datetime
from uuid import UUID

from django.db.models import Count
from django.db.models import F
from django.db.models import Max
from django.db.models import Min
from django.db.models import Q
from django.shortcuts import get_object_or_404
from ninja import Router
from ninja import Schema
from ninja import Status
from ninja.pagination import paginate

from .models import CareerRun
from .models import Character
from .models import Outfit

router = Router(tags=["Umamusume"])


# ---- Schemas ----


class RunSchema(Schema):
    id: UUID
    character: str
    character_slug: str
    outfit_title: str
    run_date: datetime
    platform: str
    rank: str
    rating: int | None
    earned_title: str
    speed: int | None
    stamina: int | None
    power: int | None
    guts: int | None
    wit: int | None
    fans: int | None
    races: int | None
    wins: int | None
    is_perfect: bool
    aptitudes: dict
    major_wins: list[str]
    support_cards: list[str]

    @staticmethod
    def resolve_character(obj) -> str:
        return obj.outfit.character.name

    @staticmethod
    def resolve_character_slug(obj) -> str:
        return obj.outfit.character.slug

    @staticmethod
    def resolve_outfit_title(obj) -> str:
        return obj.outfit.title


class OutfitSchema(Schema):
    title: str
    slug: str
    run_count: int
    best_rating: int | None


class HallOfFameSchema(Schema):
    """A character's enshrined entry — their single best run, plus context."""

    name: str
    slug: str
    run_count: int
    outfit_count: int
    best_rating: int | None
    best_rank: str
    best_run_date: datetime | None
    perfect_runs: int


class CharacterDetailSchema(Schema):
    name: str
    slug: str
    outfits: list[OutfitSchema]
    runs: list[RunSchema]


class StatsSchema(Schema):
    characters: int
    outfits: int
    runs: int
    perfect_runs: int
    best_rating: int | None
    total_races: int
    total_wins: int
    first_run: datetime | None
    latest_run: datetime | None


def _runs_qs():
    return CareerRun.objects.select_related("outfit__character")


# ---- Endpoints ----


@router.get("/umamusume/halloffame", response=list[HallOfFameSchema])
def hall_of_fame(request, limit: int = 100):
    """Best run per character, ranked — the Hall of Fame.

    One entry per character rather than per outfit, so every El Condor Pasa run
    competes for the same slot regardless of which version was trained.
    """
    characters = (
        Character.objects.annotate(
            run_count=Count("outfits__runs", distinct=True),
            outfit_count=Count("outfits", distinct=True),
            best_rating=Max("outfits__runs__rating"),
        )
        .filter(best_rating__isnull=False)
        .order_by("-best_rating")[: max(1, min(limit, 500))]
    )

    entries = []
    for character in characters:
        best = (
            _runs_qs()
            .filter(outfit__character=character, rating=character.best_rating)
            .first()
        )
        perfect = sum(
            1
            for r in CareerRun.objects.filter(outfit__character=character)
            if r.is_perfect
        )
        entries.append(
            HallOfFameSchema(
                name=character.name,
                slug=character.slug,
                run_count=character.run_count,
                outfit_count=character.outfit_count,
                best_rating=character.best_rating,
                best_rank=best.rank if best else "",
                best_run_date=best.run_date if best else None,
                perfect_runs=perfect,
            )
        )
    return entries


@router.get("/umamusume/characters/{slug}", response={200: CharacterDetailSchema, 404: dict})
def character_detail(request, slug: str):
    """One character with every outfit and every run, newest first."""
    character = get_object_or_404(Character, slug=slug)
    outfits = [
        OutfitSchema(
            title=o.title,
            slug=o.slug,
            run_count=o.run_count,
            best_rating=o.best_rating,
        )
        for o in character.outfits.annotate(
            run_count=Count("runs"), best_rating=Max("runs__rating")
        )
    ]
    runs = list(_runs_qs().filter(outfit__character=character))
    return Status(200, CharacterDetailSchema(name=character.name, slug=character.slug, outfits=outfits, runs=runs))


@router.get("/umamusume/runs", response=list[RunSchema])
@paginate
def list_runs(
    request,
    character: str | None = None,
    platform: str | None = None,
    rank: str | None = None,
    perfect_only: bool = False,
    min_rating: int | None = None,
):
    """All career runs, newest first."""
    qs = _runs_qs()
    if character:
        qs = qs.filter(
            Q(outfit__character__slug=character) | Q(outfit__character__name__iexact=character)
        )
    if platform:
        qs = qs.filter(platform=platform)
    if rank:
        qs = qs.filter(rank=rank)
    if min_rating is not None:
        qs = qs.filter(rating__gte=min_rating)
    if perfect_only:
        qs = qs.filter(races__isnull=False, races__gt=0).filter(races=F("wins"))
    return qs


@router.get("/umamusume/stats", response=StatsSchema)
def stats(request):
    """Aggregate totals across the whole archive."""
    runs = CareerRun.objects.all()
    agg = runs.aggregate(
        best=Max("rating"), first=Min("run_date"), latest=Max("run_date")
    )
    return StatsSchema(
        characters=Character.objects.count(),
        outfits=Outfit.objects.count(),
        runs=runs.count(),
        perfect_runs=sum(1 for r in runs if r.is_perfect),
        best_rating=agg["best"],
        total_races=sum(r.races or 0 for r in runs),
        total_wins=sum(r.wins or 0 for r in runs),
        first_run=agg["first"],
        latest_run=agg["latest"],
    )
