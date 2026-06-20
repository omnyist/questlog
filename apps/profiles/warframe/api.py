from __future__ import annotations

from datetime import datetime

from django.db.models import Avg
from django.db.models import Count
from django.db.models import Sum
from ninja import Router
from ninja import Schema
from ninja import Status

from .models import Affiliation
from .models import CatalogItem
from .models import MissionStat
from .models import Profile
from .models import Snapshot
from .models import WeaponStat

router = Router(tags=["Warframe"])


# ---- Schemas ----


class ProfileSchema(Schema):
    id: str
    display_name: str
    account_id: str
    platform: str
    wf_created_at: datetime | None
    mastery_rank: int
    player_level: int
    title: str
    missions_completed: int
    missions_quit: int
    missions_failed: int
    missions_interrupted: int
    missions_dumped: int
    time_played_seconds: int
    pickup_count: int
    daily_focus: int
    migrated_to_console: bool
    last_synced: datetime | None
    weapons_tracked: int
    total_weapon_kills: int


class WeaponSchema(Schema):
    weapon_path: str
    weapon_name: str
    fired: int
    hits: int
    kills: int
    headshots: int
    assists: int
    equip_time_seconds: float
    xp: int
    accuracy: float
    headshot_rate: float


class WeaponListSchema(Schema):
    total: int
    weapons: list[WeaponSchema]


class MissionSchema(Schema):
    node_tag: str
    completes: int


class AffiliationSchema(Schema):
    syndicate_tag: str
    standing: int
    title_rank: int


class SnapshotSchema(Schema):
    id: str
    captured_at: datetime
    trigger: str
    mastery_rank: int
    time_played_seconds: int
    missions_completed: int
    pickup_count: int
    total_weapon_kills: int
    weapons_tracked: int


class StatsSchema(Schema):
    mastery_rank: int
    time_played_seconds: int
    time_played_hours: float
    missions_completed: int
    missions_failed: int
    missions_quit: int
    total_weapon_kills: int
    total_weapon_fired: int
    total_weapon_hits: int
    total_headshots: int
    overall_accuracy: float
    overall_headshot_rate: float
    weapons_tracked: int
    nodes_played: int
    syndicates_joined: int
    snapshots_captured: int


# ---- Helpers ----


def _weapon_schema(w: WeaponStat) -> WeaponSchema:
    return WeaponSchema(
        weapon_path=w.weapon_path,
        weapon_name=w.weapon_name,
        fired=w.fired,
        hits=w.hits,
        kills=w.kills,
        headshots=w.headshots,
        assists=w.assists,
        equip_time_seconds=w.equip_time_seconds,
        xp=w.xp,
        accuracy=w.accuracy,
        headshot_rate=w.headshot_rate,
    )


SORT_FIELDS = {
    "kills": "-kills",
    "fired": "-fired",
    "hits": "-hits",
    "equip_time": "-equip_time_seconds",
    "accuracy": "-accuracy",
    "xp": "-xp",
    "headshots": "-headshots",
}


# ---- Endpoints ----


@router.get("/warframe/profile", response={200: ProfileSchema, 404: dict})
def get_profile(request):
    """Warframe profile overview with cumulative totals."""
    profile = Profile.objects.first()
    if not profile:
        return Status(404, {"error": "No Warframe profile archived"})

    weapon_aggregate = profile.weapons.aggregate(
        count=Count("id"),
        total_kills=Sum("kills"),
    )

    return Status(200, ProfileSchema(
        id=str(profile.id),
        display_name=profile.display_name,
        account_id=profile.account_id,
        platform=profile.platform,
        wf_created_at=profile.wf_created_at,
        mastery_rank=profile.mastery_rank,
        player_level=profile.player_level,
        title=profile.title,
        missions_completed=profile.missions_completed,
        missions_quit=profile.missions_quit,
        missions_failed=profile.missions_failed,
        missions_interrupted=profile.missions_interrupted,
        missions_dumped=profile.missions_dumped,
        time_played_seconds=profile.time_played_seconds,
        pickup_count=profile.pickup_count,
        daily_focus=profile.daily_focus,
        migrated_to_console=profile.migrated_to_console,
        last_synced=profile.last_synced,
        weapons_tracked=weapon_aggregate["count"] or 0,
        total_weapon_kills=weapon_aggregate["total_kills"] or 0,
    ))


