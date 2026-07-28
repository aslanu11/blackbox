"""D1 — owner: Pranav.

ffmpeg wrapper: cut the fight clip out of the episode file in data/raw/ using
the FightMeta.video offsets, then extract frames to
data/frames/<fight_id>/track/ at 10 fps and /key/ at 1 fps.

Done when
---------
Frame counts match the expected duration within 2%.
"""

from __future__ import annotations

from pathlib import Path  # noqa: F401

__phase__ = "D1"
__owner__ = "Pranav"


def extract(fight_id: str) -> Path:
    raise NotImplementedError(
        "D1 is not implemented yet — owner: Pranav. See this module's docstring."
    )
