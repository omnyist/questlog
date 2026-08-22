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

Run:
    uv run python data/umamusume/pull_steam.py
    uv run python data/umamusume/pull_steam.py --dry-run
"""

from __future__ import annotations

import argparse
import base64
import json
import pathlib
import re
import subprocess
import sys

HOST = "alys"
APPID = "3224770"  # Umamusume: Pretty Derby
STEAM_USERDATA = r"C:\Program Files (x86)\Steam\userdata"

# Steam names every screenshot <YYYYMMDDhhmmss>_<n>.<ext>, which is also where
# merge.py reads capture time from. Anything else in the folder isn't ours.
NAME = r"^[0-9]{14}_[0-9]+\.(jpg|jpeg|png)$"

# One multiplexed SSH connection for the whole run: a per-file handshake to a
# Windows host costs more than the transfers do.
SSH_MUX = [
    "-o", "ControlMaster=auto",
    "-o", "ControlPath=~/.ssh/cm-questlog-%r@%h:%p",
    "-o", "ControlPersist=60",
]


def powershell(host: str, script: str) -> str:
    """Run PowerShell on the remote host, encoded to dodge quoting.

    The command crosses fish, ssh, cmd.exe and PowerShell, each with its own
    quoting rules and each willing to mangle a Windows path containing spaces.
    -EncodedCommand takes base64 UTF-16LE and skips all four.
    """
    encoded = base64.b64encode(script.encode("utf-16-le")).decode()
    result = subprocess.run(
        ["ssh", *SSH_MUX, host, f"powershell -NoProfile -EncodedCommand {encoded}"],
        capture_output=True, text=True, timeout=180,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ssh {host} failed: {result.stderr.strip()[:300]}")
    return result.stdout.replace("\r", "")


def remote_screenshot_dir(host: str, appid: str) -> str:
    """Resolve the screenshots path. The Steam account ID is discovered rather
    than configured — it differs per machine and per Steam account."""
    out = powershell(host, f'''
$base = "{STEAM_USERDATA}"
Get-ChildItem $base -Directory | ForEach-Object {{
  $p = Join-Path $_.FullName "760\\remote\\{appid}\\screenshots"
  if (Test-Path $p) {{ Write-Output ("PATH " + $p) }}
}}
''')
    paths = [line[5:].strip() for line in out.splitlines() if line.startswith("PATH ")]
    if not paths:
        raise SystemExit(f"no screenshots folder for appid {appid} on {host}")
    if len(paths) > 1:
        raise SystemExit("multiple Steam accounts have this game; pass --account:\n  " + "\n  ".join(paths))
    # Forward slashes from here on. Modern scp speaks SFTP, where the remote
    # path is used literally instead of being expanded by a remote shell — so
    # backslashes arrive escaped and quotes arrive as part of the filename.
    # Windows accepts forward slashes everywhere, including PowerShell.
    return paths[0].replace("\\", "/")


def remote_files(host: str, directory: str) -> list[str]:
    out = powershell(host, f'''
Get-ChildItem -LiteralPath "{directory}" -File | ForEach-Object {{ Write-Output $_.Name }}
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
    remote = remote_files(args.host, directory)

    mark = args.since or watermark(pathlib.Path(args.extracted))
    # A bare date is the common override; pad it so it compares against a full
    # <YYYYMMDDhhmmss>_<n> name as "the very start of that day".
    if mark and re.fullmatch(r"\d{8}", mark):
        mark = mark + "000000_0"
    missing = [n for n in remote if n > mark] if mark else list(remote)

    print(f"{args.host}: {directory}")
    print(f"high-water mark: {mark or '(none — first run, pulling everything)'}"
          + ("  [--since override]" if args.since else ""))
    print(f"{len(remote)} on Steam, {len(missing)} newer than the mark")
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
        # Deliberately unquoted: under SFTP the path is taken literally, so any
        # quoting added here ends up inside the filename scp looks for. Spaces
        # are safe because this is one argv element, never a shell string.
        source = f"{args.host}:{directory}/{name}"
        result = subprocess.run(["scp", *SSH_MUX, "-q", source, str(dest / name)],
                                capture_output=True, text=True, timeout=120)
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