@router.get("/warframe/weapons", response=WeaponListSchema)
def list_weapons(
    request,
    sort: str = "kills",
    limit: int = 50,
    offset: int = 0,
    min_kills: int = 0,
):
    """Paginated weapons list. Sort by kills/fired/hits/equip_time/accuracy/xp/headshots."""
    order = SORT_FIELDS.get(sort, "-kills")
    qs = WeaponStat.objects.filter(kills__gte=min_kills)
    total = qs.count()

    limit = max(1, min(limit, 500))
    offset = max(0, offset)
    page = qs.order_by(order)[offset : offset + limit]

    return WeaponListSchema(
        total=total,
        weapons=[_weapon_schema(w) for w in page],
    )


@router.get("/warframe/weapons/top", response=list[WeaponSchema])
def top_weapons(request, by: str = "kills", limit: int = 10):
    """Top N weapons by a given metric."""
    order = SORT_FIELDS.get(by, "-kills")
    limit = max(1, min(limit, 100))
    return [_weapon_schema(w) for w in WeaponStat.objects.order_by(order)[:limit]]


@router.get("/warframe/missions", response=list[MissionSchema])
def list_missions(request, limit: int = 200):
    """Per-node completion counts, most played first."""
    limit = max(1, min(limit, 1000))
    return [
        MissionSchema(node_tag=m.node_tag, completes=m.completes)
        for m in MissionStat.objects.order_by("-completes")[:limit]
    ]


@router.get("/warframe/affiliations", response=list[AffiliationSchema])
def list_affiliations(request):
    """All syndicate standings."""
    return [
        AffiliationSchema(
            syndicate_tag=a.syndicate_tag,
            standing=a.standing,
            title_rank=a.title_rank,
        )
        for a in Affiliation.objects.order_by("syndicate_tag")
    ]


@router.get("/warframe/snapshots", response=list[SnapshotSchema])
def list_snapshots(request, limit: int = 50):
    """Progression snapshots, newest first."""
    limit = max(1, min(limit, 500))
    return [
        SnapshotSchema(
            id=str(s.id),
            captured_at=s.captured_at,
            trigger=s.trigger,
            mastery_rank=s.mastery_rank,
            time_played_seconds=s.time_played_seconds,
            missions_completed=s.missions_completed,
            pickup_count=s.pickup_count,
            total_weapon_kills=s.total_weapon_kills,
            weapons_tracked=s.weapons_tracked,
        )
        for s in Snapshot.objects.order_by("-captured_at")[:limit]
    ]


@router.get("/warframe/stats", response={200: StatsSchema, 404: dict})
def get_stats(request):
    """Aggregate derived stats across the archive."""
    profile = Profile.objects.first()
    if not profile:
        return Status(404, {"error": "No Warframe profile archived"})

    weapon_agg = profile.weapons.aggregate(
        count=Count("id"),
        total_kills=Sum("kills"),
        total_fired=Sum("fired"),
        total_hits=Sum("hits"),
        total_headshots=Sum("headshots"),
        avg_accuracy=Avg("accuracy"),
        avg_headshot_rate=Avg("headshot_rate"),
    )

    total_kills = weapon_agg["total_kills"] or 0
    total_fired = weapon_agg["total_fired"] or 0
    total_hits = weapon_agg["total_hits"] or 0
    total_headshots = weapon_agg["total_headshots"] or 0

    return Status(200, StatsSchema(
        mastery_rank=profile.mastery_rank,
        time_played_seconds=profile.time_played_seconds,
        time_played_hours=round(profile.time_played_seconds / 3600, 1),
        missions_completed=profile.missions_completed,
        missions_failed=profile.missions_failed,
        missions_quit=profile.missions_quit,
        total_weapon_kills=total_kills,
        total_weapon_fired=total_fired,
        total_weapon_hits=total_hits,
        total_headshots=total_headshots,
        overall_accuracy=round((total_hits / total_fired) if total_fired else 0, 4),
        overall_headshot_rate=round((total_headshots / total_kills) if total_kills else 0, 4),
        weapons_tracked=weapon_agg["count"] or 0,
        nodes_played=profile.missions.count(),
        syndicates_joined=profile.affiliations.count(),
        snapshots_captured=profile.snapshots.count(),
    ))


# ---- Mastery rank progression ----


class MasteryPointSchema(Schema):
    date: datetime
    mastery_rank: int


class MasterySchema(Schema):
    current_rank: int
    history: list[MasteryPointSchema]


