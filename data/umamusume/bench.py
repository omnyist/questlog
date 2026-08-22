"""Benchmark a local LM Studio vision model against the Opus extraction.

The question isn't raw accuracy — the pipeline already has cross-screen voting
and a rank/rating band check that absorb noisy errors. The question is whether a
model's mistakes are LOUD (something downstream can catch) or SILENT (plausible
values that corrupt the archive quietly). A 90% model whose errors are all loud
beats a 96% model that quietly shifts a stat column.

Two scoring sets:
  * 45 hand-verified fields across 7 screenshots — ground truth I read myself.
  * All 661 Opus extractions — broad coverage, but Opus is not infallible, so
    disagreement means "differs from Opus", not necessarily "wrong".

Run:
    uv run --with pillow --with httpx python data/umamusume/bench.py \
        --model qwen/qwen3-vl-30b
"""

from __future__ import annotations

import argparse
import json
import pathlib
import random
import sys
import time
from collections import Counter

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import extract  # noqa: E402 — reuse the production prompt, schema, and encoder

IMAGES = pathlib.Path("data/umamusume/screenshots")

# Values I read off the screenshots myself, not model output.
GROUND_TRUTH: dict[str, dict] = {
    "IMG_1353.PNG": {"screen_type": "details", "character_name": "Oguri Cap", "outfit_title": "Starlight Beat", "earned_title": "Ideal Idol", "rank": "S+", "rating": 16866, "speed": 1136, "stamina": 835, "power": 1031, "guts": 661, "wit": 851},
    "IMG_1354.PNG": {"screen_type": "result", "character_name": "Oguri Cap", "rank": "S+", "rating": 16866, "races": 42, "wins": 42},
    "IMG_1352.PNG": {"screen_type": "attributes", "character_name": "Oguri Cap", "outfit_title": "Starlight Beat", "fans": 928253},
    "20251026200504_1.jpg": {"screen_type": "details", "character_name": "Gold Ship", "outfit_title": "Red Strife", "earned_title": "The GOAT", "rank": "B+", "rating": 8704, "speed": 833, "stamina": 753, "power": 702, "guts": 377, "wit": 298},
    "20251026200610_1.jpg": {"screen_type": "result", "character_name": "Gold Ship", "rank": "B+", "rating": 8704, "races": 15, "wins": 13},
    "20251026200451_1.jpg": {"screen_type": "career_rank", "rank": "B+", "rating": 8704},
    "20251026200433_1.jpg": {"screen_type": "attributes", "character_name": "Gold Ship", "outfit_title": "Red Strife", "fans": 333292},
}

STATS = ("speed", "stamina", "power", "guts", "wit")
KNOWN_RANKS = set(extract.__dict__.get("KNOWN_RANKS", [])) or {
    "G", "F", "E", "D", "C", "C+", "B", "B+", "A", "A+", "S", "S+", "SS", "SS+",
    "UG", "UG1", "UG2", "UG3",
}


def query(model: str, image: pathlib.Path, timeout: float, url: str = extract.LOCAL_URL) -> tuple[dict, float]:
    """One image through the same code path the real local extraction uses.

    Deliberately not a reimplementation — benchmarking a second copy of the
    request would measure something the pipeline never runs. Retries are off so
    a repetition loop is scored as the failure it is rather than being papered
    over on a second attempt.
    """
    started = time.time()
    record = extract.extract_local(image, model, url, timeout, attempts=1)
    return record, time.time() - started


def loudness(record: dict) -> list[str]:
    """Problems a downstream check could catch on its own.

    Anything listed here is survivable — the pipeline rejects or corrects it.
    What's dangerous is a wrong value that appears in none of these.
    """
    loud = []
    rank = record.get("rank")
    if rank and rank not in KNOWN_RANKS:
        loud.append(f"rank {rank!r} is not a real rank")

    rating = record.get("rating")
    if rating is not None and not (3_000 <= rating <= 25_000):
        loud.append(f"rating {rating} outside the plausible range")

    if rank and rating is not None:
        minimum = extract.__dict__.get("RANK_MIN", {}).get(rank)
        if minimum and rating < minimum:
            loud.append(f"rating {rating} contradicts rank {rank}")

    # A Details screen shows all five stats. A partial set means the model lost
    # its place in the column — the exact shape of Gemma's silent failure.
    if record.get("screen_type") == "details":
        present = [s for s in STATS if record.get(s) is not None]
        if 0 < len(present) < len(STATS):
            loud.append(f"only {len(present)}/5 stats read — column misalignment")

    for field in ("character_name", "outfit_title"):
        value = record.get(field)
        if value and (value.startswith("[") or value.endswith("]")):
            loud.append(f"{field} still bracketed: {value!r}")
    return loud


