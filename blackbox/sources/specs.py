"""C4 — owner: Aslan.

battlebots.com roster page -> bot name, weapon type, team, country ->
data/bots.csv. The weapon taxonomy is schemas.WEAPON_CLASSES.

Done when
---------
At least 20 of the 24 Pro League bots resolve with a weapon class.
"""

from __future__ import annotations

from pathlib import Path  # noqa: F401

__phase__ = "C4"
__owner__ = "Aslan"


def roster() -> Path:
    raise NotImplementedError(
        "C4 is not implemented yet — owner: Aslan. See this module's docstring."
    )
