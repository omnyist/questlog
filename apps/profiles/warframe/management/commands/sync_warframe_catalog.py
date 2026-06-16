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
DEFAULT_CATEGORIES = ["Warframes"]


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
