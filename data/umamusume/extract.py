"""Extract structured career-run data from Umamusume end-of-run screenshots.

One vision call per image. Each screenshot self-identifies its screen type, so
non-end-of-run strays classify as "other" and are dropped downstream — no
separate classification pass.

Writes JSONL (one record per image) and is resumable: images already present in
the output file are skipped.

Run:
    uv run --with anthropic --with pillow python data/umamusume/extract.py \
        --only IMG_1352.PNG,IMG_1353.PNG --out data/umamusume/sample.jsonl
"""

from __future__ import annotations

import argparse
import base64
import io
import json
import pathlib
import sys

from anthropic import Anthropic
from PIL import Image

# The API downsamples above this anyway; doing it locally keeps request bodies
# small without costing accuracy or extra image tokens.
MAX_EDGE = 2576

SYSTEM = """You extract structured data from Umamusume: Pretty Derby end-of-career screenshots.

Screen types:
- "details": the "Umamusume Details" modal. Rank badge, numeric Rating, the five
  raw stats as NUMBERS (Speed/Stamina/Power/Guts/Wit), aptitude grid, title.
- "result": the post-career result screen. Large rank badge, Rating, character
  name, "Career Record" (Races / Wins), and a "Major Wins" list.
- "attributes": the "Complete Career" panel with a stats radar chart. Has Fans
  count, stat LETTER GRADES (not numbers), aptitude grid, Skill Pts.
- "career_rank": the "CAREER RANK" reveal — big rank badge, Rating, progress bar.
- "other": anything else (mid-run, menus, races, gacha, etc.).

Rules:
- Report ONLY what is legible in this image. Use null for anything absent or
  unreadable. Never infer a value from another field or from game knowledge.
- Names appear as "[Outfit] Character" (e.g. "[Starlight Beat] Oguri Cap").
  Put "Oguri Cap" in character_name and "Starlight Beat" in outfit_title. If
  there is no bracketed prefix, leave outfit_title blank.
- earned_title is the separate swappable title next to the "Change" button
  (e.g. "Ideal Idol", "The GOAT") — NOT the bracketed outfit title.
- Stats: only the "details" screen has raw numbers. On "attributes" the stats
  are letter grades; leave the numeric fields null there.
- Aptitude grades are single letters, optionally with + (S, A, B+, G, ...).
- Steam screenshots show a "Career Profile" side panel; capture its support
  card rarities/levels and the Legacy Umamusume rank badges. iOS screenshots
  have no such panel — leave those lists empty."""


# Hand-written and deliberately flat. Nested objects plus a `X | None` union on
# every field push this past the structured-output complexity limit ("Schema is
# too complex"), so every field is a required plain string — the model writes ""
# for anything it can't read — and numbers/aptitudes are parsed back below.
_STR = {"type": "string"}
_STRS = {"type": "array", "items": {"type": "string"}}

SCHEMA = {
    "type": "object",
    "properties": {
        "screen_type": {
            "type": "string",
            "enum": ["details", "result", "attributes", "career_rank", "other"],
        },
        "character_name": _STR,
        "outfit_title": _STR,
        "earned_title": _STR,
        "rank": _STR,
        "rating": _STR,
        "speed": _STR,
        "stamina": _STR,
        "power": _STR,
        "guts": _STR,
        "wit": _STR,
        "fans": _STR,
        "races": _STR,
        "wins": _STR,
        # One string beats ten nested fields for schema complexity — but the
        # format has to be described HERE, where the model can see it.
        "aptitudes": {
            "type": "string",
            "description": (
                "The full aptitude grid as comma-separated Name:Grade pairs, in "
                "this exact order: Turf, Dirt, Sprint, Mile, Medium, Long, "
                "Front, Pace, Late, End. Example: "
                "'Turf:A, Dirt:B, Sprint:E, Mile:A, Medium:A, Long:A, "
                "Front:D, Pace:A, Late:A, End:D'. "
                "Empty string if this screen shows no aptitude grid."
            ),
        },
        "major_wins": _STRS,
        "support_cards": _STRS,  # e.g. "SSR Lv30"
        "legacy_ranks": _STRS,
    },
    "required": [
        "screen_type", "character_name", "outfit_title", "earned_title", "rank",
        "rating", "speed", "stamina", "power", "guts", "wit", "fans",
        "races", "wins", "aptitudes", "major_wins", "support_cards",
        "legacy_ranks",
    ],
    "additionalProperties": False,
}

NUMERIC = ("rating", "speed", "stamina", "power", "guts", "wit", "fans", "races", "wins")


