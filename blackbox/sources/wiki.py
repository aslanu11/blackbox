"""C3 — owner: Aslan.

battlebots.fandom.com, fetched through net.fetch:
(a) bot page -> fight-history tables (pandas.read_html) -> a normalised CSV
    (season, opponent, result, method KO/JD, time).
(b) Pro League episode pages -> fight cards + results -> FightMeta patches for
    data/manifest.yaml.
Malformed tables are skipped, not fatal.

Done when
---------
Parses one bot page and one episode page from the live site.
"""

from __future__ import annotations

from pathlib import Path  # noqa: F401

__phase__ = "C3"
__owner__ = "Aslan"


def bot_history(bot: str) -> Path:
    raise NotImplementedError(
        "C3 is not implemented yet — owner: Aslan. See this module's docstring."
    )
