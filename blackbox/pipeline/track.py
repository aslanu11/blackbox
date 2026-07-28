"""D4 — owner: Pranav.

The CPU baseline, and the DEFAULT path. Per wide shot, two cv2.TrackerCSRT.
First shot: a human clicks each bot once. Later shots: auto re-acquire by
colour-histogram match against the stored bot appearance, falling back to a
click prompt. Drift-check the histogram every 2 s and re-acquire on failure.
Pixel centroids -> homography -> floor metres -> tracks.json, with gaps left
explicit (wide=False frames carry pos=None; never interpolate across a shot).

Reads (all Pranav's own D-phase artifacts, see shots.py / calibrate.py):
* ``data/frames/<fight_id>/track/*.jpg`` — 10 fps frames from D1.
* ``shots.json`` — wide/not-wide shot list from D2.
* ``calibration.json`` — image -> floor homography from D3.

Done when
---------
The fixture-replay test tracks synthetic moving blobs to under 0.5 m error, and
it runs on an arbitrary real clip without crashing.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

import cv2
import numpy as np

from . import calibrate as C
from . import shots as SH
from .. import schemas as S

__phase__ = "D4"
__owner__ = "Pranav"

#: Frames per second of the extracted track frames (matches D1 and schemas.Tracks.fps).
FPS = 10
#: How often to sanity-check a tracker against its stored appearance.
DRIFT_CHECK_EVERY_S = 2.0
#: Histogram correlation below this reads as "the tracker drifted".
DRIFT_CORRELATION_MIN = 0.35
#: Default click-box half-size in pixels, used when a human clicks a centre
#: point rather than dragging a full box (see ``_click_boxes``).
DEFAULT_BOX_HALF = 28

BBox = tuple[int, int, int, int]  # x, y, w, h

Frame = np.ndarray

# --------------------------------------------------------------------------
# Tracker construction — cv2's CSRT constructor has moved package/namespace
# across releases; try every known spelling rather than pin to one.
# --------------------------------------------------------------------------


def _new_csrt_tracker():
    for factory in (
        lambda: cv2.TrackerCSRT_create(),
        lambda: cv2.legacy.TrackerCSRT_create(),  # type: ignore[attr-defined]
        lambda: cv2.TrackerCSRT.create(),  # type: ignore[attr-defined]
    ):
        try:
            return factory()
        except (AttributeError, cv2.error):
            continue
    raise RuntimeError(
        "no cv2.TrackerCSRT constructor found — this OpenCV build lacks the tracking module"
    )


# --------------------------------------------------------------------------
# Colour-histogram appearance model, used for drift checks and re-acquisition.
# --------------------------------------------------------------------------


def _bbox_hist(frame: Frame, bbox: BBox) -> np.ndarray:
    x, y, w, h = bbox
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(frame.shape[1], x + w), min(frame.shape[0], y + h)
    crop = frame[y0:y1, x0:x1]
    if crop.size == 0:
        return np.zeros((30, 32), dtype=np.float32)
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    hist = cv2.calcHist([hsv], [0, 1], None, [30, 32], [0, 180, 0, 256])
    cv2.normalize(hist, hist, 0, 1, cv2.NORM_MINMAX)
    return hist


def _hist_similarity(a: np.ndarray, b: np.ndarray) -> float:
    return float(cv2.compareHist(a, b, cv2.HISTCMP_CORREL))


def _reacquire(frame: Frame, ref_hist: np.ndarray, box_size: tuple[int, int]) -> BBox | None:
    """Search the whole frame for the best match to ``ref_hist`` via
    histogram back-projection. Returns a bbox, or None if nothing convincing
    is found."""
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    back = cv2.calcBackProject([hsv], [0, 1], ref_hist, [0, 180, 0, 256], 1)
    disc = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))
    back = cv2.filter2D(back, -1, disc)
    _thr, mask = cv2.threshold(back, 50, 255, cv2.THRESH_BINARY)
    contours, _ = cv2.findContours(mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None
    best = max(contours, key=cv2.contourArea)
    min_area = 0.25 * box_size[0] * box_size[1]
    if cv2.contourArea(best) < min_area:
        return None
    x, y, w, h = cv2.boundingRect(best)
    return (x, y, max(w, box_size[0] // 2), max(h, box_size[1] // 2))


# --------------------------------------------------------------------------
# Interactive seeding — the human click, per spec 9.3.
# --------------------------------------------------------------------------


def _click_boxes(frame: Frame, bot_names: list[str]) -> dict[str, BBox]:
    """cv2.selectROI once per bot, prompted by name."""
    boxes: dict[str, BBox] = {}
    for bot in bot_names:
        window = f"bb track — drag a box around {bot}, enter to confirm"
        r = cv2.selectROI(window, frame, showCrosshair=True, fromCenter=False)
        cv2.destroyWindow(window)
        x, y, w, h = (int(v) for v in r)
        if w == 0 or h == 0:
            w = h = 2 * DEFAULT_BOX_HALF
        boxes[bot] = (x, y, w, h)
    return boxes


ClickFn = Callable[[Frame, list[str]], dict[str, BBox]]

# --------------------------------------------------------------------------
# Per-segment tracking
# --------------------------------------------------------------------------


def _bbox_center(bbox: BBox) -> tuple[float, float]:
    x, y, w, h = bbox
    return (x + w / 2.0, y + h / 2.0)


def _track_segment(
    frame_paths: list[Path],
    start_idx: int,
    bot_names: list[str],
    H: np.ndarray,
    appearance: dict[str, np.ndarray],
    click_fn: ClickFn,
    fps: int = FPS,
) -> tuple[list[S.TrackFrame], dict[str, np.ndarray]]:
    """Track every bot across one contiguous run of wide frames.

    ``appearance`` maps bot -> reference HSV histogram, carried in from the
    previous wide segment (empty on the fight's first segment). Returns the
    frames plus the updated appearance dict for the *next* segment.
    """
    if not frame_paths:
        return [], appearance

    first = cv2.imread(str(frame_paths[0]))
    if first is None:
        raise RuntimeError(f"could not read {frame_paths[0]}")

    boxes: dict[str, BBox] = {}
    box_size: dict[str, tuple[int, int]] = {}
    trackers: dict[str, object] = {}
    for bot in bot_names:
        ref = appearance.get(bot)
        found = None
        if ref is not None:
            guess_size = box_size.get(bot, (2 * DEFAULT_BOX_HALF, 2 * DEFAULT_BOX_HALF))
            found = _reacquire(first, ref, guess_size)
        if found is None:
            clicked = click_fn(first, [bot])
            found = clicked[bot]
        boxes[bot] = found
        box_size[bot] = (found[2], found[3])
        tracker = _new_csrt_tracker()
        tracker.init(first, found)
        trackers[bot] = tracker
        appearance[bot] = _bbox_hist(first, found)

    drift_every = max(1, int(round(DRIFT_CHECK_EVERY_S * fps)))
    out: list[S.TrackFrame] = []

    for i, path in enumerate(frame_paths):
        t = round((start_idx + i) / fps, 2)
        frame = first if i == 0 else cv2.imread(str(path))
        pos: dict[str, list[float]] = {}

        if frame is None:
            out.append(S.TrackFrame(t=t, wide=True, pos=None))
            continue

        for bot in bot_names:
            ok, bbox = (True, boxes[bot]) if i == 0 else trackers[bot].update(frame)
            bbox = tuple(int(v) for v in bbox) if ok else None

            if ok and i > 0 and i % drift_every == 0:
                cur_hist = _bbox_hist(frame, bbox)
                if _hist_similarity(cur_hist, appearance[bot]) < DRIFT_CORRELATION_MIN:
                    ok = False  # force a re-acquire below

            if not ok:
                bbox = _reacquire(frame, appearance[bot], box_size[bot])
                if bbox is not None:
                    trackers[bot] = _new_csrt_tracker()
                    trackers[bot].init(frame, bbox)
                    ok = True

            if ok and bbox is not None:
                cx, cy = _bbox_center(bbox)
                floor_xy = C.apply_homography(H, [(cx, cy)])[0]
                pos[bot] = [round(float(floor_xy[0]), 3), round(float(floor_xy[1]), 3)]
                appearance[bot] = _bbox_hist(frame, bbox)

        out.append(S.TrackFrame(t=t, wide=True, pos=(pos or None)))

    return out, appearance


# --------------------------------------------------------------------------
# Whole-fight orchestration
# --------------------------------------------------------------------------


def _wide_runs(wide_mask: list[bool]) -> list[tuple[int, int]]:
    """Contiguous [start, end) index pairs where wide_mask is True."""
    runs, start = [], None
    for i, w in enumerate(wide_mask + [False]):
        if w and start is None:
            start = i
        elif not w and start is not None:
            runs.append((start, i))
            start = None
    return runs


def _run(fight_id: str, review: bool = False, click_fn: ClickFn = _click_boxes) -> Path:
    meta = S.load_meta(fight_id)
    bot_names = list(meta.bots)
    shots = SH.load_shots(fight_id)
    cal = C.load_calibration(fight_id)
    H = np.array(cal.homography)

    track_dir = S.FRAMES_DIR / fight_id / "track"
    frame_paths = sorted(track_dir.glob("*.jpg"))
    if not frame_paths:
        raise FileNotFoundError(f"no frames under {track_dir} — run `bb ingest --fight-id {fight_id}` first.")

    wide_mask = [SH.is_wide(shots, round(i / FPS, 2)) for i in range(len(frame_paths))]
    frames: list[S.TrackFrame | None] = [None] * len(frame_paths)

    appearance: dict[str, np.ndarray] = {}
    for start, end in _wide_runs(wide_mask):
        seg_frames, appearance = _track_segment(
            frame_paths[start:end], start, bot_names, H, appearance, click_fn
        )
        for offset, tf in enumerate(seg_frames):
            frames[start + offset] = tf

    for i in range(len(frames)):
        if frames[i] is None:
            frames[i] = S.TrackFrame(t=round(i / FPS, 2), wide=False, pos=None)

    tracked_ok = sum(
        1 for f in frames if f.wide and f.pos is not None and set(f.pos) == set(bot_names)
    )
    coverage = round(tracked_ok / len(frames), 3) if frames else 0.0

    tracks = S.Tracks(fight_id=fight_id, fps=FPS, coverage=coverage, frames=frames)  # type: ignore[arg-type]
    path = S.save_tracks(tracks)
    print(f"coverage {coverage:.1%} -> {path}")

    if review:
        _render_review(fight_id, frame_paths, frames)  # type: ignore[arg-type]

    return path


def _render_review(fight_id: str, frame_paths: list[Path], frames: list[S.TrackFrame]) -> Path:
    """A side-by-side (raw | tracked) mp4 for eyeballing, per ``--review``."""
    first = cv2.imread(str(frame_paths[0]))
    h, w = first.shape[:2]
    out_path = S.fight_dir(fight_id, create=True) / "track_review.mp4"
    writer = cv2.VideoWriter(str(out_path), cv2.VideoWriter_fourcc(*"mp4v"), FPS, (2 * w, h))

    cal = C.load_calibration(fight_id)
    H_inv = C.invert_homography(np.array(cal.homography))
    colors = [(0, 255, 0), (0, 128, 255), (255, 0, 255)]

    for path, tf in zip(frame_paths, frames):
        raw = cv2.imread(str(path))
        if raw is None:
            continue
        annotated = raw.copy()
        if tf.pos:
            for i, (bot, xy) in enumerate(tf.pos.items()):
                px = C.apply_homography(H_inv, [xy])[0]
                cv2.circle(annotated, (int(px[0]), int(px[1])), 8, colors[i % len(colors)], 2)
                cv2.putText(
                    annotated, bot, (int(px[0]) + 10, int(px[1])),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, colors[i % len(colors)], 1, cv2.LINE_AA,
                )
        writer.write(np.concatenate([raw, annotated], axis=1))
    writer.release()
    print(f"track_review.mp4 -> {out_path}")
    return out_path


def track(fight_id: str, review: bool = False) -> Path:
    return _run(fight_id, review=review)
