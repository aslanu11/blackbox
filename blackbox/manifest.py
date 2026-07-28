"""Manifest loader - the missing seam between the hand-edited registry and the
pipeline's meta.json artifacts.

Every pipeline module reads `S.load_meta(fight_id)`; only the fixture generator
ever wrote one. `bb sync` materializes data/manifest.yaml into
data/processed/<fight_id>/meta.json so real fights enter the pipeline the same
way synthetic ones do. The manifest stays the single hand-edited source (spec
§10); meta.json is derived and safe to regenerate.

Owner: Aslan (the manifest is Aslan-owned per TEAM.md).
"""

from __future__ import annotations

import hashlib

import yaml

from . import schemas as S

#: Brand-ish colors for bots we know; everything else gets a stable palette
#: pick. Only these + recorder orange may be saturated on screen (spec §12).
KNOWN_COLORS: dict[str, str] = {
    "Minotaur": "#D4AF37",
    "Bloodsport": "#1E6FD9",
    "HyperShock": "#2FBF71",
    "HUGE": "#8CC63E",
    "Witch Doctor": "#C0392B",
    "End Game": "#27AE60",
    "Malice": "#E67E22",
    "DeathRoll": "#16A085",
    "Golden Fury": "#F1C40F",
    "Orbitron": "#9B59B6",
    "Cobalt": "#2980B9",
    "The Twins": "#E74C3C",
}

_PALETTE = [
    "#D4AF37", "#1E6FD9", "#2FBF71", "#C0392B", "#9B59B6",
    "#E67E22", "#16A085", "#F1C40F", "#2980B9", "#E74C3C",
]


def color_for(bot: str, taken: set[str]) -> str:
    if bot in KNOWN_COLORS and KNOWN_COLORS[bot] not in taken:
        return KNOWN_COLORS[bot]
    idx = int(hashlib.sha256(bot.encode("utf-8")).hexdigest()[:8], 16)
    for i in range(len(_PALETTE)):
        candidate = _PALETTE[(idx + i) % len(_PALETTE)]
        if candidate not in taken:
            return candidate
    return _PALETTE[idx % len(_PALETTE)]


def load_manifest() -> list[dict]:
    if not S.MANIFEST_PATH.exists():
        raise FileNotFoundError(f"{S.MANIFEST_PATH} not found")
    doc = yaml.safe_load(S.MANIFEST_PATH.read_text(encoding="utf-8")) or {}
    return doc.get("fights") or []


def _to_meta(entry: dict) -> S.FightMeta:
    def _num(key: str) -> float | None:
        v = entry.get(key)
        return None if v in (None, "TODO", "") else float(v)

    bots = [str(b) for b in entry["bots"]]
    taken: set[str] = set()
    colors: dict[str, str] = {}
    for b in bots:
        colors[b] = color_for(b, taken)
        taken.add(colors[b])

    yt_id = entry.get("yt_id")
    return S.FightMeta(
        fight_id=str(entry["fight_id"]),
        episode=entry.get("episode"),
        bots=bots,
        colors=colors,
        result=S.FightResult(
            winner=entry.get("winner"),
            method=entry.get("method"),
            time_s=_num("time_s"),
        ),
        video=S.VideoRef(
            yt_id=None if yt_id in (None, "TODO", "") else str(yt_id),
            fight_start_s=_num("fight_start_s"),
            fight_end_s=_num("fight_end_s"),
        ),
        role=entry.get("role", "proleague"),
    )


def sync() -> list[str]:
    """Materialize every manifest entry into meta.json. Returns fight ids.

    The synthetic fixture is skipped - `bb fixture` owns its meta (and its
    scripted result must never be overwritten by a manifest edit).
    """
    synced: list[str] = []
    for entry in load_manifest():
        if entry.get("synthetic"):
            continue
        meta = _to_meta(entry)
        S.save_meta(meta)
        synced.append(meta.fight_id)
    return synced
