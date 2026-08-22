"""Extract structured career-run data from Umamusume end-of-run screenshots.

One vision call per image. Each screenshot self-identifies its screen type, so
non-end-of-run strays classify as "other" and are dropped downstream — no
separate classification pass.

Writes JSONL (one record per image) and is resumable: images already present in
the output file are skipped.

Two backends. The API path is the one that built the archive; `--local` talks to
an LM Studio server instead, which is what the ongoing feed uses — a handful of
screenshots after a career, no reason to pay for those. Both share the prompt,
the encoder, and the output format, so records from either are interchangeable.

Run:
    uv run --with anthropic --with pillow python data/umamusume/extract.py \
        --only IMG_1352.PNG,IMG_1353.PNG --out data/umamusume/sample.jsonl

    uv run --with pillow python data/umamusume/extract.py --local
"""

from __future__ import annotations

import argparse
import base64
import copy
import io
import json
import pathlib
import re
import sys
import time
from typing import TYPE_CHECKING

import httpx
from PIL import Image

if TYPE_CHECKING:
    from anthropic import Anthropic

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

# Shared with merge.py/bench.py so validity checks agree on what a rank is.
KNOWN_RANKS = ("G","F","E","D","C","C+","B","B+","A","A+","S","S+","SS","SS+",
               "UG","UG1","UG2","UG3")
RANK_MIN = {"C+":4_000,"B":6_500,"B+":8_200,"A":10_000,"A+":12_100,"S":14_500,
            "S+":15_900,"SS":17_500,"SS+":19_200,"UG":19_600,"UG1":20_100,
            "UG2":20_500,"UG3":21_000}

NUMERIC = ("rating", "speed", "stamina", "power", "guts", "wit", "fans", "races", "wins")

LOCAL_URL = "http://localhost:1234/v1/chat/completions"
LOCAL_MODEL = "qwen/qwen3-vl-30b"  # benchmarked in bench.py; override with --model

# Observed maxima across the 661-image archive are 3 / 6 / 7. See local_schema().
LOCAL_ARRAY_CAPS = {"major_wins": 8, "support_cards": 8, "legacy_ranks": 10}

APTITUDE_KEYS = ("turf", "dirt", "sprint", "mile", "medium", "long", "front", "pace", "late", "end")
APTITUDE_GRADES = ["S", "A", "B", "C", "D", "E", "F", "G", ""]


def local_schema() -> dict:
    """SCHEMA adjusted for llama.cpp. Both changes are forced, not preferences.

    Numeric fields become real integers. They are strings above only because
    Anthropic caps schema complexity; llama.cpp has no such cap, and a string
    grammar over a field the model wants to emit as a number makes it write the
    literal `", "` instead of the digits — the same model reads them correctly
    with the grammar off.

    Arrays get maxItems. Unbounded, the grammar will accept an array forever and
    a small model loops (`"B", "B", "B", ...`) until max_tokens, returning
    truncated JSON. A cap is what actually ends the loop.

    Aptitudes become a real object for the same reason. Asked for the grid as one
    comma-separated string, a local model returns whatever grid it noticed first
    — usually the five stat grades, which look plausible and are the wrong data
    entirely. Naming the ten fields makes the question unambiguous, and an enum
    of grades leaves no room to answer with something else.
    """
    schema = copy.deepcopy(SCHEMA)
    for key in NUMERIC:
        schema["properties"][key] = {"type": ["integer", "null"]}
    # Fresh dicts: the array fields share one object above, and deepcopy
    # preserves that sharing, so mutating in place would apply one cap to all.
    for key, cap in LOCAL_ARRAY_CAPS.items():
        schema["properties"][key] = {**schema["properties"][key], "maxItems": cap}
    schema["properties"]["aptitudes"] = {
        "type": "object",
        "description": (
            "The Track/Distance/Style aptitude grid. Empty string for any grade "
            "not shown on this screen. These are NOT the Speed/Stamina/Power/"
            "Guts/Wit stat grades."
        ),
        "properties": {k: {"type": "string", "enum": APTITUDE_GRADES} for k in APTITUDE_KEYS},
        "required": list(APTITUDE_KEYS),
        "additionalProperties": False,
    }
    return schema


