"""D3 — owner: Pranav.

OpenCV click-tool: a human clicks 4+ known floor points on a chosen wide frame
(print the 48 ft box diagram first: corners, screw hazards). Computes the
homography, saves calibration.json, prints the reprojection error. --check
overlays the projected floor grid for eyeball validation.

The clicking is a HUMAN task (spec 9.3). This module provides the tool.

Done when
---------
A synthetic test with a known H recovers points to under 2% error.
"""

from __future__ import annotations

from pathlib import Path  # noqa: F401

__phase__ = "D3"
__owner__ = "Pranav"


def calibrate(fight_id: str, check: bool = False) -> Path:
    raise NotImplementedError(
        "D3 is not implemented yet — owner: Pranav. See this module's docstring."
    )
