from __future__ import annotations

from datetime import datetime

from django.db.models import Count
from django.db.models import Prefetch
from ninja import Router
from ninja import Schema

from .models import Encounter
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