def normalize(raw: dict) -> dict:
    """Blank strings to None, numeric strings to ints, aptitudes to a dict."""
    out = dict(raw)
    for key in NUMERIC:
        value = (out.get(key) or "").replace(",", "").strip()
        out[key] = int(value) if value.lstrip("-").isdigit() else None
    for key in ("character_name", "outfit_title", "earned_title", "rank"):
        out[key] = (out.get(key) or "").strip() or None

    apt: dict[str, str] = {}
    for part in (raw.get("aptitudes") or "").split(","):
        if ":" in part:
            name, grade = part.split(":", 1)
            name, grade = name.strip().lower(), grade.strip()
            if name and grade:
                apt[name] = grade
    # Keep the unparsed string too — without it a parse failure is
    # indistinguishable from the model returning nothing.
    out["aptitudes_raw"] = raw.get("aptitudes") or ""
    out["aptitudes"] = apt
    return out


def encode(path: pathlib.Path) -> tuple[str, str]:
    """Downsample to MAX_EDGE and return (base64, media_type)."""
    with Image.open(path) as im:
        im = im.convert("RGB")
        if max(im.size) > MAX_EDGE:
            scale = MAX_EDGE / max(im.size)
            im = im.resize((round(im.width * scale), round(im.height * scale)), Image.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=88)
    return base64.standard_b64encode(buf.getvalue()).decode(), "image/jpeg"


def extract(client: Anthropic, path: pathlib.Path, model: str, effort: str) -> dict:
    data, media_type = encode(path)
    response = client.messages.create(
        model=model,
        max_tokens=8000,
        system=SYSTEM,
        # Transcription, not reasoning — low effort keeps this fast and cheap.
        output_config={
            "format": {"type": "json_schema", "schema": SCHEMA},
            "effort": effort,
        },
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": data}},
                    {"type": "text", "text": "Extract this screenshot."},
                ],
            }
        ],
    )
    if response.stop_reason == "refusal":
        raise RuntimeError(f"{path.name}: refused")
    text = next((b.text for b in response.content if b.type == "text"), None)
    if not text:
        raise RuntimeError(f"{path.name}: no text block (stop_reason={response.stop_reason})")
    return {
        "image": path.name,
        "usage": {
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
        },
        **normalize(json.loads(text)),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--images", default="data/umamusume/screenshots")
    parser.add_argument("--out", default="data/umamusume/extracted.jsonl")
    parser.add_argument("--model", default="claude-opus-5")
    parser.add_argument("--effort", default="low", choices=["low", "medium", "high"])
    parser.add_argument("--only", help="comma-separated filenames (for validation samples)")
    parser.add_argument("--limit", type=int, help="stop after N images")
    args = parser.parse_args()

    root = pathlib.Path(args.images)
    out = pathlib.Path(args.out)

    if args.only:
        names = [n.strip() for n in args.only.split(",") if n.strip()]
        images = [root / n for n in names]
        missing = [p.name for p in images if not p.exists()]
        if missing:
            print(f"not found in {root}: {', '.join(missing)}", file=sys.stderr)
            return 1
    else:
        images = sorted(
            p for p in root.iterdir() if p.suffix.lower() in {".jpg", ".jpeg", ".png"}
        )

    # Resume: skip anything already extracted.
    done: set[str] = set()
    if out.exists():
        with out.open() as fh:
            done = {json.loads(line)["image"] for line in fh if line.strip()}
    pending = [p for p in images if p.name not in done]
    if args.limit:
        pending = pending[: args.limit]

    print(f"{len(images)} selected, {len(done)} already done, {len(pending)} to extract")
    if not pending:
        return 0

    client = Anthropic()
    totals = {"input": 0, "output": 0}
    failures = 0

    with out.open("a") as fh:
        for i, path in enumerate(pending, 1):
            try:
                record = extract(client, path, args.model, args.effort)
            except Exception as exc:  # noqa: BLE001 — log and continue the batch
                failures += 1
                print(f"[{i}/{len(pending)}] {path.name}: FAILED {exc}", file=sys.stderr)
                continue
            fh.write(json.dumps(record) + "\n")
            fh.flush()
            totals["input"] += record["usage"]["input_tokens"]
            totals["output"] += record["usage"]["output_tokens"]
            who = record.get("character_name") or "—"
            print(f"[{i}/{len(pending)}] {path.name}: {record['screen_type']:<12} {who}")

    print(f"\ntokens: {totals['input']:,} in / {totals['output']:,} out | failures: {failures}")
    print(f"wrote {out}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
