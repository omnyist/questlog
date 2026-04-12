from __future__ import annotations

from datetime import datetime

from django.db.models import Count
from django.db.models import Min
from django.db.models import Q
from django.db.models import Sum
from ninja import Router
from ninja import Schema

from .models import Activity
from .models import AggregateStats
from .models import Character
from .models import Profile

router = Router(tags=["Destiny 2"])


# ---- Schemas ----


class CharacterSchema(Schema):
    id: str
    character_id: str
    character_class: str
    race: str
    gender: str
    light_level: int
    minutes_played: int
    date_last_played: datetime | None
    emblem_path: str
    emblem_background_path: str
    is_deleted: bool


class ProfileSchema(Schema):
    id: str
    bungie_name: str
    bungie_name_code: int | None
    membership_type: int
    membership_id: str
    last_synced: datetime | None
    characters: list[CharacterSchema]
    character_count: int
    activity_count: int


class AggregateStatsSchema(Schema):
    mode: str
    scope: str
    character_id: str | None
    activities_entered: int
    activities_won: int
    activities_cleared: int
    kills: int
    deaths: int
    assists: int
    precision_kills: int
    suicides: int
    best_single_game_kills: int
    longest_kill_spree: int
    longest_single_life: float
    orbs_dropped: int
    resurrections_performed: int
    resurrections_received: int
    seconds_played: int
    average_lifespan: float
    kd_ratio: float
    kda_ratio: float
    efficiency: float
    best_single_game_score: int
    fastest_completion: float
    longest_kill_distance: float
    total_kill_distance: float
    highest_light_level: int
    combat_rating: float


class ActivitySchema(Schema):
    instance_id: str
    activity_name: str
    mode_name: str
    mode_category: str
    period: datetime
    duration_seconds: int
    completed: bool
    standing: int | None
    kills: int
    deaths: int
    assists: int
    score: int
    team_score: int
    kd_ratio: float
    efficiency: float
    has_pgcr: bool
    character_class: str


class ActivityListSchema(Schema):
    total: int
    activities: list[ActivitySchema]


class CarnageEntrySchema(Schema):
    display_name: str
    character_class: str
    light_level: int
    is_self: bool
    kills: int
    deaths: int
    assists: int
    score: int
    completed: bool
    time_played_seconds: int


class ActivityDetailSchema(Schema):
    instance_id: str
    activity_name: str
    mode_name: str
    mode_category: str
    period: datetime
    duration_seconds: int
    completed: bool
    standing: int | None
    kills: int
    deaths: int
    assists: int
    score: int
    team_score: int
    kd_ratio: float
    efficiency: float
    character_class: str
    pgcr_entries: list[CarnageEntrySchema] | None


class RaidBreakdownSchema(Schema):
    activity_name: str
    attempts: int
    clears: int
    fastest_seconds: int | None


class RaidStatsSchema(Schema):
    total_attempts: int
    total_clears: int
    clear_rate: float
    total_kills: int
    total_deaths: int
    raids: list[RaidBreakdownSchema]


# ---- Helpers ----


def _character_schema(character: Character) -> CharacterSchema:
    return CharacterSchema(
        id=str(character.id),
        character_id=character.character_id,
        character_class=character.character_class,
        race=character.race,
        gender=character.gender,
        light_level=character.light_level,
        minutes_played=character.minutes_played,
        date_last_played=character.date_last_played,
        emblem_path=character.emblem_path,
        emblem_background_path=character.emblem_background_path,
        is_deleted=character.is_deleted,
    )


def _aggregate_schema(stat: AggregateStats) -> AggregateStatsSchema:
    return AggregateStatsSchema(
        mode=stat.mode,
        scope=stat.scope,
        character_id=stat.character.character_id if stat.character else None,
        activities_entered=stat.activities_entered,
        activities_won=stat.activities_won,
        activities_cleared=stat.activities_cleared,
        kills=stat.kills,
        deaths=stat.deaths,
        assists=stat.assists,
        precision_kills=stat.precision_kills,
        suicides=stat.suicides,
        best_single_game_kills=stat.best_single_game_kills,
        longest_kill_spree=stat.longest_kill_spree,
        longest_single_life=stat.longest_single_life,
        orbs_dropped=stat.orbs_dropped,
        resurrections_performed=stat.resurrections_performed,
        resurrections_received=stat.resurrections_received,
        seconds_played=stat.seconds_played,
        average_lifespan=stat.average_lifespan,
        kd_ratio=stat.kd_ratio,
        kda_ratio=stat.kda_ratio,
        efficiency=stat.efficiency,
        best_single_game_score=stat.best_single_game_score,
        fastest_completion=stat.fastest_completion,
        longest_kill_distance=stat.longest_kill_distance,
        total_kill_distance=stat.total_kill_distance,
        highest_light_level=stat.highest_light_level,
        combat_rating=stat.combat_rating,
    )


def _activity_schema(activity: Activity, has_pgcr: bool) -> ActivitySchema:
    return ActivitySchema(
        instance_id=activity.instance_id,
        activity_name=activity.activity_name,
        mode_name=activity.mode_name,
        mode_category=activity.mode_category,
        period=activity.period,
        duration_seconds=activity.duration_seconds,
        completed=activity.completed,
        standing=activity.standing,
        kills=activity.kills,
        deaths=activity.deaths,
        assists=activity.assists,
        score=activity.score,
        team_score=activity.team_score,
        kd_ratio=activity.kd_ratio,
        efficiency=activity.efficiency,
        has_pgcr=has_pgcr,
        character_class=activity.character.character_class if activity.character_id else "",
    )


# ---- Endpoints ----


