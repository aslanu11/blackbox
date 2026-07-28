"""B3 — owner: Aslan.

P(bots[0] wins)(t) = logistic(w . [control, rolling-30s hit-magnitude
differential, mobility differential]). Hand-tuned weights live in a constants
block at the top of this module. Hard constraint: from KO-5s, ramp the winner's
probability to 0.99. `bb momentum --calibrate` buckets predictions vs outcomes
across the corpus -> reliability curve PNG + Brier score.

Done when
---------
The fixture curve trends toward the KO winner and crosses 0.5 in the right
direction after the mobility break.
"""

from __future__ import annotations

from pathlib import Path  # noqa: F401

__phase__ = "B3"
__owner__ = "Aslan"


def compute(fight_id: str) -> Path:
    raise NotImplementedError(
        "B3 is not implemented yet — owner: Aslan. See this module's docstring."
    )
