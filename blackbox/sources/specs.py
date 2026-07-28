"""C4 - owner: Aslan.

battlebots.com roster page -> bot name, weapon type, team, country ->
data/bots.csv. The weapon taxonomy is schemas.WEAPON_CLASSES.

Done when
---------
At least 20 of the 24 Pro League bots resolve with a weapon class.
"""

from __future__ import annotations

import csv
import re
from pathlib import Path

from .. import net
from .. import schemas as S

__phase__ = "C4"
__owner__ = "Aslan"

ROSTER_URL = "https://battlebots.com/robots/"

#: keyword -> weapon class, checked in order (first match wins).
_WEAPON_KEYWORDS: list[tuple[str, str]] = [
    ("vertical spinner", "vertical_spinner"),
    ("vert spinner", "vertical_spinner"),
    ("vertical disc", "vertical_spinner"),
    ("horizontal spinner", "horizontal_spinner"),
    ("horizontal bar", "horizontal_spinner"),
    ("undercutter", "horizontal_spinner"),
    ("shell spinner", "horizontal_spinner"),
    ("ring spinner", "horizontal_spinner"),
    ("drum", "drum"),
    ("eggbeater", "drum"),
    ("beater", "drum"),
    ("flipper", "flipper"),
    ("launcher", "flipper"),
    ("hammer saw", "hammer"),
    ("hammersaw", "hammer"),
    ("hammer", "hammer"),
    ("axe", "hammer"),
    ("crusher", "crusher"),
    ("grabber", "crusher"),
    ("gripper", "crusher"),
    ("clamp", "crusher"),
    ("lifter", "control"),
    ("wedge", "control"),
    ("plow", "control"),
    ("plough", "control"),
    ("pusher", "control"),
    ("spinner", "vertical_spinner"),  # generic fallback, last
]


def classify_weapon(description: str) -> str:
    d = description.lower()
    for keyword, cls in _WEAPON_KEYWORDS:
        if keyword in d:
            assert cls in S.WEAPON_CLASSES
            return cls
    return "other"


def parse_roster(html: str) -> list[dict]:
    """Best-effort roster extraction. Fandom-grade HTML changes often; every
    selector here is defensive and a miss just drops one bot, not the run."""
    bots: list[dict] = []
    # Robot cards on battlebots.com render as headings/links to /robots/<slug>.
    for m in re.finditer(
        r'href="[^"]*/robots?/(?P<slug>[a-z0-9-]+)/?"[^>]*>(?P<name>[^<]{2,40})<',
        html,
        re.IGNORECASE,
    ):
        name = re.sub(r"\s+", " ", m.group("name")).strip()
        if not name or name.lower() in ("robots", "the robots", "meet the robots"):
            continue
        # Weapon/team/country: look in a window after the card anchor.
        window = html[m.end() : m.end() + 1500]
        weapon_m = re.search(r"weapon(?:\s+type)?\s*:?\s*(?:<[^>]*>\s*)*([^<]{3,60})", window, re.IGNORECASE)
        team_m = re.search(r"team\s*:?\s*(?:<[^>]*>\s*)*([^<]{3,60})", window, re.IGNORECASE)
        entry = {
            "name": name,
            "weapon_text": weapon_m.group(1).strip() if weapon_m else "",
            "weapon_class": classify_weapon(weapon_m.group(1) if weapon_m else name),
            "team": team_m.group(1).strip() if team_m else None,
        }
        if entry["name"].lower() not in {b["name"].lower() for b in bots}:
            bots.append(entry)
    return bots


def roster(url: str = ROSTER_URL) -> Path:
    html = net.fetch(url)
    bots = parse_roster(html)
    out = S.DATA_DIR / "bots.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["name", "weapon_class", "weapon_text", "team"])
        writer.writeheader()
        writer.writerows(bots)
    print(f"  {len(bots)} bots -> {out}")
    return out
