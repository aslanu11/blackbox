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


def bot_history(bot: str) -> Path:
    """Fight-history tables from a bot's fandom page -> normalised CSV."""
    html = net.fetch(f"{BASE}/{_slug(bot)}")
    try:
        tables = pd.read_html(io.StringIO(html))
    except ValueError:
        tables = []

    rows: list[dict] = []
    for table in tables:
        cols = [str(c).strip().lower() for c in table.columns.get_level_values(-1)]
        table.columns = cols
        # A fight table has an opponent-ish column and a result-ish column.
        opp_col = next((c for c in cols if "opponent" in c or "vs" in c), None)
        res_col = next((c for c in cols if "result" in c or "win/loss" in c or "outcome" in c), None)
        if not opp_col or not res_col:
            continue
        season_col = next((c for c in cols if "season" in c or "event" in c or "year" in c), None)
        time_col = next((c for c in cols if "time" in c or "length" in c), None)
        for _, r in table.iterrows():
            try:
                opponent = str(r[opp_col]).strip()
                result_text = str(r[res_col]).strip()
                if not opponent or opponent.lower() in ("nan", ""):
                    continue
                rows.append(
                    {
                        "bot": bot,
                        "season": str(r[season_col]).strip() if season_col else None,
                        "opponent": opponent,
                        "won": result_text.lower().startswith("w"),
                        "method": _classify_method(result_text),
                        "result_text": result_text,
                        "time": str(r[time_col]).strip() if time_col else None,
                    }
                )
            except (KeyError, TypeError):
                continue  # one bad row never kills the table

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"{_slug(bot).lower()}_history.csv"
    pd.DataFrame(rows).to_csv(out, index=False)
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
