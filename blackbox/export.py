"""E4 — owner: Aslan.

Copy data/processed/* JSON + PNGs + overlay mp4s into web/public/data/ and write
index.json - the manifest of exported fights the frontend loads at startup.

Done when
---------
`bb export && cd web && npm run dev` shows the fixture fight end to end.
"""

from __future__ import annotations

from pathlib import Path  # noqa: F401

__phase__ = "E4"
__owner__ = "Aslan"


def export(fight_id: str | None = None) -> Path:
    raise NotImplementedError(
        "E4 is not implemented yet — owner: Aslan. See this module's docstring."
    )
