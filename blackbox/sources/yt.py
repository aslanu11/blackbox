"""C2 — owner: Aslan.

download(yt_id): yt-dlp -f "bv*[height<=720]+ba" --merge-output-format mp4 into
  data/raw/. HUMAN-TRIGGERED ONLY - never auto-download in tests or CI.
info(yt_id): --write-info-json --skip-download, then parse out `heatmap`
  (a list of {start_time, end_time, value}, normalised to attention points),
  view_count, like_count, comment_count and chapters.
A missing heatmap warns and returns None - it must not raise.

Done when
---------
Given any public yt_id, info parsing works.
"""

from __future__ import annotations

from pathlib import Path  # noqa: F401

__phase__ = "C2"
__owner__ = "Aslan"


def info(yt_id: str) -> dict:
    raise NotImplementedError(
        "C2 is not implemented yet — owner: Aslan. See this module's docstring."
    )
