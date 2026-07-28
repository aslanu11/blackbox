"""D4 — owner: Pranav.

The CPU baseline, and the DEFAULT path. Per wide shot, two cv2.TrackerCSRT.
First shot: a human clicks each bot once. Later shots: auto re-acquire by
colour-histogram match against the stored bot appearance, falling back to a
click prompt. Drift-check the histogram every 2 s and re-acquire on failure.
Pixel centroids -> homography -> floor metres -> tracks.json, with gaps left
explicit (wide=False frames carry pos=None; never interpolate across a shot).

Done when
---------
The fixture-replay test tracks synthetic moving blobs to under 0.5 m error, and
it runs on an arbitrary real clip without crashing.
"""

from __future__ import annotations

from pathlib import Path  # noqa: F401

__phase__ = "D4"
__owner__ = "Pranav"


def track(fight_id: str, review: bool = False) -> Path:
    raise NotImplementedError(
        "D4 is not implemented yet — owner: Pranav. See this module's docstring."
    )
