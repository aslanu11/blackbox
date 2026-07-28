"""C1 - owner: Aslan.

fetch(url, render=False) -> str. With BRIGHTDATA_API_TOKEN set, requests route
through the Bright Data Web Unlocker API; without it, plain httpx with an
honest User-Agent. Every request is logged to data/fetch_log.jsonl - which
path served it is sponsor-visible evidence at the demo (spec §8).

On-disk response cache keyed by URL hash: scraping the same page twice is free
and rate-limit-safe.

Done when
---------
Both paths fetch a plain page; a missing token degrades silently to plain.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv

from . import schemas as S

__phase__ = "C1"
__owner__ = "Aslan"

load_dotenv(S.ROOT / ".env")

CACHE_DIR = S.DATA_DIR / "http_cache"
FETCH_LOG = S.DATA_DIR / "fetch_log.jsonl"
USER_AGENT = "BLACKBOX-hackathon/0.1 (BattleBots telemetry research; github.com/aslanu11/blackbox)"
BRIGHTDATA_ENDPOINT = "https://api.brightdata.com/request"
TIMEOUT_S = 30.0


def _token() -> str | None:
    return os.environ.get("BRIGHTDATA_API_TOKEN") or None


def _zone() -> str:
    return os.environ.get("BRIGHTDATA_UNLOCKER_ZONE", "web_unlocker1")


def _cache_path(url: str) -> Path:
    return CACHE_DIR / f"{hashlib.sha256(url.encode('utf-8')).hexdigest()}.html"


def _log(url: str, path_used: str, status: int, cached: bool) -> None:
    FETCH_LOG.parent.mkdir(parents=True, exist_ok=True)
    with FETCH_LOG.open("a", encoding="utf-8") as f:
        f.write(
            json.dumps(
                {
                    "ts": round(time.time(), 1),
                    "url": url,
                    "via": path_used,
                    "status": status,
                    "cached": cached,
                }
            )
            + "\n"
        )


def _fetch_brightdata(url: str, render: bool) -> tuple[str, int]:
    resp = httpx.post(
        BRIGHTDATA_ENDPOINT,
        headers={"Authorization": f"Bearer {_token()}"},
        json={"zone": _zone(), "url": url, "format": "raw", **({"render": True} if render else {})},
        timeout=TIMEOUT_S,
    )
    resp.raise_for_status()
    return resp.text, resp.status_code


def _fetch_plain(url: str) -> tuple[str, int]:
    headers = {"User-Agent": USER_AGENT}
    # EU/UK requests to YouTube get a GDPR interstitial ("Before you continue")
    # instead of the page. SOCS=CAI declines non-essential cookies and skips
    # the interstitial - the privacy-preserving choice, and the only way to
    # reach the actual content non-interactively.
    if "youtube.com" in url:
        headers["Cookie"] = "SOCS=CAI"
    resp = httpx.get(
        url,
        headers=headers,
        follow_redirects=True,
        timeout=TIMEOUT_S,
    )
    resp.raise_for_status()
    return resp.text, resp.status_code


def fetch(url: str, render: bool = False, force: bool = False) -> str:
    """Fetch a URL through whichever path is available, with caching + logging."""
    cache = _cache_path(url)
    if cache.exists() and not force:
        text = cache.read_text(encoding="utf-8")
        if text.strip():  # never serve a cached empty body - refetch instead
            _log(url, "cache", 200, True)
            return text

    if _token():
        try:
            text, status = _fetch_brightdata(url, render)
            via = "brightdata"
        except (httpx.HTTPError, httpx.HTTPStatusError):
            # A venue-claimed token can still be misconfigured; don't strand
            # the pipeline on it.
            text, status = _fetch_plain(url)
            via = "plain-fallback"
        if not text.strip():
            # The Unlocker restricts some targets (YouTube/Google return an
            # empty 200 body on standard zones). The plain path handles them.
            text, status = _fetch_plain(url)
            via = "plain-fallback-empty"
    else:
        text, status = _fetch_plain(url)
        via = "plain"

    if text.strip():  # cache only real content
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache.write_text(text, encoding="utf-8")
    _log(url, via, status, False)
    return text
