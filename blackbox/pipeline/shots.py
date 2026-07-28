"""D2 — owner: Pranav.

PySceneDetect ContentDetector -> shot list. Classify each shot wide/not-wide:
the primary path is llm.classify_wide(mid_frame) (cached); --heuristic falls
back to low border-region frame-diff variance. Writes shots.json.

``shots.json`` is a Phase-D-only artifact — not in schemas.py's ``_ARTIFACTS``
(spec §5 only covers cross-phase contracts). It lives at
``data/processed/<fight_id>/shots.json`` alongside the contract files, and is
track.py's (D4) only input besides the raw frames and calibration.json.

Done when
---------
Runs end to end on any mp4; classifications are cached so re-runs cost nothing.
"""

from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np
from pydantic import BaseModel, ConfigDict, Field

from .. import schemas as S

__phase__ = "D2"
__owner__ = "Pranav"

#: Border strip width as a fraction of the shorter frame dimension. A locked
#: -off wide shot has a near-static border (arena wall / crowd barrier);
#: close-ups and handheld shots move a lot at the edges even when the centre
#: is a static face or bot.
_BORDER_FRAC = 0.12
#: Mean per-pixel border frame-diff below this (0-255 scale) reads as "wide".
_HEURISTIC_THRESHOLD = 6.0
#: How many frame pairs to sample per shot when scoring border motion.
_SAMPLE_PAIRS = 6


class Shot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start_t: float
    end_t: float
    wide: bool


class Shots(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fight_id: str
    shots: list[Shot] = Field(default_factory=list)


def shots_path(fight_id: str) -> Path:
    return S.fight_dir(fight_id) / "shots.json"


def save_shots(s: Shots) -> Path:
    path = shots_path(s.fight_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(s.model_dump(mode="json"), indent=2) + "\n", encoding="utf-8")
    return path


def load_shots(fight_id: str) -> Shots:
    path = shots_path(fight_id)
    if not path.exists():
        raise FileNotFoundError(f"{path} not found — run `bb shots --fight-id {fight_id}` first.")
    return Shots.model_validate_json(path.read_text(encoding="utf-8"))


def is_wide(shots: Shots, t: float) -> bool:
    """True if time ``t`` falls inside a shot classified wide."""
    for sh in shots.shots:
        if sh.start_t <= t < sh.end_t:
            return sh.wide
    return False


# --------------------------------------------------------------------------
# Wide-shot classification
# --------------------------------------------------------------------------


def _border_motion_score(frames: list[np.ndarray]) -> float:
    """Mean per-pixel absolute frame-diff inside a border strip, across up to
    ``_SAMPLE_PAIRS`` consecutive pairs sampled evenly through the shot."""
    if len(frames) < 2:
        return 0.0
    h, w = frames[0].shape[:2]
    b = max(2, int(_BORDER_FRAC * min(h, w)))

    def _border(img: np.ndarray) -> np.ndarray:
        mask = np.zeros((h, w), dtype=bool)
        mask[:b, :] = mask[-b:, :] = mask[:, :b] = mask[:, -b:] = True
        return img[mask]

    idxs = np.linspace(0, len(frames) - 2, num=min(_SAMPLE_PAIRS, len(frames) - 1), dtype=int)
    scores = []
    for i in idxs:
        a = cv2.cvtColor(frames[i], cv2.COLOR_BGR2GRAY).astype(np.float32)
        c = cv2.cvtColor(frames[i + 1], cv2.COLOR_BGR2GRAY).astype(np.float32)
        diff = np.abs(_border(a) - _border(c))
        scores.append(float(diff.mean()))
    return float(np.mean(scores))


def classify_wide_heuristic(frames: list[np.ndarray]) -> bool:
    """Low border motion -> a locked-off wide shot of the box."""
    return _border_motion_score(frames) < _HEURISTIC_THRESHOLD


def _classify_shot(mid_frame_path: Path, sample_frames: list[np.ndarray], heuristic: bool) -> bool:
    if not heuristic:
        try:
            from .. import llm

            return llm.classify_wide(str(mid_frame_path))
        except NotImplementedError:
            print(f"llm.classify_wide not implemented yet (A5 pending) — falling back to heuristic for {mid_frame_path.name}")
    return classify_wide_heuristic(sample_frames)


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------


def detect(fight_id: str, heuristic: bool = False) -> Path:
    clip_path = S.fight_dir(fight_id) / "clip.mp4"
    if not clip_path.exists():
        raise FileNotFoundError(f"{clip_path} not found — run `bb ingest --fight-id {fight_id}` first.")

    from scenedetect import ContentDetector, SceneManager, open_video

    video = open_video(str(clip_path))
    manager = SceneManager()
    manager.add_detector(ContentDetector())
    manager.detect_scenes(video=video)
    scene_list = manager.get_scene_list()

    if not scene_list:
        duration_s = video.duration.seconds
        scene_list = [(0.0, duration_s)]
    else:
        scene_list = [(s.seconds, e.seconds) for s, e in scene_list]

    key_dir = S.FRAMES_DIR / fight_id / "key"
    track_dir = S.FRAMES_DIR / fight_id / "track"

    shots: list[Shot] = []
    for start_t, end_t in scene_list:
        mid_t = 0.5 * (start_t + end_t)
        mid_frame_path = _nearest_frame(key_dir, mid_t, fps=1) or _nearest_frame(track_dir, mid_t, fps=10)
        sample_paths = _frames_in_range(track_dir, start_t, end_t, fps=10, limit=_SAMPLE_PAIRS + 1)
        sample_frames = [f for p in sample_paths if (f := cv2.imread(str(p))) is not None]

        if mid_frame_path is None or not sample_frames:
            wide = False
        else:
            wide = _classify_shot(mid_frame_path, sample_frames, heuristic)

        shots.append(Shot(start_t=round(start_t, 3), end_t=round(end_t, 3), wide=wide))

    path = save_shots(Shots(fight_id=fight_id, shots=shots))
    n_wide = sum(s.wide for s in shots)
    print(f"{len(shots)} shots, {n_wide} wide -> {path}")
    return path


def _nearest_frame(frame_dir: Path, t: float, fps: int) -> Path | None:
    if not frame_dir.exists():
        return None
    idx = int(round(t * fps))
    candidate = frame_dir / f"frame_{idx:06d}.jpg"
    if candidate.exists():
        return candidate
    frames = sorted(frame_dir.glob("*.jpg"))
    return frames[-1] if frames else None


def _frames_in_range(frame_dir: Path, start_t: float, end_t: float, fps: int, limit: int) -> list[Path]:
    if not frame_dir.exists():
        return []
    lo, hi = int(start_t * fps), max(int(start_t * fps) + 1, int(end_t * fps))
    idxs = np.linspace(lo, hi - 1, num=min(limit, max(1, hi - lo)), dtype=int)
    out = []
    for i in idxs:
        p = frame_dir / f"frame_{i:06d}.jpg"
        if p.exists():
            out.append(p)
    return out
