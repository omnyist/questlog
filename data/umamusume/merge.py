"""Merge extracted screenshots into career runs, and report gaps.

Reads extract.py's JSONL, groups screenshots into runs, folds each run's
screens into one record, and writes runs.json for the Django importer. Image
handling stays here so the app doesn't take a Pillow dependency.

Run:
    uv run --with pillow python data/umamusume/merge.py
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import itertools
import json
import pathlib
import re
from collections import Counter

from PIL import Image

# Screenshots within this gap belong to the same run — unless the character
# changes, which splits regardless.
CLUSTER_GAP = datetime.timedelta(minutes=10)

# A career takes 20 minutes at an absolute minimum (usually 30-120), so two
# genuine completions can never be minutes apart. When they appear to be, the
# second is someone else's uma being viewed — and the tell is that it has only a
# Details modal: the Result screen exists only for a career YOU finished.
MIN_RUN_GAP = datetime.timedelta(minutes=20)

# The attributes screen shows stat GRADES and fans — no career rank, no rating.
# Reading either from it yields a stat grade or a raw stat number, so it is
# excluded from both. See the 52/56 rank disagreements it caused.
RANK_SCREENS = {"details", "result", "career_rank"}

# Ladder order, and the minimum rating for each rank. Published values where the
# community documents them (B/B+/A/A+/UG); elsewhere just under the lowest value
# observed across 372 readings. Used only to FLAG contradictions, so approximate
# boundaries are fine — the ordering is what matters.
RANK_ORDER = ["G", "F", "E", "D", "C", "C+", "B", "B+", "A", "A+", "S", "S+", "SS", "UG", "UG1", "UG2"]
RANK_MIN = {
    "C+": 4_000, "B": 6_500, "B+": 8_200, "A": 10_000, "A+": 12_100,
    "S": 14_500, "S+": 15_900, "SS": 17_500, "UG": 19_600, "UG1": 20_100, "UG2": 20_500,
}

STATS = ("speed", "stamina", "power", "guts", "wit")

# Observed across 172 fully-statted runs: 214-1433 per stat, and a rating that
# runs 2.43-4.35x the stat sum (superlinear, hence the wide band). Deliberately
# loose — this catches a value read off the wrong element entirely, not a small
# misread. A one-row column shift moves the sum by ~5%, well inside the band, so
# nothing here would catch it; disagreeing Details screens are what does.
STAT_RANGE = (1, 1_800)
RATING_PER_STAT = (2.0, 5.0)

STEAM_NAME = re.compile(r"(\d{8})(\d{6})_1\.jpg$", re.IGNORECASE)
EXIF_IFD_POINTER = 0x8769  # 34665 — points at the sub-IFD holding DateTimeOriginal
EXIF_DATETIME_ORIGINAL = 36867
EXIF_DATETIME = 306  # top-level fallback; iOS writes the same value to both


def capture_time(root: pathlib.Path, image: str, stored: str | None = None) -> datetime.datetime | None:
    """Steam encodes capture time in the filename; iOS carries it in EXIF.

    A previously resolved value wins, so the archive survives deleting the
    source images — an iOS date exists nowhere else once its PNG is gone.

    Deliberately never uses mtime/birthtime — they mean opposite things on the
    two platforms (copy time for one, capture time for the other), so trusting
    either uniformly misdates half the archive.
    """
    if stored:
        return datetime.datetime.fromisoformat(stored)
    m = STEAM_NAME.search(image)
    if m:
        return datetime.datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S")
    try:
        with Image.open(root / image) as im:
            exif = im.getexif()
            # DateTimeOriginal lives in the Exif sub-IFD; getexif() alone returns
            # only the top-level IFD, where it is absent.
            raw = exif.get_ifd(EXIF_IFD_POINTER).get(EXIF_DATETIME_ORIGINAL) or exif.get(EXIF_DATETIME)
    except OSError:
        return None
    if not raw:
        return None
    return datetime.datetime.strptime(str(raw).strip(), "%Y:%m:%d %H:%M:%S")


def vote(records: list[dict], field: str, screens: set[str] | None = None):
    """Most common non-null value across the run's screens.

    The screens overlap by design, so a lone digit misread loses to the two
    screens that agree with each other.
    """
    values = [
        r[field]
        for r in records
        if r.get(field) is not None
        and r["screen_type"] != "other"
        and (r["screen_type"] in screens if screens else True)
    ]
    return Counter(values).most_common(1)[0][0] if values else None


def first_from(records: list[dict], screen: str, field: str):
    for r in records:
        if r["screen_type"] == screen and r.get(field) not in (None, [], {}, ""):
            return r[field]
    return None


def split_on_character(cluster: list[dict]) -> list[list[dict]]:
    """One burst can hold two runs finished minutes apart. Character identity is
    the reliable boundary — a tighter time gap would fragment slow runs."""
    groups: list[list[dict]] = []
    current: list[dict] = []
    seen: str | None = None
    for rec in cluster:
        who = rec.get("character_name")
        if who and seen and who != seen and current:
            groups.append(current)
            current = []
        if who:
            seen = who
        current.append(rec)
    if current:
        groups.append(current)
    return groups


def rank_conflicts(rank: str | None, rating: int | None) -> str | None:
    """Rank is a function of rating, so a mismatch means one of them is wrong."""
    if not rank or rating is None or rank not in RANK_MIN:
        return None
    if rating < RANK_MIN[rank]:
        return f"rating {rating:,} below {rank} minimum {RANK_MIN[rank]:,}"
    idx = RANK_ORDER.index(rank)
    for higher in RANK_ORDER[idx + 1:]:
        if higher in RANK_MIN:
            if rating >= RANK_MIN[higher]:
                return f"rating {rating:,} reaches {higher} but rank says {rank}"
            break
    return None


def stat_conflicts(run: dict, disputed: list[str]) -> str | None:
    """Sanity-check the raw stats.

    Ordered by how much each finding actually proves. A disagreement between two
    Details screens of the same career is decisive — the game does not change
    the numbers between screenshots, so one reading is simply wrong. The rest are
    plausibility bounds: they catch a value grabbed off the wrong element, and
    would not catch a subtle misread.
    """
    if disputed:
        return f"Details screens disagree on {', '.join(disputed)}"

    present = [s for s in STATS if run.get(s) is not None]
    if 0 < len(present) < len(STATS):
        missing = [s for s in STATS if run.get(s) is None]
        return f"only {len(present)}/5 stats read (missing {', '.join(missing)})"
    if not present:
        return None

    low, high = STAT_RANGE
    out_of_range = [f"{s}={run[s]:,}" for s in STATS if not (low <= run[s] <= high)]
    if out_of_range:
        return f"stat outside {low}-{high:,}: {', '.join(out_of_range)}"

    if run.get("rating"):
        ratio = run["rating"] / sum(run[s] for s in STATS)
        if not (RATING_PER_STAT[0] <= ratio <= RATING_PER_STAT[1]):
            return (f"rating {run['rating']:,} is {ratio:.2f}x the stat sum "
                    f"{sum(run[s] for s in STATS):,} (expected {RATING_PER_STAT[0]}-{RATING_PER_STAT[1]}x)")
    return None


def build_run(group: list[dict]) -> dict | None:
    real = [r for r in group if r["screen_type"] != "other"]
    if not real:
        return None

    character = vote(real, "character_name")
    if not character:
        return None

    rating = vote(real, "rating", RANK_SCREENS)
    rank = vote(real, "rank", RANK_SCREENS)
    races = vote(real, "races")
    wins = vote(real, "wins")

    images = [r["image"] for r in group]
    platform = "ios" if any(i.lower().endswith(".png") for i in images) else "steam"

    fingerprint = hashlib.sha256(
        "|".join(str(x) for x in (character, vote(real, "outfit_title"), rating, races, wins)).encode()
    ).hexdigest()

    # Stats come only from Details screens, but a run can have more than one —
    # voting lets them cross-check each other instead of the first silently
    # winning. A tie means two screens of the same career disagree, which the
    # game makes impossible, so record it rather than picking a side.
    stats: dict[str, int | None] = {}
    disputed: list[str] = []
    for stat in STATS:
        seen = [r[stat] for r in real if r["screen_type"] == "details" and r.get(stat) is not None]
        counts = Counter(seen).most_common(2)
        stats[stat] = counts[0][0] if counts else None
        if len(counts) > 1 and counts[0][1] == counts[1][1]:
            disputed.append(f"{stat} ({counts[0][0]:,} vs {counts[1][0]:,})")

    screens = {r["screen_type"] for r in real}
    run = {
        "character": character,
        "outfit_title": vote(real, "outfit_title"),
        "earned_title": vote(real, "earned_title"),
        "rank": rank,
        "rating": rating,
        **stats,
        "fans": vote(real, "fans"),
        "races": races,
        "wins": wins,
        "aptitudes": first_from(real, "details", "aptitudes") or first_from(real, "attributes", "aptitudes") or {},
        "major_wins": first_from(real, "result", "major_wins") or [],
        "support_cards": next((r["support_cards"] for r in real if r.get("support_cards")), []),
        "legacy_ranks": next((r["legacy_ranks"] for r in real if r.get("legacy_ranks")), []),
        "run_date": min(r["_when"] for r in group).isoformat(),
        "platform": platform,
        "source_images": images,
        "screens": sorted(screens),
        "fingerprint": fingerprint,
        "warning": rank_conflicts(rank, rating),
    }
    run["stat_warning"] = stat_conflicts(run, disputed)
    return run


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--extracted", default="data/umamusume/extracted.jsonl")
    ap.add_argument("--images", default="data/umamusume/screenshots")
    ap.add_argument("--out", default="data/umamusume/runs.json")
    args = ap.parse_args()

    root = pathlib.Path(args.images)
    extracted_path = pathlib.Path(args.extracted)
    records = [json.loads(line) for line in extracted_path.open() if line.strip()]
    undated = []
    newly_dated = 0
    for rec in records:
        rec["_when"] = capture_time(root, rec["image"], rec.get("captured_at"))
        if rec["_when"] is None:
            undated.append(rec["image"])
        elif not rec.get("captured_at"):
            rec["captured_at"] = rec["_when"].isoformat()
            newly_dated += 1

    # Persist resolved dates back into the extraction so the source images stop
    # being load-bearing and can be archived off this machine.
    if newly_dated:
        with extracted_path.open("w") as fh:
            for rec in records:
                fh.write(json.dumps({k: v for k, v in rec.items() if k != "_when"}) + "\n")

    records = [r for r in records if r["_when"]]
    records.sort(key=lambda r: r["_when"])

    clusters: list[list[dict]] = [[records[0]]]
    for prev, cur in itertools.pairwise(records):
        if cur["_when"] - prev["_when"] <= CLUSTER_GAP:
            clusters[-1].append(cur)
        else:
            clusters.append([cur])

    runs = []
    for cluster in clusters:
        for group in split_on_character(cluster):
            run = build_run(group)
            if run:
                runs.append(run)

    # Collapse duplicates: the same run screenshotted twice hashes identically.
    by_fp: dict[str, dict] = {}
    for run in runs:
        existing = by_fp.get(run["fingerprint"])
        if existing:
            existing["source_images"] += run["source_images"]
            existing["screens"] = sorted(set(existing["screens"]) | set(run["screens"]))
        else:
            by_fp[run["fingerprint"]] = run
    runs = sorted(by_fp.values(), key=lambda r: r["run_date"])

    # Mark browsed umas: too close to the preceding run to be a real career, and
    # carrying no Result screen. Kept in the file, flagged rather than dropped,
    # so the exclusion is visible and reversible.
    for run in runs:
        run["suspect"] = None
    for prev, cur in itertools.pairwise(runs):
        gap = datetime.datetime.fromisoformat(cur["run_date"]) - datetime.datetime.fromisoformat(prev["run_date"])
        if gap >= MIN_RUN_GAP:
            continue
        weaker = min((prev, cur), key=lambda r: ("result" in r["screens"], len(r["screens"])))
        if "result" not in weaker["screens"]:
            weaker["suspect"] = (
                f"only {gap.total_seconds()/60:.1f} min after the previous run and has no Result "
                f"screen — likely another trainer's uma being viewed, not a completed career"
            )

    pathlib.Path(args.out).write_text(json.dumps(runs, indent=2))
    suspects = [r for r in runs if r["suspect"]]

    complete = [r for r in runs if "details" in r["screens"] and "result" in r["screens"]]
    no_stats = [r for r in runs if r["speed"] is None]
    no_record = [r for r in runs if r["races"] is None]
    flagged = [r for r in runs if r["warning"]]

    print(f"screenshots: {len(records)} dated, {len(undated)} undated"
          + (f"  ({newly_dated} capture times persisted into the extraction)" if newly_dated else ""))
    print(f"runs: {len(runs)}  ({len(suspects)} flagged not-yours, {len(runs)-len(suspects)} importable; "
          f"complete Details+Result: {len(complete)})")
    print(f"characters: {len({r['character'] for r in runs})}   "
          f"outfits: {len({(r['character'], r['outfit_title']) for r in runs})}")
    print(f"wrote {args.out}")

    print(f"\nflagged as NOT YOURS (excluded from import): {len(suspects)}")
    for r in suspects:
        print(f"  {r['run_date'][:10]}  [{r['outfit_title'] or '—'}] {r['character']}  "
              f"{r['rank']}/{r['rating']}")
        print(f"     {r['suspect']}")

    print("\n--- GAP REPORT: re-screenshot these in-game ---")
    print(f"\nmissing raw stats (no Details screen): {len(no_stats)}")
    for r in sorted(no_stats, key=lambda x: x["run_date"])[:20]:
        print(f"  {r['run_date'][:10]}  [{r['outfit_title'] or '—'}] {r['character']}  "
              f"rank={r['rank']} rating={r['rating']}")
    if len(no_stats) > 20:
        print(f"  ... and {len(no_stats)-20} more")

    print(f"\nmissing race record (no Result screen): {len(no_record)}")
    for r in sorted(no_record, key=lambda x: x["run_date"])[:20]:
        print(f"  {r['run_date'][:10]}  [{r['outfit_title'] or '—'}] {r['character']}  "
              f"rank={r['rank']} rating={r['rating']}")
    if len(no_record) > 20:
        print(f"  ... and {len(no_record)-20} more")

    print(f"\nrank/rating contradictions (needs a human eye): {len(flagged)}")
    for r in flagged:
        print(f"  {r['run_date'][:10]}  {r['character']}: {r['warning']}")
        print(f"     {', '.join(r['source_images'])}")

    stat_flagged = [r for r in runs if r["stat_warning"]]
    print(f"\nstat integrity problems (needs a human eye): {len(stat_flagged)}")
    for r in stat_flagged:
        print(f"  {r['run_date'][:10]}  {r['character']}: {r['stat_warning']}")
        print(f"     {', '.join(r['source_images'])}")

    if undated:
        print(f"\nundated screenshots (no filename timestamp, no EXIF): {len(undated)}")
        for i in undated[:10]:
            print(f"  {i}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
