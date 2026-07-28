"""D1 — owner: Pranav.

ffmpeg wrapper: cut the fight clip out of the episode file in data/raw/ using
the FightMeta.video offsets, then extract frames to
data/frames/<fight_id>/track/ at 10 fps and /key/ at 1 fps.

Frames are numbered 0-based (``-start_number 0``) so frame index i lines up
with t = i / fps everywhere downstream (shots.py's keyframe lookup, track.py's
frame enumeration).

Done when
---------
Frame counts match the expected duration within 2%.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from .. import schemas as S

__phase__ = "D1"
__owner__ = "Pranav"

#: Frame extraction rates, matching schemas.Tracks.fps (track) and shots.py's
#: keyframe lookup (key).
TRACK_FPS = 10
KEY_FPS = 1

VIDEO_EXTS = (".mp4", ".mkv", ".webm", ".mov", ".avi")


def _run_ffmpeg(args: list[str]) -> None:
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("ffmpeg not found on PATH — run `bb doctor` for install instructions.")
    result = subprocess.run(["ffmpeg", "-y", *args], capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed ({' '.join(args)}):\n{result.stderr[-4000:]}")


def _find_raw_video(fight_id: str, yt_id: str | None) -> Path:
    if not S.RAW_DIR.exists():
        raise FileNotFoundError(f"{S.RAW_DIR} does not exist — download footage with yt-dlp first (see TEAM.md).")

    def _video_files(pattern: str) -> list[Path]:
        return sorted(p for p in S.RAW_DIR.glob(pattern) if p.suffix.lower() in VIDEO_EXTS)

    candidates = _video_files(f"{fight_id}.*") or _video_files(f"{fight_id}*")
    if not candidates and yt_id:
        candidates = _video_files(f"*{yt_id}*")
    if not candidates:
        raise FileNotFoundError(
            f"no raw footage for {fight_id!r} under {S.RAW_DIR} — "
            f"run yt-dlp by hand into data/raw/{fight_id}.mp4 first (see TEAM.md)."
        )
    return candidates[0]


def _extract_frames(clip_path: Path, out_dir: Path, fps: int) -> int:
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    _run_ffmpeg(
        ["-i", str(clip_path), "-vf", f"fps={fps}", "-start_number", "0", str(out_dir / "frame_%06d.jpg")]
    )
    return len(list(out_dir.glob("*.jpg")))


def extract(fight_id: str) -> Path:
    meta = S.load_meta(fight_id)
    start, end = meta.video.fight_start_s, meta.video.fight_end_s
    if start is None or end is None:
        raise ValueError(
            f"{fight_id}: meta.video.fight_start_s/fight_end_s not set — fill data/manifest.yaml first."
        )
    duration = end - start
    if duration <= 0:
        raise ValueError(f"{fight_id}: fight_end_s ({end}) must be after fight_start_s ({start})")

    raw = _find_raw_video(fight_id, meta.video.yt_id)

    clip_path = S.fight_dir(fight_id, create=True) / "clip.mp4"
    _run_ffmpeg(
        ["-i", str(raw), "-ss", str(start), "-to", str(end), "-c:v", "libx264", "-crf", "18", "-c:a", "aac", str(clip_path)]
    )

    track_dir = S.FRAMES_DIR / fight_id / "track"
    key_dir = S.FRAMES_DIR / fight_id / "key"
    n_track = _extract_frames(clip_path, track_dir, TRACK_FPS)
    n_key = _extract_frames(clip_path, key_dir, KEY_FPS)

    expected_track = duration * TRACK_FPS
    off_pct = abs(n_track - expected_track) / expected_track if expected_track else 0.0
    status = "OK" if off_pct <= 0.02 else "WARNING: >2% off expected duration"
    print(f"clip          -> {clip_path}")
    print(f"track frames  -> {track_dir} ({n_track}, expected ~{expected_track:.0f}) [{status}]")
    print(f"key frames    -> {key_dir} ({n_key})")

    return track_dir