@router.get("/warframe/mastery", response={200: MasterySchema, 404: dict})
def get_mastery(request, granularity: str = "changes"):
    """Current mastery rank plus progression over time from snapshots.

    granularity=changes (default) returns one point per rank increase plus the
    latest snapshot; granularity=all returns every snapshot.
    """
    profile = Profile.objects.first()
    if not profile:
        return Status(404, {"error": "No Warframe profile archived"})

    snapshots = list(
        profile.snapshots.order_by("captured_at").values_list(
            "captured_at", "mastery_rank"
        )
    )

    points: list[MasteryPointSchema] = []
    if granularity == "all":
        points = [
            MasteryPointSchema(date=ts, mastery_rank=rank) for ts, rank in snapshots
        ]
    else:
        last_rank = None
        for ts, rank in snapshots:
            if rank != last_rank:
                points.append(MasteryPointSchema(date=ts, mastery_rank=rank))
                last_rank = rank
        # Always include the most recent snapshot so the series ends at "now".
        if snapshots:
            ts, rank = snapshots[-1]
            if not points or points[-1].date != ts:
                points.append(MasteryPointSchema(date=ts, mastery_rank=rank))

    return Status(200, MasterySchema(current_rank=profile.mastery_rank, history=points))


# ---- Mastery completion ----

# Affinity to reach a rank R = MULT * R^2. Weapons use 500, frames/companions 1000.
MASTERY_MULT = {
    "Warframes": 1000,
    "Archwing": 1000,
    "Sentinels": 1000,
    "Pets": 1000,
    "Primary": 500,
    "Secondary": 500,
    "Melee": 500,
    "Arch-Gun": 500,
    "Arch-Melee": 500,
    "SentinelWeapons": 500,
}
DEFAULT_MULT = 500


class CategoryCompletionSchema(Schema):
    category: str
    mastered: int
    total: int
    pct: float


class CompletionSchema(Schema):
    total_masterable: int
    total_mastered: int
    completion_pct: float
    categories: list[CategoryCompletionSchema]


def mastery_threshold(category: str, max_level_cap: int) -> int:
    """Affinity needed to max an item (= reach mastery) for its category."""
    mult = MASTERY_MULT.get(category, DEFAULT_MULT)
    cap = max_level_cap or 30
    return mult * cap * cap


def compute_completion(xp_by_path: dict, items) -> dict:
    """Compute mastered-vs-total completion from per-item affinity.

    `items` is an iterable of (unique_name, category, max_level_cap). An item
    counts as mastered if its lifetime affinity meets the max-rank threshold.
    Approximate: modular gear (Zaws/Kitguns/Amps) and a few sources aren't
    represented as single catalog items, so true MR completion may run higher.
    """
    from collections import defaultdict

    cat_total: dict[str, int] = defaultdict(int)
    cat_mastered: dict[str, int] = defaultdict(int)

    for unique_name, category, cap in items:
        cat_total[category] += 1
        if xp_by_path.get(unique_name, 0) >= mastery_threshold(category, cap):
            cat_mastered[category] += 1

    categories = []
    total = mastered = 0
    for cat in sorted(cat_total):
        t, m = cat_total[cat], cat_mastered[cat]
        total += t
        mastered += m
        categories.append(
            {"category": cat, "mastered": m, "total": t, "pct": round(m / t * 100, 1) if t else 0.0}
        )

    return {
        "total_masterable": total,
        "total_mastered": mastered,
        "completion_pct": round(mastered / total * 100, 1) if total else 0.0,
        "categories": categories,
    }


@router.get("/warframe/mastery/completion", response={200: CompletionSchema, 404: dict})
def get_mastery_completion(request):
    """Mastery completion — items mastered vs total masterable, by category.

    Reads per-item affinity from the profile's XPInfo and compares against the
    WFCD catalog. Approximate (see compute_completion docstring).
    """
    profile = Profile.objects.first()
    if not profile:
        return Status(404, {"error": "No Warframe profile archived"})

    xp_list = (profile.profile_data or {}).get("LoadOutInventory", {}).get("XPInfo", []) or []
    xp_by_path = {
        e.get("ItemType"): int(e.get("XP", 0) or 0)
        for e in xp_list
        if e.get("ItemType")
    }

    items = CatalogItem.objects.filter(masterable=True).values_list(
        "unique_name", "category", "max_level_cap"
    )
    result = compute_completion(xp_by_path, items)
    return Status(
        200,
        CompletionSchema(
            total_masterable=result["total_masterable"],
            total_mastered=result["total_mastered"],
            completion_pct=result["completion_pct"],
            categories=[CategoryCompletionSchema(**c) for c in result["categories"]],
        ),
    )


# ---- Most-used Warframes ----


class FrameSchema(Schema):
    name: str
    weapon_path: str
    image_name: str
    equip_time_seconds: float
    equip_time_hours: float
    kills: int
    is_prime: bool
    mastery_req: int


