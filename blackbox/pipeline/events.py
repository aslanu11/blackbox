"""B2 — owner: Aslan.

Hit    = joint |dv| spike (both bots, summed above threshold) while separation
         is under 2.5 m. Magnitude = combined dv; actor = higher approach velocity.
KO     = mobility index under 0.15 sustained 10 s, or taken from FightMeta.result.
Hazard = an impulse inside a hazard zone (from the calibration floor map)
         without opponent proximity.

Done when
---------
At least 4 of the 5 fixture hits recovered within 1 s, at most 1 false positive;
KO time within 3 s.
"""

from __future__ import annotations

from pathlib import Path  # noqa: F401

__phase__ = "B2"
__owner__ = "Aslan"


def detect(fight_id: str) -> Path:
    raise NotImplementedError(
        "B2 is not implemented yet — owner: Aslan. See this module's docstring."
    )
