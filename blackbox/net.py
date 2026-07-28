"""C1 — owner: Aslan.

fetch(url, render=False) -> str. If BRIGHTDATA_API_TOKEN is set, route via the
Bright Data Web Unlocker API (httpx to their endpoint, zone from env);
otherwise plain httpx with an honest User-Agent. Log which path served each
request to data/fetch_log.jsonl - we show that log at the demo (sponsor
visibility). On-disk response cache keyed by URL hash.

Rules-adaptation seam (spec 8): if the 17:00 rules mandate Bright Data for all
data access, this is already the default when the token is present, and the
fetch log is the proof.

Done when
---------
Both paths fetch a plain page; a missing token degrades silently to plain.
"""

from __future__ import annotations

from pathlib import Path  # noqa: F401

__phase__ = "C1"
__owner__ = "Aslan"


def fetch(url: str, render: bool = False) -> str:
    raise NotImplementedError(
        "C1 is not implemented yet — owner: Aslan. See this module's docstring."
    )