def normalize(raw: dict) -> dict:
    """Blank strings to None, numeric strings to ints, aptitudes to a dict."""
    out = dict(raw)
    for key in NUMERIC:
        value = out.get(key)
        if isinstance(value, int):
            continue  # already a number: a schema that types these as integers
        value = (value or "").replace(",", "").strip()
        out[key] = int(value) if value.lstrip("-").isdigit() else None
    for key in ("character_name", "outfit_title", "earned_title", "rank"):
        out[key] = (out.get(key) or "").strip() or None

    apt: dict[str, str] = {}
    incoming = raw.get("aptitudes")
    if isinstance(incoming, dict):
        # Already structured: the local schema asks for the grid field by field.
        apt = {k.strip().lower(): v.strip() for k, v in incoming.items() if isinstance(v, str) and v.strip()}
    else:
        for part in (incoming or "").split(","):
            if ":" in part:
                name, grade = part.split(":", 1)
                name, grade = name.strip().lower(), grade.strip()
                if name and grade:
                    apt[name] = grade
    # Keep the unparsed value too — without it a parse failure is
    # indistinguishable from the model returning nothing.
    out["aptitudes_raw"] = incoming if isinstance(incoming, str) else json.dumps(incoming or {})
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


def extract_local(
    path: pathlib.Path,
    model: str,
    url: str,
    timeout: float,
    attempts: int = 3,
) -> dict:
    """One image against an OpenAI-compatible local server (LM Studio).

    Retries raise the temperature rather than repeating the same call: the first
    attempt is greedy, so an identical retry reproduces the identical failure.
    The failure worth retrying is a repetition loop that truncates the JSON, and
    a little sampling noise is what breaks it.
    """
    data, media_type = encode(path)
    schema = local_schema()
    last: Exception | None = None
    for attempt in range(attempts):
        response = httpx.post(
            url,
            timeout=timeout,
            json={
                "model": model,
                "temperature": 0.0 if attempt == 0 else 0.3,
                "max_tokens": 1200,
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {"name": "screen", "strict": True, "schema": schema},
                },
                "messages": [
                    {"role": "system", "content": SYSTEM},
                    {
                        "role": "user",
                        "content": [
                            {"type": "image_url", "image_url": {"url": f"data:{media_type};base64,{data}"}},
                            {"type": "text", "text": "Extract this screenshot."},
                        ],
                    },
                ],
            },
        )
        response.raise_for_status()
        body = response.json()
        usage = body.get("usage") or {}
        try:
            return to_record(
                path.name,
                body["choices"][0]["message"]["content"],
                usage.get("prompt_tokens", 0),
                usage.get("completion_tokens", 0),
            )
        except json.JSONDecodeError as exc:
            last = exc
    raise RuntimeError(f"{path.name}: unparseable JSON after {attempts} attempts ({last})")


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
    parser.add_argument("--model", help=f"default: claude-opus-5, or {LOCAL_MODEL} with --local")
    parser.add_argument("--effort", default="low", choices=["low", "medium", "high"])
    parser.add_argument("--only", help="comma-separated filenames (for validation samples)")
    parser.add_argument("--limit", type=int, help="stop after N images")
    parser.add_argument("--batch", action="store_true", help="use the Batch API (50%% cheaper)")
    parser.add_argument("--state", default="data/umamusume/batch_state.json")
    parser.add_argument("--local", action="store_true",
                        help="extract against a local LM Studio server instead of the API")
    parser.add_argument("--local-url", default=LOCAL_URL)
    parser.add_argument("--local-timeout", type=float, default=600.0)
    args = parser.parse_args()

    if args.local and args.batch:
        print("--batch is an Anthropic Batch API feature; it has no local equivalent", file=sys.stderr)
        return 1
    model = args.model or (LOCAL_MODEL if args.local else "claude-opus-5")

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

    # Imported here, not at module scope, so a fully local run needs neither the
    # anthropic package nor credentials.
    client = None
    if not args.local:
        from anthropic import Anthropic

        client = Anthropic()

    if args.batch:
        return run_batch(client, pending, model, args.effort, out, pathlib.Path(args.state))

    print(f"backend: {'local ' + args.local_url if args.local else 'anthropic api'} | model: {model}")
    totals = {"input": 0, "output": 0}
    failures = 0

    with out.open("a") as fh:
        for i, path in enumerate(pending, 1):
            try:
                if args.local:
                    record = extract_local(path, model, args.local_url, args.local_timeout)
                else:
                    record = extract(client, path, model, args.effort)
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
