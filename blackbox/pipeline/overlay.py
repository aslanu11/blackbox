"""D5 — owner: Pranav.

Burn the overlay into an mp4 with OpenCV/ffmpeg: fading position trails in the
FightMeta bot colours, bot labels, hit-flash rings at event times, mobility
bars, a small momentum needle read from telemetry.json, and a recorder-style
footer reading "COVERAGE 81%  CH1 CH2 CH3". 720p, hero segment only, 90 s max.

Do NOT build a live canvas-over-video overlay in the frontend (spec 2.6) -
the overlay is burned into the file.

Done when
---------
`bb overlay --fight-id fixture-001` produces a watchable mp4 from synthetic data.
"""

from __future__ import annotations

from pathlib import Path  # noqa: F401

__phase__ = "D5"
__owner__ = "Pranav"


def render(fight_id: str) -> Path:
    raise NotImplementedError(
        "D5 is not implemented yet — owner: Pranav. See this module's docstring."
    )
