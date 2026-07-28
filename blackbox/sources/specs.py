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


FANDOM = "https://battlebots.fandom.com/wiki"
_LEAGUE_PAGE = f"{FANDOM}/BattleBots_Pro_League"


def league_records() -> dict[str, str]:
    """All 24 Pro League bots + W-L records from the group standings tables."""
    import io

    import pandas as pd

    html = net.fetch(_LEAGUE_PAGE)
    records: dict[str, str] = {}
    for t in pd.read_html(io.StringIO(html)):
        cols = [str(c) for c in t.columns]
        if len(cols) == 3 and "Robot" in cols[1] and "Record" in cols[2]:
            for _, r in t.iterrows():
                records[str(r.iloc[1]).strip()] = str(r.iloc[2]).strip()
    return records


def bot_weapon(bot: str) -> str:
    """Current weapon text from the bot's fandom infobox ('' if not found)."""
    html = net.fetch(f"{FANDOM}/{bot.replace(' ', '_')}")
    m = re.search(
        r"pi-data-label[^>]*>\s*Weapon[^<]*<.*?pi-data-value[^>]*>(.*?)</div>",
        html,
        re.DOTALL,
    )
    if not m:
        return ""
    text = re.sub(r"<[^>]+>", " ", m.group(1))
    return re.sub(r"\s+", " ", text).strip()


def roster(url: str = ROSTER_URL) -> Path:
    """data/bots.csv for the whole league.

    Primary source is the fandom wiki (standings for the roster + records,
    per-bot infobox for the weapon) because battlebots.com renders its roster
    client-side. The battlebots.com parser stays as a fallback.
    """
    out = S.DATA_DIR / "bots.csv"
    out.parent.mkdir(parents=True, exist_ok=True)

    records = league_records()
    bots: list[dict] = []
    if records:
        for name, record in records.items():
            weapon_text = bot_weapon(name)
            bots.append(
                {
                    "name": name,
                    "weapon_class": classify_weapon(weapon_text or name),
                    "weapon_text": weapon_text,
                    "record": record,
                }
            )
        fieldnames = ["name", "weapon_class", "weapon_text", "record"]
    else:  # fandom unreachable - try battlebots.com
        bots = parse_roster(net.fetch(url))
        fieldnames = ["name", "weapon_class", "weapon_text", "team"]

    with out.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(bots)
    print(f"  {len(bots)} bots -> {out}")
    return out
