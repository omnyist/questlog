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
import re
import sys
import time

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


def build_params(path: pathlib.Path, model: str, effort: str) -> dict:
    """Request body for one image. Shared by the sync and batch paths so both
    send byte-identical requests — the batch run inherits the validated one."""
    data, media_type = encode(path)
    return {
        "model": model,
        "max_tokens": 8000,
        "system": SYSTEM,
        # Transcription, not reasoning — low effort keeps this fast and cheap.
        "output_config": {
            "format": {"type": "json_schema", "schema": SCHEMA},
            "effort": effort,
        },
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": data}},
                    {"type": "text", "text": "Extract this screenshot."},
                ],
            }
        ],
    }


def to_record(image: str, text: str, input_tokens: int, output_tokens: int) -> dict:
    return {
        "image": image,
        "usage": {"input_tokens": input_tokens, "output_tokens": output_tokens},
        **normalize(json.loads(text)),
    }


def extract(client: Anthropic, path: pathlib.Path, model: str, effort: str) -> dict:
    response = client.messages.create(**build_params(path, model, effort))
    if response.stop_reason == "refusal":
        raise RuntimeError(f"{path.name}: refused")
    text = next((b.text for b in response.content if b.type == "text"), None)
    if not text:
        raise RuntimeError(f"{path.name}: no text block (stop_reason={response.stop_reason})")
    return to_record(path.name, text, response.usage.input_tokens, response.usage.output_tokens)


# Batch requests cap at 256 MB; 390 MB of encoded images needs chunking, and
# the margin covers JSON overhead on top of the base64 itself.
BATCH_BYTES = 180_000_000


def run_batch(
    client: Anthropic,
    images: list[pathlib.Path],
    model: str,
    effort: str,
    out: pathlib.Path,
    state_path: pathlib.Path,
) -> int:
    """Submit images as Batch API jobs (50% cheaper), then poll and collect.

    Batch IDs are persisted, so an interrupted poll resumes instead of
    resubmitting — a resubmit would pay for the same work twice.
    """
    from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
    from anthropic.types.messages.batch_create_params import Request

    state: dict = json.loads(state_path.read_text()) if state_path.exists() else {}
    batch_ids: list[str] = state.get("batch_ids", [])
    # custom_id must match ^[a-zA-Z0-9_-]{1,64}$ — filenames have dots. Keep an
    # explicit map rather than reversing the sanitization, which isn't injective.
    id_map: dict[str, str] = state.get("id_map", {})

    if not batch_ids:
        used: set[str] = set()

        def custom_id_for(name: str) -> str:
            base = re.sub(r"[^a-zA-Z0-9_-]", "_", name)[:64]
            cid, n = base, 1
            while cid in used:
                n += 1
                cid = f"{base[:60]}_{n}"
            used.add(cid)
            id_map[cid] = name
            return cid

        def submit(chunk: list, size: int) -> None:
            b = client.messages.batches.create(requests=chunk)
            batch_ids.append(b.id)
            print(f"submitted {b.id} ({len(chunk)} images, ~{size/1e6:.0f} MB)")

        chunk: list = []
        size = 0
        for path in images:
            params = build_params(path, model, effort)
            approx = len(params["messages"][0]["content"][0]["source"]["data"])
            if chunk and size + approx > BATCH_BYTES:
                submit(chunk, size)
                chunk, size = [], 0
            chunk.append(
                Request(
                    custom_id=custom_id_for(path.name),
                    params=MessageCreateParamsNonStreaming(**params),
                )
            )
            size += approx
        if chunk:
            submit(chunk, size)
        state_path.write_text(json.dumps({"batch_ids": batch_ids, "id_map": id_map}, indent=2))
        print(f"\n{len(batch_ids)} batches submitted; state saved to {state_path}")
    else:
        print(f"resuming {len(batch_ids)} batches from {state_path}")

    # Poll until every batch has ended.
    while True:
        statuses = {bid: client.messages.batches.retrieve(bid).processing_status for bid in batch_ids}
        pending = [b for b, s in statuses.items() if s != "ended"]
        if not pending:
            break
        print(f"  waiting on {len(pending)}/{len(batch_ids)} batches ({', '.join(sorted(set(statuses.values())))})")
        time.sleep(60)

    # Collect. Results arrive in arbitrary order — key on custom_id, never position.
    counts = {"succeeded": 0, "errored": 0, "canceled": 0, "expired": 0}
    totals = {"input": 0, "output": 0}
    with out.open("a") as fh:
        for bid in batch_ids:
            for result in client.messages.batches.results(bid):
                kind = result.result.type
                counts[kind] = counts.get(kind, 0) + 1
                image = id_map.get(result.custom_id, result.custom_id)
                if kind != "succeeded":
                    print(f"  {image}: {kind}", file=sys.stderr)
                    continue
                msg = result.result.message
                text = next((b.text for b in msg.content if b.type == "text"), None)
                if not text:
                    counts["errored"] += 1
                    print(f"  {image}: no text block", file=sys.stderr)
                    continue
                record = to_record(
                    image, text, msg.usage.input_tokens, msg.usage.output_tokens
                )
                fh.write(json.dumps(record) + "\n")
                totals["input"] += record["usage"]["input_tokens"]
                totals["output"] += record["usage"]["output_tokens"]

    print(f"\n{counts}")
    print(f"tokens: {totals['input']:,} in / {totals['output']:,} out")
    print(f"wrote {out}")

    # Retire the state file once collected. Left in place it would make the next
    # run resume these finished batches instead of submitting the new images.
    if not (counts["errored"] or counts["expired"]):
        state_path.replace(state_path.with_suffix(".done.json"))
        print(f"batch state retired to {state_path.with_suffix('.done.json')}")
    return 1 if counts["errored"] or counts["expired"] else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--images", default="data/umamusume/screenshots")
    parser.add_argument("--out", default="data/umamusume/extracted.jsonl")
    parser.add_argument("--model", default="claude-opus-5")
    parser.add_argument("--effort", default="low", choices=["low", "medium", "high"])
    parser.add_argument("--only", help="comma-separated filenames (for validation samples)")
    parser.add_argument("--limit", type=int, help="stop after N images")
    parser.add_argument("--batch", action="store_true", help="use the Batch API (50%% cheaper)")
    parser.add_argument("--state", default="data/umamusume/batch_state.json")
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

    if args.batch:
        return run_batch(client, pending, args.model, args.effort, out, pathlib.Path(args.state))

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