@router.get("/warframe/frames", response=list[FrameSchema])
def list_frames(request, limit: int = 20, prime_only: bool = False):
    """Most-used Warframes by equip time.

    Joins WeaponStat to the WFCD catalog (category=Warframes) so only true
    frames are returned — sentinels, pets, archwings, and exalted weapons are
    excluded.
    """
    limit = max(1, min(limit, 200))

    catalog_qs = CatalogItem.objects.filter(category="Warframes")
    if prime_only:
        catalog_qs = catalog_qs.filter(is_prime=True)
    catalog = {c.unique_name: c for c in catalog_qs}

    weapons = (
        WeaponStat.objects.filter(weapon_path__in=catalog.keys())
        .order_by("-equip_time_seconds")[:limit]
    )

    return [
        FrameSchema(
            name=catalog[w.weapon_path].name,
            weapon_path=w.weapon_path,
            image_name=catalog[w.weapon_path].image_name,
            equip_time_seconds=w.equip_time_seconds,
            equip_time_hours=round(w.equip_time_seconds / 3600, 1),
            kills=w.kills,
            is_prime=catalog[w.weapon_path].is_prime,
            mastery_req=catalog[w.weapon_path].mastery_req,
        )
        for w in weapons
    ]


# ---- Progression (time series + velocity/projection) ----


class ProgressionPointSchema(Schema):
    date: datetime
    mastery_rank: int
    time_played_hours: float
    missions_completed: int
    total_weapon_kills: int
    weapons_tracked: int


class ProgressionSummarySchema(Schema):
    tracked_since: datetime
    days_tracked: int
    sessions: int
    current_mastery_rank: int
    mr_gained: int
    mr_per_month: float
    current_hours_played: float
    hours_in_window: float
    hours_per_week: float
    avg_session_hours: float
    projected_mr30_date: datetime | None


class ProgressionSchema(Schema):
    summary: ProgressionSummarySchema
    series: list[ProgressionPointSchema]


@router.get("/warframe/progression", response={200: ProgressionSchema, 404: dict})
def get_progression(request):
    """Full snapshot time series plus velocity/projection summary.

    The series is every snapshot oldest-first (cumulative lifetime values at
    each point). The summary derives rates over the tracked window. Velocity
    and projections are estimates — windowed from the first archived snapshot,
    so they exclude play before tracking began.
    """
    profile = Profile.objects.first()
    if not profile:
        return Status(404, {"error": "No Warframe profile archived"})

    snaps = list(profile.snapshots.order_by("captured_at"))
    if not snaps:
        return Status(404, {"error": "No snapshots recorded yet"})

    series = [
        ProgressionPointSchema(
            date=s.captured_at,
            mastery_rank=s.mastery_rank,
            time_played_hours=round(s.time_played_seconds / 3600, 1),
            missions_completed=s.missions_completed,
            total_weapon_kills=s.total_weapon_kills,
            weapons_tracked=s.weapons_tracked,
        )
        for s in snaps
    ]

    first, last = snaps[0], snaps[-1]
    window_seconds = (last.captured_at - first.captured_at).total_seconds()
    days_tracked = int(window_seconds // 86400)
    months = window_seconds / (30 * 86400)
    weeks = window_seconds / (7 * 86400)

    mr_gained = last.mastery_rank - first.mastery_rank
    hours_in_window = (last.time_played_seconds - first.time_played_seconds) / 3600
    sessions = sum(1 for s in snaps if s.trigger == "session_end")

    mr_per_month = (mr_gained / months) if months > 0 else 0.0
    hours_per_week = (hours_in_window / weeks) if weeks > 0 else 0.0
    avg_session_hours = (hours_in_window / sessions) if sessions > 0 else 0.0

    projected_mr30 = None
    if last.mastery_rank < 30 and mr_per_month > 0:
        from datetime import timedelta

        months_to_30 = (30 - last.mastery_rank) / mr_per_month
        projected_mr30 = last.captured_at + timedelta(days=months_to_30 * 30)

    summary = ProgressionSummarySchema(
        tracked_since=first.captured_at,
        days_tracked=days_tracked,
        sessions=sessions,
        current_mastery_rank=last.mastery_rank,
        mr_gained=mr_gained,
        mr_per_month=round(mr_per_month, 2),
        current_hours_played=round(last.time_played_seconds / 3600, 1),
        hours_in_window=round(hours_in_window, 1),
        hours_per_week=round(hours_per_week, 1),
        avg_session_hours=round(avg_session_hours, 2),
        projected_mr30_date=projected_mr30,
    )

    return Status(200, ProgressionSchema(summary=summary, series=series))
