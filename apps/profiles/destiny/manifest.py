"""Destiny Manifest Resolver.

The Bungie Manifest is a SQLite database mapping hash IDs to definition data
(activity names, class names, mode names, etc.). Bungie serves it as a zipped
SQLite file via the mobileWorldContentPaths endpoint.

Hash handling: Bungie's in-API hashes are unsigned 32-bit, but the SQLite
manifest stores them as signed 32-bit integers. Values >= 2^31 must be
converted to their signed equivalent for lookup.
"""

from __future__ import annotations

import json
import sqlite3
import zipfile
from pathlib import Path


def signed_hash(h: int) -> int:
    """Convert Bungie unsigned 32-bit hash to signed int for SQLite lookup."""
    return h - (1 << 32) if h >= (1 << 31) else h


def extract_manifest_if_zipped(source: Path) -> Path:
    """If the downloaded manifest is a zip, extract the SQLite file.

    Returns the path to a usable SQLite file.
    """
    with source.open("rb") as f:
        magic = f.read(4)

    if magic[:2] == b"PK":
        with zipfile.ZipFile(source) as zf:
            names = zf.namelist()
            if not names:
                raise ValueError(f"Empty manifest zip: {source}")
            extract_dir = source.parent
            extracted_name = names[0]
            extracted_path = extract_dir / extracted_name
            if not extracted_path.exists():
                zf.extract(extracted_name, extract_dir)
            return extracted_path

    return source


class ManifestResolver:
    """Loads the Destiny manifest SQLite and resolves hashes to names."""

    CLASS_NAMES = {"titan", "hunter", "warlock"}
    RACE_NAMES = {"human", "awoken", "exo"}
    GENDER_NAMES = {"male", "female", "masculine", "feminine"}

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        self._cache: dict[tuple[str, int], dict] = {}

    def close(self) -> None:
        self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def get_definition(self, table: str, hash_id: int) -> dict:
        """Look up a definition by hash, returning {} if not found."""
        key = (table, hash_id)
        if key in self._cache:
            return self._cache[key]

        try:
            cursor = self.conn.execute(
                f"SELECT json FROM {table} WHERE id = ?",
                (signed_hash(hash_id),),
            )
            row = cursor.fetchone()
        except sqlite3.OperationalError:
            self._cache[key] = {}
            return {}

        if not row:
            self._cache[key] = {}
            return {}

        data = json.loads(row["json"])
        self._cache[key] = data
        return data

    def _display_name(self, defn: dict) -> str:
        return defn.get("displayProperties", {}).get("name", "")

    def resolve_activity(self, activity_hash: int) -> dict:
        """Returns a dict with name, mode_type, mode_types, activity_type_hash."""
        defn = self.get_definition("DestinyActivityDefinition", activity_hash)
        return {
            "name": self._display_name(defn),
            "mode_type": defn.get("directActivityModeType"),
            "mode_types": defn.get("activityModeTypes", []),
            "activity_type_hash": defn.get("activityTypeHash"),
            "director_activity_hash": defn.get("directActivityHash"),
        }

    def resolve_activity_mode(self, mode_hash: int) -> str:
        defn = self.get_definition("DestinyActivityModeDefinition", mode_hash)
        return self._display_name(defn)

    def resolve_class(self, class_hash: int) -> str:
        defn = self.get_definition("DestinyClassDefinition", class_hash)
        return self._display_name(defn).lower()

    def resolve_race(self, race_hash: int) -> str:
        defn = self.get_definition("DestinyRaceDefinition", race_hash)
        return self._display_name(defn).lower()

    def resolve_gender(self, gender_hash: int) -> str:
        defn = self.get_definition("DestinyGenderDefinition", gender_hash)
        return self._display_name(defn).lower()


# Bungie mode enum → simplified category used on Activity.mode_category.
# Reference: DestinyActivityModeType in the Bungie API.
# Full sunken list at https://bungie-net.github.io/multi/schema_Destiny-HistoricalStats-Definitions-DestinyActivityModeType.html
MODE_CATEGORY_MAP: dict[int, str] = {
    2: "story",
    3: "strike",
    4: "raid",
    5: "crucible",
    6: "patrol",
    7: "story",  # AllPvE bucket — treated as story fallback
    10: "crucible",
    12: "crucible",
    15: "crucible",
    16: "story",
    17: "nightfall",
    18: "strike",
    19: "ironbanner",
    25: "crucible",
    31: "crucible",
    32: "crucible",
    37: "crucible",
    38: "crucible",
    39: "trials",
    40: "social",
    41: "crucible",
    42: "crucible",
    43: "crucible",
    44: "crucible",
    45: "crucible",
    46: "nightfall",
    47: "nightfall",
    48: "crucible",
    49: "crucible",
    50: "crucible",
    51: "crucible",
    52: "crucible",
    53: "crucible",
    54: "crucible",
    55: "crucible",
    56: "crucible",
    57: "crucible",
    58: "crucible",
    59: "crucible",
    60: "crucible",
    61: "crucible",
    62: "crucible",
    63: "gambit",
    64: "gambit",
    65: "crucible",
    66: "crucible",
    67: "crucible",
    68: "crucible",
    69: "crucible",
    70: "crucible",
    71: "crucible",
    72: "crucible",
    73: "crucible",
    74: "crucible",
    75: "gambit",
    76: "crucible",
    77: "crucible",
    78: "crucible",
    79: "nightfall",
    80: "crucible",
    81: "crucible",
    82: "dungeon",
    83: "nightfall",
    84: "trials",
}


def mode_category_for(modes: list[int] | None, fallback_mode: int | None = None) -> str:
    """Pick the best simplified category for a list of mode types.

    Priority order is narrower categories first (raid > dungeon > trials > ...).
    """
    if not modes and fallback_mode is not None:
        modes = [fallback_mode]
    if not modes:
        return "other"

    priority = [
        "raid",
        "dungeon",
        "trials",
        "ironbanner",
        "nightfall",
        "gambit",
        "strike",
        "crucible",
        "story",
        "patrol",
        "social",
    ]
    mapped = [MODE_CATEGORY_MAP.get(m) for m in modes if m is not None]
    for cat in priority:
        if cat in mapped:
            return cat
    return "other"
