"""D2 — owner: Pranav.

PySceneDetect ContentDetector -> shot list. Classify each shot wide/not-wide:
the primary path is llm.classify_wide(mid_frame) (cached); --heuristic falls
back to low border-region frame-diff variance. Writes shots.json.

Done when
---------
Runs end to end on any mp4; classifications are cached so re-runs cost nothing.
"""

from __future__ import annotations

from pathlib import Path  # noqa: F401

__phase__ = "D2"
__owner__ = "Pranav"


def detect(fight_id: str, heuristic: bool = False) -> Path:
    raise NotImplementedError(
        "D2 is not implemented yet — owner: Pranav. See this module's docstring."
    )
