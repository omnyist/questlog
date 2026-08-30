"""Pull new Umamusume screenshots off the Steam machine.

Steam writes screenshots to a deterministic path, so the manual drag-and-drop
step is avoidable for Steam (iOS has no equivalent — those still arrive by
hand).

What counts as new is decided by a high-water mark: the newest Steam screenshot
already present in the extraction. Steam names every file
<YYYYMMDDhhmmss>_<n>, so newest-by-name is newest-by-time and one string
comparison replaces holding the whole history on disk. Nothing here reads the
screenshots directory to decide what to fetch, so the images stay disposable —
delete them after extraction and this still knows where it left off.

Alys ran Windows until 2026-08-27 and this drove PowerShell over ssh; it now
runs CachyOS, so the whole remote side is plain POSIX shell. The reformat took
the local screenshot history with it (Steam does not cloud-sync screenshots),
which is only survivable because extracted.jsonl is the archive, not the images.

Run:
    uv run python data/umamusume/pull_steam.py
    uv run python data/umamusume/pull_steam.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import subprocess
import sys

HOST = "alys"
APPID = "3224770"  # Umamusume: Pretty Derby

# Where Steam keeps userdata on Linux. The first is usually a symlink to the
# second; both are listed because which one exists varies by install method,
# and a Flatpak Steam keeps its own tree entirely.
STEAM_ROOTS = (
    "$HOME/.steam/steam/userdata",
    "$HOME/.local/share/Steam/userdata",
    "$HOME/.var/app/com.valvesoftware.Steam/data/Steam/userdata",
)

# Steam names every screenshot <YYYYMMDDhhmmss>_<n>.<ext>, which is also where
# merge.py reads capture time from. Anything else in the folder isn't ours —
# including the `thumbnails` directory Steam keeps alongside them.
NAME = r"^[0-9]{14}_[0-9]+\.(jpg|jpeg|png)$"

# One multiplexed SSH connection for the whole run: a per-file handshake costs
# more than the transfers do.
SSH_MUX = [
    "-o", "ControlMaster=auto",
    "-o", "ControlPath=~/.ssh/cm-questlog-%r@%h:%p",
    "-o", "ControlPersist=60",
]


def remote(host: str, script: str) -> str:
    """Run a POSIX shell script on the remote host.

    The script goes over stdin to `sh -s` rather than as arguments. Every Linux
    box on this rack logs in to fish, so anything passed as a command string is
    parsed by fish first — and bash-isms fail there as syntax errors rather than
    doing nothing visible. Feeding stdin to an explicit `sh` sidesteps the login
    shell entirely, and no quoting has to survive two parsers.
    """
    result = subprocess.run(
        ["ssh", *SSH_MUX, host, "sh", "-s"],
        input=script, capture_output=True, text=True, timeout=180,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ssh {host} failed: {result.stderr.strip()[:300]}")
    return result.stdout


def remote_screenshot_dir(host: str, appid: str) -> str:
    """Resolve the screenshots path.

    The Steam account ID is discovered rather than configured — it differs per
    machine and per account, and hardcoding it is what would break on the next
    reinstall.
    """
    roots = " ".join(f'"{r}"' for r in STEAM_ROOTS)
    out = remote(host, f'''
for root in {roots}; do
  [ -d "$root" ] || continue
  for dir in "$root"/*/760/remote/{appid}/screenshots; do
    [ -d "$dir" ] && echo "PATH $dir"
  done
done
# The loop's status is the last test's, and the last entry may well be a
# directory (Steam keeps `thumbnails` here) — without this the script
# reports failure having printed a perfectly good listing.
exit 0
''')
    paths = sorted({line[5:].strip() for line in out.splitlines() if line.startswith("PATH ")})
    if not paths:
        raise SystemExit(f"no screenshots folder for appid {appid} on {host}")
    if len(paths) > 1:
        # Not necessarily an error: ~/.steam/steam is usually a symlink to
        # ~/.local/share/Steam, so the same directory can surface twice. Only
        # genuinely distinct inodes are ambiguous.
        distinct = remote(host, "\n".join(f'stat -Lc "%d:%i {p}" "{p}"' for p in paths))
        inodes = {line.split(" ", 1)[0] for line in distinct.splitlines() if line.strip()}
        if len(inodes) > 1:
            raise SystemExit("multiple Steam accounts have this game:\n  " + "\n  ".join(paths))
    return paths[0]


def remote_files(host: str, directory: str) -> list[str]:
    out = remote(host, f'''
cd "{directory}" || exit 1
for f in *; do
  [ -f "$f" ] && echo "$f"
done
# The loop's status is the last test's, and the last entry may well be a
# directory (Steam keeps `thumbnails` here) — without this the script
# reports failure having printed a perfectly good listing.
exit 0
''')
    pattern = re.compile(NAME, re.IGNORECASE)
    return sorted(n.strip() for n in out.splitlines() if pattern.match(n.strip()))


def watermark(extracted: pathlib.Path) -> str | None:
    """Newest Steam screenshot already extracted, or None for a first run.

    Only Steam-named files count. iOS screenshots live in the same extraction
    as IMG_####.PNG, and "I" sorts above every digit — letting one in would
    park the mark above every possible Steam name and silently pull nothing
    ever again.
    """
    if not extracted.exists():
        return None
    pattern = re.compile(NAME, re.IGNORECASE)
    with extracted.open() as fh:
        names = [json.loads(line)["image"] for line in fh if line.strip()]
    steam = [n for n in names if pattern.match(n)]
    return max(steam) if steam else None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--host", default=HOST)
    ap.add_argument("--appid", default=APPID)
    ap.add_argument("--dest", default="data/umamusume/screenshots")
    ap.add_argument("--extracted", default="data/umamusume/extracted.jsonl")
    ap.add_argument("--since", metavar="NAME_OR_DATE",
                    help="override the high-water mark: a filename or a YYYYMMDD date. "
                         "Use to backfill screenshots older than the newest extracted one, "
                         "which the mark alone will skip.")
    ap.add_argument("--limit", type=int, help="copy at most N (oldest first)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    dest = pathlib.Path(args.dest)
    directory = remote_screenshot_dir(args.host, args.appid)
    remote_list = remote_files(args.host, directory)

    mark = args.since or watermark(pathlib.Path(args.extracted))
    # A bare date is the common override; pad it so it compares against a full
    # <YYYYMMDDhhmmss>_<n> name as "the very start of that day".
    if mark and re.fullmatch(r"\d{8}", mark):
        mark = mark + "000000_0"
    missing = [n for n in remote_list if n > mark] if mark else list(remote_list)

    print(f"{args.host}: {directory}")
    print(f"high-water mark: {mark or '(none — first run, pulling everything)'}"
          + ("  [--since override]" if args.since else ""))
    print(f"{len(remote_list)} on Steam, {len(missing)} newer than the mark")
    if args.limit:
        missing = missing[: args.limit]
        print(f"limited to {len(missing)}")
    if not missing:
        return 0
    print(f"  {missing[0]} … {missing[-1]}")

    if args.dry_run:
        print("dry run: nothing copied")
        return 0

    dest.mkdir(parents=True, exist_ok=True)
    copied = failed = 0
    for i, name in enumerate(missing, 1):
        result = subprocess.run(
            ["scp", *SSH_MUX, "-q", f"{args.host}:{directory}/{name}", str(dest / name)],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode == 0:
            copied += 1
        else:
            failed += 1
            print(f"  FAILED {name}: {result.stderr.strip()[:160]}", file=sys.stderr)
        if i % 25 == 0 or i == len(missing):
            print(f"  {i}/{len(missing)}")

    print(f"\ncopied {copied} into {dest}" + (f", {failed} failed" if failed else ""))
    print("next: uv run --with pillow python data/umamusume/extract.py --local")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
