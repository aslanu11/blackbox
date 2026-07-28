"""C3 - owner: Aslan.

battlebots.fandom.com, fetched through net.fetch:
(a) bot page -> fight-history tables (pandas.read_html) -> a normalised CSV
    (season, opponent, result, method KO/JD, time).
(b) Pro League episode pages -> fight cards + results -> FightMeta patch
    suggestions for data/manifest.yaml (printed, never auto-applied - the
    manifest is hand-edited only, spec 10).
Malformed tables are skipped, not fatal.

Done when
---------
Parses one bot page and one episode page from the live site.
"""

from __future__ import annotations

import io
import re
from pathlib import Path

import pandas as pd

from .. import net
from .. import schemas as S

__phase__ = "C3"
__owner__ = "Aslan"

BASE = "https://battlebots.fandom.com/wiki"
OUT_DIR = S.DATA_DIR / "wiki"


def _slug(name: str) -> str:
    return name.strip().replace(" ", "_")


def _classify_method(result_text: str) -> str | None:
    t = result_text.lower()
    if "ko" in t or "knockout" in t or "knocked out" in t:
        return "ko"
    if "jd" in t or "judge" in t or "decision" in t or "split" in t or "unanimous" in t:
        return "jd"
    return None


def parse_history_tables(bot: str, tables: list[pd.DataFrame]) -> list[dict]:
    """Fandom's fight-history widget renders as 3 columns:

        stage | "vs. Opponent (seed)" | "Won (KO)" / "Lost (Split JD)" / ...

    Season/competition headers are merged rows where all three columns carry
    the same text. Pure function so tests can feed it synthetic tables.
    """
    rows: list[dict] = []
    for table in tables:
        if table.shape[1] != 3:
            continue
        vals = table.fillna("").astype(str).values
        if not any(v[1].strip().lower().startswith("vs.") for v in vals):
            continue
        season = None
        for c0, c1, c2 in vals:
            c0, c1, c2 = c0.strip(), c1.strip(), c2.strip()
            if c0 == c1 == c2 and c0 and not c1.lower().startswith("vs."):
                if c0.upper() != bot.upper():  # skip the bot-name banner row
                    season = re.sub(r"\s+\d+-\d+$", "", c0)  # strip "  2-1" records
                continue
            if not c1.lower().startswith("vs."):
                continue
            opponent = re.sub(r"^vs\.\s*", "", c1, flags=re.IGNORECASE)
            opponent = re.sub(r"\s*\(\d+\)\s*$", "", opponent).strip()  # seed "(3)"
            if not opponent:
                continue
            rows.append(
                {
                    "bot": bot,
                    "season": season,
                    "stage": c0 or None,
                    "opponent": opponent,
                    "won": c2.lower().startswith("w"),
                    "method": _classify_method(c2),
                    "result_text": c2,
                }
            )
    return rows


def bot_history(bot: str) -> Path:
    """Fight-history tables from a bot's fandom page -> normalised CSV."""
    html = net.fetch(f"{BASE}/{_slug(bot)}")
    try:
        tables = pd.read_html(io.StringIO(html))
    except ValueError:
        tables = []
    rows = parse_history_tables(bot, tables)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"{_slug(bot).lower()}_history.csv"
    pd.DataFrame(rows, columns=["bot", "season", "stage", "opponent", "won", "method", "result_text"]).to_csv(out, index=False)
    return out


_FIGHT_LINE = re.compile(
    r"(?P<a>[A-Z][\w .'-]{1,30}?)\s+(?:vs\.?|versus)\s+(?P<b>[A-Z][\w .'-]{1,30})",
    re.IGNORECASE,
)


def episode_card(episode_url_or_title: str) -> list[dict]:
    """Fight card from a Pro League episode page -> manifest patch suggestions.

    Returns a list of {bots: [a, b], winner: str|None} dicts and prints a YAML
    block a human can paste into data/manifest.yaml (never auto-applied).
    """
    url = (
        episode_url_or_title
        if episode_url_or_title.startswith("http")
        else f"{BASE}/{_slug(episode_url_or_title)}"
    )
    html = net.fetch(url)

    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text)

    fights: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for m in _FIGHT_LINE.finditer(text):
        a, b = m.group("a").strip(), m.group("b").strip()
        if len(a) < 2 or len(b) < 2 or a.lower() == b.lower():
            continue
        key = tuple(sorted((a.lower(), b.lower())))
        if key in seen:
            continue
        seen.add(key)
        # Winner: "X defeats Y" / "X def. Y" patterns near this match.
        window = text[max(m.start() - 200, 0) : m.end() + 200]
        winner = None
        beat = re.search(r"([A-Z][\w .'-]{1,30}?)\s+(?:defeat(?:s|ed)?|def\.|beat)\s", window)
        if beat and beat.group(1).strip() in (a, b):
            winner = beat.group(1).strip()
        fights.append({"bots": [a, b], "winner": winner})

    if fights:
        print("# Suggested manifest patch - review before pasting (bots may include noise):")
        for i, f in enumerate(fights, 1):
            print(
                f"  - {{fight_id: TODO-f{i}, episode: TODO, bots: [{f['bots'][0]}, {f['bots'][1]}], "
                f"role: proleague, yt_id: TODO}}"
                + (f"   # winner: {f['winner']}" if f["winner"] else "")
            )
    return fights
