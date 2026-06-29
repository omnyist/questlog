"""sync_warframe_catalog — vendors the WFCD warframe-items catalog into the DB.

Downloads per-category JSON from the WFCD warframe-items dataset and upserts
into CatalogItem, keyed on uniqueName (the /Lotus/... asset path) so it joins
to WeaponStat.weapon_path.

Idempotent — safe to re-run; refresh whenever the game adds items.
"""

from __future__ import annotations

import httpx
from django.core.management.base import BaseCommand

from apps.profiles.warframe.models import CatalogItem

BASE_URL = "https://raw.githubusercontent.com/WFCD/warframe-items/master/data/json"
# All categories that grant mastery, for completion tracking.
DEFAULT_CATEGORIES = [
    "Warframes",
    "Primary",
    "Secondary",
    "Melee",
    "Arch-Gun",
    "Arch-Melee",
    "Archwing",
    "Sentinels",
    "SentinelWeapons",
    "Pets",
]


# Tenet weapons share a prefix but split across two acquisition paths; WFCD's
# "Tenet" tag doesn't distinguish them, so we special-case the Ergo Glast set
# (everything else Tenet drops from a Sister of Parvos). List from FrameHub.
HOLOKEY_WEAPONS = {
    "Tenet Agendus",
    "Tenet Exec",
    "Tenet Livia",
    "Tenet Grigori",
    "Tenet Ferrox",
}

# The six syndicates that sell augment/signature weapons for standing.
SYNDICATES = {
    "Red Veil",
    "New Loka",
    "Perrin Sequence",
    "Cephalon Suda",
    "Arbiters of Hexis",
    "Steel Meridian",
}


def _pet_acquisition(unique_name: str) -> str:
    """Companion acquisition from the /Lotus/ asset path — WFCD tags none of
    them. Sub-typing mirrors FrameHub's (Infested before plain, since
    "InfestedCatbrow" contains "Catbrow" and "PredatorKubrow" contains "Kubrow").
    """
    if "MoaPet" in unique_name:
        return "Legs (Fortuna)"
    if "ZanukaPet" in unique_name:
        return "Sister of Parvos"  # Hound parts drop from Sisters of Parvos
    if "InfestedCatbrow" in unique_name or "PredatorKubrow" in unique_name:
        return "Deimos (Son)"
    if "Catbrow" in unique_name or "Kubrow" in unique_name:
        return "Incubator"
    return "Companion"


def _acquisition(item: dict) -> str:
    """How an item is obtained, classified from name prefix + WFCD tags.

    Name prefix is authoritative for the lich-style systems and a few others —
    DE names those consistently even when WFCD's tags lag (several Coda weapons
    are tagged only "Infested", for instance). We fall back to tags for the
    systems prefixes don't identify (syndicates, events, invasions, relics),
    then to market vs. foundry. Faction tags (Tenno/Grineer/...) are ignored.
    """
    name = item.get("name", "") or ""
    tags = set(item.get("tags", []) or [])
    # Word membership (not just first word) so compound names like
    # "Dual Coda Torxica" still match their system.
    words = set(name.split())

    # Name-identified systems (reliable from DE naming).
    if "Kuva" in words:
        return "Kuva Lich"
    if "Coda" in words:
        return "Technocyte Coda"
    if "Tenet" in words:
        return "Corrupted Holokey" if name in HOLOKEY_WEAPONS else "Sister of Parvos"
    if words & {"Prisma", "Mara"}:
        return "Baro Ki'Teer"
    if "Dex" in words:
        return "Anniversary"

    # Tag-identified systems (prefixes don't reveal these).
    syndicate = tags & SYNDICATES
    if syndicate:
        return sorted(syndicate)[0]
    if "Syndicate" in tags:
        return "Syndicate"
    if tags & {"Baro", "Prisma"}:
        return "Baro Ki'Teer"
    if "Invasion Reward" in tags:
        return "Invasion"
    if tags & {"Vandal", "Wraith"}:
        return "Event"
    # isPrime catches primes WFCD shipped without a "Prime" tag (e.g. Odonata
    # Prime). Must precede market/foundry — primes are built from relic parts.
    if "Prime" in tags or item.get("isPrime"):
        return "Void Relic"

    # Companions get no tags; classify by asset path before the build/buy
    # fallback (MOAs and Hounds have recipes and would read as Foundry).
    if item.get("category") == "Pets":
        return _pet_acquisition(item.get("uniqueName", "") or "")

    # Generic fallbacks.
    if name.startswith("Mk1-"):
        return "Market"
    if item.get("marketCost"):
        return "Market"
    if item.get("components"):
        return "Foundry"
    return ""


class Command(BaseCommand):
    help = "Sync the WFCD warframe-items catalog into CatalogItem"

    def add_arguments(self, parser):
        parser.add_argument(
            "--categories",
            nargs="+",
            default=DEFAULT_CATEGORIES,
            help="WFCD category files to sync (e.g. Warframes Primary Sentinels)",
        )

    def handle(self, *args, **options):
        categories = options["categories"]
        total_created = 0
        total_updated = 0

        with httpx.Client(timeout=60.0, follow_redirects=True) as client:
            for category in categories:
                url = f"{BASE_URL}/{category}.json"
                self.stdout.write(f"Fetching {category}...")
                try:
                    response = client.get(url)
                    response.raise_for_status()
                    items = response.json()
                except httpx.HTTPError as exc:
                    self.stderr.write(self.style.ERROR(f"  Failed to fetch {category}: {exc}"))
                    continue

                created, updated = self._sync_items(items)
                total_created += created
                total_updated += updated
                self.stdout.write(
                    self.style.SUCCESS(
                        f"  {category}: {created} created, {updated} updated ({len(items)} total)"
                    )
                )

        self.stdout.write(
            self.style.SUCCESS(
                f"Catalog sync complete: {total_created} created, {total_updated} updated"
            )
        )

    def _sync_items(self, items: list[dict]) -> tuple[int, int]:
        created = 0
        updated = 0
        for item in items:
            unique_name = item.get("uniqueName")
            if not unique_name:
                continue
            defaults = {
                "name": item.get("name", "") or "",
                "category": item.get("category", "") or "",
                "item_type": item.get("type", "") or "",
                "mastery_req": int(item.get("masteryReq", 0) or 0),
                "masterable": bool(item.get("masterable", False)),
                "is_prime": bool(item.get("isPrime", False)),
                "vaulted": bool(item.get("vaulted", False)),
                "vault_date": item.get("vaultDate", "") or "",
                "max_level_cap": int(item.get("maxLevelCap", 30) or 30),
                "acquisition": _acquisition(item),
                "tags": item.get("tags", []) or [],
                "image_name": item.get("imageName", "") or "",
                "product_category": item.get("productCategory", "") or "",
                "raw": item,
            }
            _, was_created = CatalogItem.objects.update_or_create(
                unique_name=unique_name,
                defaults=defaults,
            )
            if was_created:
                created += 1
            else:
                updated += 1
        return created, updated
