"""C2 - owner: Aslan.

download(yt_id): yt-dlp into data/raw/. HUMAN-TRIGGERED ONLY - never called
from tests or CI (spec §9.2).
info(yt_id): metadata only - parses out the "most replayed" heatmap (the
audience-attention signal this whole product runs on), view/like/comment
counts and chapters. A missing heatmap warns and returns None; plenty of
videos simply don't have one.

Done when
---------
Given any public yt_id, info parsing works.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from .. import schemas as S

__phase__ = "C2"
__owner__ = "Aslan"

FORMAT = "bv*[height<=720]+ba"


def _run(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "yt_dlp", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def download(yt_id: str) -> Path:
    """Download the episode video into data/raw/<yt_id>.mp4. Human-triggered."""
    S.RAW_DIR.mkdir(parents=True, exist_ok=True)
    out = S.RAW_DIR / f"{yt_id}.mp4"
    if out.exists():
        return out
    proc = _run(
        [
            "-f", FORMAT,
            "--merge-output-format", "mp4",
            "-o", str(S.RAW_DIR / f"{yt_id}.%(ext)s"),
            f"https://www.youtube.com/watch?v={yt_id}",
        ]
    )
    if proc.returncode != 0:
        raise RuntimeError(f"yt-dlp download failed for {yt_id}:\n{proc.stderr[-2000:]}")
    if not out.exists():
        raise RuntimeError(f"yt-dlp finished but {out} is missing - check data/raw/")
    return out


def info(yt_id: str, force: bool = False) -> dict:
    """Metadata + normalized attention points for one video. No video download.

    Returns::

        { "yt_id", "duration_s", "view_count", "like_count", "comment_count",
          "chapters": [...] | None,
          "heatmap": [[t_seconds, value_0_1], ...] | None }
    """
    S.RAW_DIR.mkdir(parents=True, exist_ok=True)
    info_path = S.RAW_DIR / f"{yt_id}.info.json"

    if not info_path.exists() or force:
        proc = _run(
            [
                "--write-info-json",
                "--skip-download",
                "-o", str(S.RAW_DIR / f"{yt_id}"),
                f"https://www.youtube.com/watch?v={yt_id}",
            ]
        )
        if proc.returncode != 0:
            raise RuntimeError(f"yt-dlp info failed for {yt_id}:\n{proc.stderr[-2000:]}")

    raw = json.loads(info_path.read_text(encoding="utf-8"))
    return parse_info(raw)


def parse_info(raw: dict) -> dict:
    """Pure parser - separated from the network so tests can feed it fixtures."""
    heatmap = normalize_heatmap(raw.get("heatmap"))
    if heatmap is None:
        print(f"  [yt] warning: no most-replayed heatmap for {raw.get('id')}", file=sys.stderr)
    return {
        "yt_id": raw.get("id"),
        "duration_s": raw.get("duration"),
        "view_count": raw.get("view_count"),
        "like_count": raw.get("like_count"),
        "comment_count": raw.get("comment_count"),
        "chapters": raw.get("chapters"),
        "heatmap": heatmap,
    }


def normalize_heatmap(heatmap: list | None) -> list[list[float]] | None:
    """yt-dlp heatmap entries {start_time, end_time, value} -> [[t, v], ...].

    t is the bucket midpoint in episode seconds; v is normalized to peak 1.0.
    """
    if not heatmap:
        return None
    points: list[list[float]] = []
    for entry in heatmap:
        try:
            t = (float(entry["start_time"]) + float(entry["end_time"])) / 2.0
            points.append([round(t, 2), float(entry["value"])])
        except (KeyError, TypeError, ValueError):
            continue
    if not points:
        return None
    peak = max(v for _, v in points)
    if peak <= 0:
        return None
    return [[t, round(v / peak, 4)] for t, v in points]


def attention_for_fight(fight_id: str) -> Path:
    """Cut the episode heatmap down to fight-local time -> attention.json."""
    meta = S.load_meta(fight_id)
    if not meta.video.yt_id:
        raise RuntimeError(f"{fight_id}: no yt_id in the manifest yet (human task, spec 9.1)")
    if meta.video.fight_start_s is None or meta.video.fight_end_s is None:
        raise RuntimeError(f"{fight_id}: fight_start_s/fight_end_s missing from the manifest")

    data = info(meta.video.yt_id)
    if not data["heatmap"]:
        raise RuntimeError(f"{fight_id}: video {meta.video.yt_id} has no most-replayed heatmap")

    t0, t1 = meta.video.fight_start_s, meta.video.fight_end_s
    local = [[round(t - t0, 2), v] for t, v in data["heatmap"] if t0 <= t <= t1]
    if not local:
        raise RuntimeError(f"{fight_id}: heatmap has no points inside {t0}-{t1}s")

    vals = [v for _, v in local]
    baseline = sorted(vals)[max(int(len(vals) * 0.2) - 1, 0)]  # 20th pct, per DECISIONS.md
    peak_t, peak = max(local, key=lambda p: p[1])

    attention = S.Attention(
        video_id=meta.video.yt_id,
        fight_id=fight_id,
        points=local,
        stats=S.AttentionStats(baseline=round(baseline, 4), peak=round(peak, 4), peak_t=peak_t),
        event_lift=[],  # B5 fills this
    )
    return S.save_attention(attention)
