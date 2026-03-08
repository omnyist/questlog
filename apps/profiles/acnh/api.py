from __future__ import annotations

from datetime import datetime

from django.db.models import Count
from django.db.models import Prefetch
from ninja import Router
from ninja import Schema

from .models import Encounter
from .models import Villager
from .models import VillagerHunt

router = Router(tags=["ACNH"])


# Schemas
class VillagerSchema(Schema):
    id: int
    name: str
    species: str
    personality: str
    icon_url: str
    image_url: str


class EncounterSchema(Schema):
    id: str
    villager: VillagerSchema
    timestamp: datetime
    recruited: bool
    notes: str
    encounters: int


class HuntSchema(Schema):
    id: str
    date: str
    target_villager: VillagerSchema | None
    result_villager: VillagerSchema | None
    encounter_count: int
    encounters: list[EncounterSchema]


class HuntResponseSchema(Schema):
    hunt: HuntSchema | None


# Endpoints
@router.get("/acnh/hunts/latest", response=HuntResponseSchema)
def get_latest_hunt(request):
    """Most recent villager hunt with the last 5 encounters."""
    hunt = (
        VillagerHunt.objects.select_related("target_villager", "result_villager")
        .annotate(total_encounters=Count("encounters"))
        .order_by("-date")
        .prefetch_related(
            Prefetch(
                "encounters",
                queryset=Encounter.objects.select_related("villager").order_by(
                    "-timestamp"
                )[:5],
                to_attr="recent_encounters",
            )
        )
        .first()
    )

    if not hunt:
        return HuntResponseSchema(hunt=None)

    # Batch-fetch encounter counts for all villagers in the recent encounters
    villager_ids = [enc.villager_id for enc in hunt.recent_encounters]
    seen_counts = dict(
        Encounter.objects.filter(villager_id__in=villager_ids)
        .values_list("villager_id")
        .annotate(count=Count("id"))
        .values_list("villager_id", "count")
    )

    return HuntResponseSchema(
        hunt=HuntSchema(
            id=str(hunt.id),
            date=str(hunt.date),
            target_villager=_villager_schema(hunt.target_villager),
            result_villager=_villager_schema(hunt.result_villager),
            encounter_count=hunt.total_encounters,
            encounters=[
                EncounterSchema(
                    id=str(enc.id),
                    villager=VillagerSchema(
                        id=enc.villager.id,
                        name=enc.villager.name,
                        species=enc.villager.species,
                        personality=enc.villager.personality,
                        icon_url=enc.villager.icon_url,
                        image_url=enc.villager.image_url,
                    ),
                    timestamp=enc.timestamp,
                    recruited=enc.recruited,
                    notes=enc.notes,
                    encounters=seen_counts.get(enc.villager_id, 1),
                )
                for enc in hunt.recent_encounters
            ],
        ),
    )


def _villager_schema(villager) -> VillagerSchema | None:
    if not villager:
        return None
    return VillagerSchema(
        id=villager.id,
        name=villager.name,
        species=villager.species,
        personality=villager.personality,
        icon_url=villager.icon_url,
        image_url=villager.image_url,
    )


# --- Stats endpoint ---


class TopVillagerSchema(Schema):
    villager: VillagerSchema
    count: int


class PersonalityStatSchema(Schema):
    personality: str
    count: int


class SpeciesStatSchema(Schema):
    species: str
    count: int


class HuntRecordSchema(Schema):
    id: str
    date: str
    encounter_count: int
    result_villager: VillagerSchema | None


class StatsSchema(Schema):
    total_hunts: int
    total_islands: int
    avg_islands_per_hunt: float
    most_encountered: list[TopVillagerSchema]
    personality_distribution: list[PersonalityStatSchema]
    species_distribution: list[SpeciesStatSchema]
    shortest_hunt: HuntRecordSchema | None
    longest_hunt: HuntRecordSchema | None


@router.get("/acnh/stats", response=StatsSchema)
def get_stats(request):
    """Aggregate stats across all villager hunts."""
    hunts = VillagerHunt.objects.annotate(num_encounters=Count("encounters"))
    total_hunts = hunts.count()
    total_islands = Encounter.objects.count()
    avg_islands = total_islands / total_hunts if total_hunts > 0 else 0

    # Most encountered villagers (top 5)
    most_encountered_qs = (
        Encounter.objects.values("villager")
        .annotate(count=Count("id"))
        .order_by("-count")[:5]
    )
    villager_ids = [row["villager"] for row in most_encountered_qs]
    villagers_by_id = {v.id: v for v in Villager.objects.filter(id__in=villager_ids)}
    most_encountered = [
        TopVillagerSchema(
            villager=_villager_schema(villagers_by_id[row["villager"]]),
            count=row["count"],
        )
        for row in most_encountered_qs
        if row["villager"] in villagers_by_id
    ]

    # Personality distribution
    personality_dist = list(
        Encounter.objects.values("villager__personality")
        .annotate(count=Count("id"))
        .order_by("-count")
    )
    personality_distribution = [
        PersonalityStatSchema(personality=row["villager__personality"], count=row["count"])
        for row in personality_dist
    ]

    # Species distribution (top 10)
    species_dist = list(
        Encounter.objects.values("villager__species")
        .annotate(count=Count("id"))
        .order_by("-count")[:10]
    )
    species_distribution = [
        SpeciesStatSchema(species=row["villager__species"], count=row["count"])
        for row in species_dist
    ]

    # Shortest and longest hunts
    shortest = hunts.order_by("num_encounters").select_related("result_villager").first()
    longest = hunts.order_by("-num_encounters").select_related("result_villager").first()

    def _hunt_record(hunt) -> HuntRecordSchema | None:
        if not hunt:
            return None
        return HuntRecordSchema(
            id=str(hunt.id),
            date=str(hunt.date),
            encounter_count=hunt.num_encounters,
            result_villager=_villager_schema(hunt.result_villager),
        )

    return StatsSchema(
        total_hunts=total_hunts,
        total_islands=total_islands,
        avg_islands_per_hunt=round(avg_islands, 1),
        most_encountered=most_encountered,
        personality_distribution=personality_distribution,
        species_distribution=species_distribution,
        shortest_hunt=_hunt_record(shortest),
        longest_hunt=_hunt_record(longest),
    )
