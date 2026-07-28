"""C5 - owner: Aslan (28 Jul evening).

League-wide YouTube attention at scale, through Bright Data.

The per-fight attention lane needs a published most-replayed heatmap, which
YouTube only grants some videos. But sponsorship value doesn't care about one
fight: it cares which ROBOTS pull audience across the whole channel. So:

1. Scrape the official BattleBots channel's videos tab (Bright Data path -
   YouTube aggressively blocks datacenter scrapers, this is the Unlocker
   earning its keep) -> video ids, titles, view counts.
2. Match video titles against the 24-bot league roster (data/bots.csv) -
   fight videos are reliably titled "X vs. Y ...".
3. Per matched video, scrape the watch page -> exact view count + the
   most-replayed heatmap when present (peak intensity = how re-watchable
   the video is).
4. Aggregate per bot -> data/processed/sponsorship.json:
     videos, total_views, avg_views, heat_peak (mean over heatmapped videos),
     sponsor_index = (total_views / 1e6) * (1 + heat_peak)
   Formula documented in DECISIONS.md; it rewards reach x re-watchability.

Every fetch goes through net.fetch -> cached + logged to fetch_log.jsonl.
"""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any

from .. import net
from .. import schemas as S

__phase__ = "C5"
__owner__ = "Aslan"

CHANNEL_VIDEOS_URL = "https://www.youtube.com/@BattleBots/videos"
WATCH_URL = "https://www.youtube.com/watch?v={yt_id}"


# --------------------------------------------------------------------------
# Page parsing - YouTube embeds JSON blobs in the initial HTML.
# --------------------------------------------------------------------------


def _extract_json_blob(html: str, marker: str) -> dict | None:
    """Pull the ``var <marker> = {...};`` JSON blob out of a YouTube page by
    brace-counting from the first '{' after the marker."""
    i = html.find(marker)
    if i < 0:
        return None
    start = html.find("{", i)
    if start < 0:
        return None
    depth = 0
    in_str = False
    esc = False
    for j in range(start, min(len(html), start + 8_000_000)):
        ch = html[j]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(html[start : j + 1])
                except json.JSONDecodeError:
                    return None
    return None


def _walk(node: Any, key: str):
    """Yield every value of ``key`` anywhere in a nested dict/list."""
    if isinstance(node, dict):
        if key in node:
            yield node[key]
        for v in node.values():
            yield from _walk(v, key)
    elif isinstance(node, list):
        for v in node:
            yield from _walk(v, key)


def _parse_view_count(text: str) -> int | None:
    """'1,234,567 views' / '123K views' / '1.2M views' -> int."""
    m = re.search(r"([\d,.]+)\s*([KMB])?\s*views", text.replace("\xa0", " "), re.IGNORECASE)
    if not m:
        return None
    num, suffix = m.group(1), (m.group(2) or "").upper()
    try:
        value = float(num.replace(",", "")) if suffix else float(num.replace(",", ""))
    except ValueError:
        return None
    mult = {"": 1, "K": 1_000, "M": 1_000_000, "B": 1_000_000_000}[suffix]
    return int(value * mult)


def channel_videos() -> list[dict]:
    """The channel's videos tab -> [{yt_id, title, views_approx}]."""
    html = net.fetch(CHANNEL_VIDEOS_URL)
    data = _extract_json_blob(html, "ytInitialData")
    if data is None:
        raise RuntimeError("could not parse ytInitialData from the channel page")

    out: list[dict] = []
    seen: set[str] = set()

    # Legacy format: videoRenderer entries.
    for vr in _walk(data, "videoRenderer"):
        vid = vr.get("videoId")
        if not vid or vid in seen:
            continue
        seen.add(vid)
        title = "".join(r.get("text", "") for r in vr.get("title", {}).get("runs", []))
        views_text = vr.get("viewCountText", {}).get("simpleText", "")
        out.append({"yt_id": vid, "title": title, "views_approx": _parse_view_count(views_text)})

    # 2024+ format: lockupViewModel entries (contentId + nested title/metadata).
    for lv in _walk(data, "lockupViewModel"):
        vid = lv.get("contentId")
        if not vid or vid in seen:
            continue
        title = next((t.get("content", "") for t in _walk(lv, "title") if isinstance(t, dict) and t.get("content")), "")
        views = None
        for txt in _walk(lv, "content"):
            if isinstance(txt, str) and "views" in txt:
                views = _parse_view_count(txt)
                if views is not None:
                    break
        if not title:
            continue
        seen.add(vid)
        out.append({"yt_id": vid, "title": title, "views_approx": views})
    return out


