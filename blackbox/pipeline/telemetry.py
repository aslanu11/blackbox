"""B1 — owner: Aslan.

Savitzky-Golay smoothing on positions, per contiguous wide segment ONLY -
never across a gap. Speed. control(t) = 0.6*center-occupancy-share +
0.4*opponent-wall-proximity over a rolling 10 s. Mobility index =
rolling-30s max speed / that bot's own first-60s baseline. Heatmap PNGs
(matplotlib, transparent background, bot-coloured). All series resampled to 1 Hz.

Done when
---------
Fixture mobility decay for bots[1] is detected within 5 s of the scripted onset.
"""

from __future__ import annotations

from pathlib import Path  # noqa: F401

__phase__ = "B1"
__owner__ = "Aslan"


def compute(fight_id: str) -> Path:
    raise NotImplementedError(
        "B1 is not implemented yet — owner: Aslan. See this module's docstring."
    )
