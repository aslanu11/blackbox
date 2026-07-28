"""B5 — owner: Aslan.

Map the episode-time heatmap to fight-local attention via the FightMeta offsets.
event_lift = mean attention in a +/-5 s window around each event / the fight
baseline. Then media_value.json across all fights: screen_s = total wide
coverage seconds; attn_index = mean fight attention / episode baseline;
media_value = screen_s * attn_index (document the formula in DECISIONS.md);
perf_score from results.

Done when
---------
Fixture attention bumps give event_lift above 1.5 on the scripted hits and
roughly baseline elsewhere.
"""

from __future__ import annotations

from pathlib import Path  # noqa: F401

__phase__ = "B5"
__owner__ = "Aslan"


def fuse(fight_id: str) -> Path:
    raise NotImplementedError(
        "B5 is not implemented yet — owner: Aslan. See this module's docstring."
    )
