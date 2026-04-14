from __future__ import annotations

from datetime import datetime

from django.db.models import Avg
from django.db.models import Count
from django.db.models import Sum
from ninja import Router
from ninja import Schema

from .models import Affiliation
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
        return 404, {"error": "No Warframe profile archived"}

    weapon_aggregate = profile.weapons.aggregate(
        count=Count("id"),
        total_kills=Sum("kills"),
    )

    return 200, ProfileSchema(
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
    )


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
        return 404, {"error": "No Warframe profile archived"}

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

    return 200, StatsSchema(
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
    )