def video_stats(yt_id: str) -> dict:
    """One watch page -> exact views + most-replayed heatmap peak (or None)."""
    html = net.fetch(WATCH_URL.format(yt_id=yt_id))

    views = None
    player = _extract_json_blob(html, "ytInitialPlayerResponse")
    if player:
        details = player.get("videoDetails", {})
        try:
            views = int(details.get("viewCount", ""))
        except (TypeError, ValueError):
            views = None

    # Most-replayed markers ship as heatMarkerRenderer entries in the page.
    intensities = [
        float(m)
        for m in re.findall(r'"heatMarkerIntensityScoreNormalized"\s*:\s*([\d.]+)', html)
    ]
    heat_peak = max(intensities) if intensities else None
    return {"yt_id": yt_id, "views": views, "heat_peak": heat_peak, "n_heat_markers": len(intensities)}


# --------------------------------------------------------------------------
# Title -> bot matching
# --------------------------------------------------------------------------


def _roster_names() -> list[str]:
    path = S.DATA_DIR / "bots.csv"
    if not path.exists():
        raise FileNotFoundError("data/bots.csv missing - run `bb roster` (specs.roster) first")
    with path.open(encoding="utf-8") as f:
        return [row["name"] for row in csv.DictReader(f) if row.get("name")]


def match_bots(title: str, roster: list[str]) -> list[str]:
    """Roster bots named in a video title, word-boundary matched."""
    hits = []
    for bot in roster:
        if re.search(rf"(?<![A-Za-z]){re.escape(bot)}(?![A-Za-z])", title, re.IGNORECASE):
            hits.append(bot)
    return hits


# --------------------------------------------------------------------------
# Aggregation
# --------------------------------------------------------------------------


def channel_inventory() -> list[dict]:
    """EVERY upload on the channel via yt-dlp's flat-playlist mode.

    The videos-tab HTML only exposes ~30 entries before JS pagination; the
    per-bot fight uploads live far deeper. yt-dlp walks the continuations for
    us, metadata-only (no video downloaded). Cached to data/yt_channel.json.
    """
    import subprocess

    cache = S.DATA_DIR / "yt_channel.json"
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))

    proc = subprocess.run(
        ["yt-dlp", "--flat-playlist", "-J", CHANNEL_VIDEOS_URL],
        capture_output=True,
        text=True,
        timeout=300,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"yt-dlp flat-playlist failed: {proc.stderr[-300:]}")
    data = json.loads(proc.stdout)
    videos = [
        {
            "yt_id": e.get("id"),
            "title": e.get("title", ""),
            "views_approx": e.get("view_count"),
        }
        for e in data.get("entries", [])
        if e.get("id")
    ]
    cache.write_text(json.dumps(videos, indent=1) + "\n", encoding="utf-8")
    return videos


def sponsorship(max_videos: int = 40) -> Path:
    """Scrape the channel, match titles to bots, aggregate sponsor metrics."""
    roster = _roster_names()
    try:
        videos = channel_inventory()
    except (RuntimeError, FileNotFoundError, OSError) as e:
        print(f"  yt-dlp inventory unavailable ({e}) - falling back to the videos-tab scrape")
        videos = channel_videos()
    print(f"  channel inventory: {len(videos)} videos")

    matched = [(v, bots) for v in videos if (bots := match_bots(v["title"], roster))]
    matched = matched[:max_videos]
    print(f"  {len(matched)} videos name at least one league bot")

    per_bot: dict[str, dict] = {
        b: {"videos": 0, "total_views": 0, "heat_peaks": [], "titles": []} for b in roster
    }
    for v, bots in matched:
        stats = video_stats(v["yt_id"])
        views = stats["views"] or v["views_approx"] or 0
        for b in bots:
            rec = per_bot[b]
            rec["videos"] += 1
            rec["total_views"] += views
            rec["titles"].append(v["title"])
            if stats["heat_peak"] is not None:
                rec["heat_peaks"].append(stats["heat_peak"])

    bots_out = []
    for name, rec in per_bot.items():
        if rec["videos"] == 0:
            continue
        heat = sum(rec["heat_peaks"]) / len(rec["heat_peaks"]) if rec["heat_peaks"] else None
        sponsor_index = round((rec["total_views"] / 1e6) * (1.0 + (heat or 0.0)), 2)
        bots_out.append(
            {
                "name": name,
                "videos": rec["videos"],
                "total_views": rec["total_views"],
                "avg_views": int(rec["total_views"] / rec["videos"]),
                "heat_peak": round(heat, 3) if heat is not None else None,
                "sponsor_index": sponsor_index,
            }
        )
    bots_out.sort(key=lambda b: -b["sponsor_index"])

    out = S.PROCESSED_DIR / "sponsorship.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(
            {"source": "youtube @BattleBots via Bright Data", "n_videos_scraped": len(matched), "bots": bots_out},
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"  {len(bots_out)} bots -> {out}")
    return out
