"""
Import IronMON data from Synthform export.

Usage: uv run python data/import_ironmon.py

Reads: data/ironmon_export.json (Django dumpdata format)
Maps:
  - ironmon.challenge → Challenge
  - ironmon.checkpoint → Checkpoint
  - ironmon.seed → Run
  - ironmon.result → CheckpointResult
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
sys.path.insert(0, str(Path(__file__).parent.parent))
django.setup()

from apps.profiles.ironmon.models import Challenge
from apps.profiles.ironmon.models import Checkpoint
from apps.profiles.ironmon.models import CheckpointResult
from apps.profiles.ironmon.models import Run


def import_ironmon():
    with open(Path(__file__).parent / "ironmon_export.json") as f:
        data = json.load(f)

    # Group by model type
    challenges = [d for d in data if d["model"] == "ironmon.challenge"]
    checkpoints = [d for d in data if d["model"] == "ironmon.checkpoint"]
    seeds = [d for d in data if d["model"] == "ironmon.seed"]
    results = [d for d in data if d["model"] == "ironmon.result"]

    print(f"Found: {len(challenges)} challenges, {len(checkpoints)} checkpoints, "
          f"{len(seeds)} seeds, {len(results)} results")

    # Map old PKs to new objects
    challenge_map = {}
    checkpoint_map = {}

    # Import challenges → Challenge
    for c in challenges:
        challenge, created = Challenge.objects.get_or_create(
            slug=c["fields"]["name"].lower().replace(" ", "-"),
            defaults={"name": c["fields"]["name"]},
        )
        challenge_map[c["pk"]] = challenge
        print(f"  Challenge: {challenge.name} ({'created' if created else 'exists'})")

    # Import checkpoints
    for cp in checkpoints:
        checkpoint, created = Checkpoint.objects.get_or_create(
            challenge=challenge_map[cp["fields"]["challenge"]],
            order=cp["fields"]["order"],
            defaults={
                "name": cp["fields"]["name"],
                "trainer": cp["fields"]["trainer"],
            },
        )
        checkpoint_map[cp["pk"]] = checkpoint

    print(f"  Imported {len(checkpoint_map)} checkpoints")

    # Import seeds → Run (bulk for performance)
    existing_seeds = set(Run.objects.values_list("seed_number", flat=True))
    runs_to_create = []
    for s in seeds:
        if s["pk"] not in existing_seeds:
            runs_to_create.append(
                Run(
                    seed_number=s["pk"],
                    challenge=challenge_map[s["fields"]["challenge"]],
                )
            )
    if runs_to_create:
        Run.objects.bulk_create(runs_to_create, ignore_conflicts=True)
    print(f"  Imported {len(runs_to_create)} new runs (skipped {len(seeds) - len(runs_to_create)} existing)")

    # Import results (bulk)
    existing_results = set(
        CheckpointResult.objects.values_list("run_id", "checkpoint_id")
    )
    results_to_create = []
    for r in results:
        checkpoint = checkpoint_map[r["fields"]["checkpoint"]]
        key = (r["fields"]["seed"], checkpoint.id)
        if key not in existing_results:
            results_to_create.append(
                CheckpointResult(
                    run_id=r["fields"]["seed"],
                    checkpoint=checkpoint,
                )
            )
    if results_to_create:
        CheckpointResult.objects.bulk_create(results_to_create, ignore_conflicts=True)
    print(f"  Imported {len(results_to_create)} new results (skipped {len(results) - len(results_to_create)} existing)")

    # Update denormalized fields
    print("  Updating denormalized fields...")
    updated = 0
    for run in Run.objects.prefetch_related("results__checkpoint"):
        last = run.results.order_by("-checkpoint__order").first()
        if last:
            run.highest_checkpoint = last.checkpoint
            run.is_victory = last.checkpoint.order == 23  # Champion
            run.save(update_fields=["highest_checkpoint", "is_victory"])
            updated += 1

    print(f"  Updated {updated} runs with highest checkpoint")

    # Summary
    print("\nImport complete!")
    print(f"  Challenges: {Challenge.objects.count()}")
    print(f"  Checkpoints: {Checkpoint.objects.count()}")
    print(f"  Runs: {Run.objects.count()}")
    print(f"  Results: {CheckpointResult.objects.count()}")
    print(f"  Victories: {Run.objects.filter(is_victory=True).count()}")


if __name__ == "__main__":
    import_ironmon()