@router.get("/destiny/profile", response={200: ProfileSchema, 404: dict})
def get_profile(request):
    """Overview of the archived Destiny 2 profile and its characters."""
    profile = Profile.objects.prefetch_related("characters").first()
    if not profile:
        return 404, {"error": "No Destiny 2 profile archived"}

    activity_count = Activity.objects.filter(profile=profile).count()
    characters = list(profile.characters.all())

    return 200, ProfileSchema(
        id=str(profile.id),
        bungie_name=profile.bungie_name,
        bungie_name_code=profile.bungie_name_code,
        membership_type=profile.membership_type,
        membership_id=profile.membership_id,
        last_synced=profile.last_synced,
        characters=[_character_schema(c) for c in characters],
        character_count=len(characters),
        activity_count=activity_count,
    )


@router.get("/destiny/characters", response=list[CharacterSchema])
def list_characters(request):
    """All archived guardians."""
    return [_character_schema(c) for c in Character.objects.all()]


@router.get("/destiny/stats", response=list[AggregateStatsSchema])
def list_stats(
    request,
    scope: str | None = None,
    mode: str | None = None,
    character_id: str | None = None,
):
    """Aggregate stats across all modes, filterable by scope/mode/character."""
    qs = AggregateStats.objects.select_related("character")
    if scope:
        qs = qs.filter(scope=scope)
    if mode:
        qs = qs.filter(mode=mode)
    if character_id:
        qs = qs.filter(character__character_id=character_id)
    return [_aggregate_schema(s) for s in qs]


@router.get("/destiny/stats/{mode}", response=list[AggregateStatsSchema])
def get_stats_by_mode(request, mode: str):
    """All aggregate stat rows for a single mode (account + per-character)."""
    qs = AggregateStats.objects.filter(mode=mode).select_related("character")
    return [_aggregate_schema(s) for s in qs]


@router.get("/destiny/activities", response=ActivityListSchema)
def list_activities(
    request,
    mode_category: str | None = None,
    character_id: str | None = None,
    completed: bool | None = None,
    limit: int = 50,
    offset: int = 0,
):
    """Paginated activity history, newest first. Filterable."""
    qs = Activity.objects.select_related("character").prefetch_related("carnage_report")
    if mode_category:
        qs = qs.filter(mode_category=mode_category)
    if character_id:
        qs = qs.filter(character__character_id=character_id)
    if completed is not None:
        qs = qs.filter(completed=completed)

    total = qs.count()
    limit = max(1, min(limit, 500))
    offset = max(0, offset)
    page = qs[offset : offset + limit]

    return ActivityListSchema(
        total=total,
        activities=[
            _activity_schema(a, has_pgcr=hasattr(a, "carnage_report") and a.carnage_report is not None)
            for a in page
        ],
    )


@router.get("/destiny/activities/{instance_id}", response={200: ActivityDetailSchema, 404: dict})
def get_activity(request, instance_id: str):
    """Single activity, with PGCR entries if available."""
    try:
        activity = (
            Activity.objects.select_related("character")
            .prefetch_related("carnage_report__entries")
            .get(instance_id=instance_id)
        )
    except Activity.DoesNotExist:
        return 404, {"error": "Activity not found"}

    pgcr_entries: list[CarnageEntrySchema] | None = None
    if hasattr(activity, "carnage_report") and activity.carnage_report:
        pgcr_entries = [
            CarnageEntrySchema(
                display_name=e.display_name,
                character_class=e.character_class,
                light_level=e.light_level,
                is_self=e.is_self,
                kills=e.kills,
                deaths=e.deaths,
                assists=e.assists,
                score=e.score,
                completed=e.completed,
                time_played_seconds=e.time_played_seconds,
            )
            for e in activity.carnage_report.entries.all()
        ]

    return 200, ActivityDetailSchema(
        instance_id=activity.instance_id,
        activity_name=activity.activity_name,
        mode_name=activity.mode_name,
        mode_category=activity.mode_category,
        period=activity.period,
        duration_seconds=activity.duration_seconds,
        completed=activity.completed,
        standing=activity.standing,
        kills=activity.kills,
        deaths=activity.deaths,
        assists=activity.assists,
        score=activity.score,
        team_score=activity.team_score,
        kd_ratio=activity.kd_ratio,
        efficiency=activity.efficiency,
        character_class=activity.character.character_class if activity.character_id else "",
        pgcr_entries=pgcr_entries,
    )


@router.get("/destiny/raids/stats", response=RaidStatsSchema)
def get_raid_stats(request):
    """Raid-specific breakdown: attempts, clears, fastest, per-raid stats."""
    raids_qs = Activity.objects.filter(mode_category="raid")
    total_attempts = raids_qs.count()
    total_clears = raids_qs.filter(completed=True).count()
    total_kills = raids_qs.aggregate(k=Sum("kills"))["k"] or 0
    total_deaths = raids_qs.aggregate(d=Sum("deaths"))["d"] or 0

    breakdown_qs = (
        raids_qs.values("activity_name")
        .annotate(
            attempts=Count("id"),
            clears=Count("id", filter=Q(completed=True)),
            fastest=Min("duration_seconds", filter=Q(completed=True)),
        )
        .order_by("-attempts")
    )
    raids = [
        RaidBreakdownSchema(
            activity_name=row["activity_name"] or "Unknown",
            attempts=row["attempts"],
            clears=row["clears"],
            fastest_seconds=row["fastest"] if row["fastest"] else None,
        )
        for row in breakdown_qs
    ]

    clear_rate = (total_clears / total_attempts) if total_attempts else 0.0

    return RaidStatsSchema(
        total_attempts=total_attempts,
        total_clears=total_clears,
        clear_rate=round(clear_rate, 3),
        total_kills=total_kills,
        total_deaths=total_deaths,
        raids=raids,
    )