def compare(expected: dict, got: dict, fields: list[str]) -> list[tuple[str, object, object]]:
    return [(f, expected.get(f), got.get(f)) for f in fields if expected.get(f) != got.get(f)]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--model", required=True, help="LM Studio model id")
    ap.add_argument("--timeout", type=float, default=600.0)
    ap.add_argument("--sample", type=int, default=0,
                    help="also score this many random images against the Opus extraction")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--dump", default="data/umamusume/bench_results.jsonl",
                    help="per-image model output, so disagreements can be adjudicated "
                         "without paying for another pass")
    args = ap.parse_args()

    print(f"model: {args.model}\n")

    # --- Phase 1: hand-verified ground truth ---
    checked = wrong = 0
    silent: list[str] = []
    elapsed: list[float] = []
    print("=== hand-verified ground truth (45 fields, 7 images) ===")
    for image, expected in GROUND_TRUTH.items():
        try:
            got, dt = query(args.model, IMAGES / image, args.timeout)
        except Exception as exc:  # noqa: BLE001 — a dead model is a valid result
            print(f"  {image:<26} FAILED {type(exc).__name__}: {str(exc)[:120]}")
            continue
        elapsed.append(dt)
        diffs = compare(expected, got, list(expected))
        checked += len(expected)
        wrong += len(diffs)
        loud = loudness(got)
        verdict = "OK" if not diffs else f"{len(diffs)} wrong"
        print(f"  {image:<26} {dt:>5.1f}s  {verdict}" + (f"   [loud: {'; '.join(loud)}]" if loud else ""))
        for field, want, have in diffs:
            quiet = not loud
            marker = "SILENT" if quiet else "loud  "
            if quiet:
                silent.append(f"{image} {field}: want {want!r} got {have!r}")
            print(f"      {marker} {field}: want {want!r} got {have!r}")

    if checked:
        print(f"\n  accuracy: {checked-wrong}/{checked} = {(checked-wrong)/checked*100:.0f}%")
        print(f"  avg: {sum(elapsed)/max(1,len(elapsed)):.1f}s/image")
        print(f"  SILENT errors (nothing downstream would catch): {len(silent)}")
        for s in silent:
            print(f"    {s}")

    # --- Phase 2: broad agreement with the Opus extraction ---
    if args.sample:
        opus = {json.loads(line)["image"]: json.loads(line)
                for line in pathlib.Path("data/umamusume/extracted.jsonl").open() if line.strip()}
        pool = [i for i in opus if (IMAGES / i).exists()]
        random.seed(args.seed)
        picks = random.sample(pool, min(args.sample, len(pool)))
        fields = ["screen_type", "character_name", "outfit_title", "rank", "rating", *STATS,
                  "fans", "races", "wins"]
        agree = total = 0
        per_field = Counter()
        loud_count = 0
        print(f"\n=== agreement with Opus extraction ({len(picks)} random images) ===")
        dump = pathlib.Path(args.dump).open("w") if args.dump else None
        for i, image in enumerate(picks, 1):
            try:
                got, _ = query(args.model, IMAGES / image, args.timeout)
            except Exception as exc:  # noqa: BLE001
                print(f"  [{i}/{len(picks)}] {image}: FAILED {type(exc).__name__}")
                if dump:
                    dump.write(json.dumps({"image": image, "error": type(exc).__name__}) + "\n")
                continue
            if dump:
                dump.write(json.dumps({"image": image, "local": got, "opus": opus[image],
                                       "loud": loudness(got)}, default=str) + "\n")
            diffs = compare(opus[image], got, fields)
            total += len(fields)
            agree += len(fields) - len(diffs)
            for field, _, _ in diffs:
                per_field[field] += 1
            if loudness(got):
                loud_count += 1
            if i % 10 == 0:
                print(f"  [{i}/{len(picks)}] running agreement: {agree/max(1,total)*100:.0f}%")
        if dump:
            dump.close()
            print(f"  per-image output written to {args.dump}")
        if total:
            print(f"\n  agreement with Opus: {agree}/{total} = {agree/total*100:.0f}%")
            print(f"  images with a loud signal: {loud_count}/{len(picks)}")
            print("  most-disagreed fields:")
            for field, n in per_field.most_common(8):
                print(f"    {field:<16} {n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
