"""D4 acceptance — "the fixture-replay test tracks synthetic moving blobs to
under 0.5 m error, and it runs on an arbitrary real clip without crashing."

There is no real footage yet, so this test manufactures its own: it renders
one coloured circle per bot at the *fixture's own ground-truth floor
positions*, projected through a known synthetic camera homography, then runs
the real D4 pipeline (CSRT tracking + histogram re-acquisition + homography)
over those frames and checks the recovered floor positions against the
ground truth tracks.json already asserted by test_fixtures.py.

The human click (spec 9.3) is replaced by a "perfect eye" click_fn that finds
each bot's rendered blob by colour — this isolates the CV pipeline (CSRT +
re-acquisition + homography) from click precision, which isn't what D4 is
being graded on.
"""

from __future__ import annotations

import shutil

import cv2
import numpy as np
import pytest

from blackbox import fixtures as F
from blackbox import schemas as S
from blackbox.pipeline import calibrate as C
from blackbox.pipeline import shots as SH
from blackbox.pipeline import track as T

IMG_SIZE = 240
BOT_COLORS = {F.BOT_A: (30, 170, 250), F.BOT_B: (230, 90, 20)}  # BGR, distinct hues


def _floor_to_image_homography(img_size: int = IMG_SIZE) -> np.ndarray:
    scale = (img_size * 0.9) / S.FLOOR_M
    margin = img_size * 0.05
    return np.array([[scale, 0.0, margin], [0.0, scale, margin], [0.0, 0.0, 1.0]])


def _write_synthetic_frames(fight_id: str, frames_by_index: dict[int, dict | None], floor_to_image: np.ndarray) -> None:
    track_dir = S.FRAMES_DIR / fight_id / "track"
    if track_dir.exists():
        shutil.rmtree(track_dir)
    track_dir.mkdir(parents=True, exist_ok=True)

    rng = np.random.default_rng(1)
    for i in sorted(frames_by_index):
        pos = frames_by_index[i]
        img = np.full((IMG_SIZE, IMG_SIZE, 3), 45, dtype=np.uint8)
        if pos:
            for bot, xy in pos.items():
                px = C.apply_homography(floor_to_image, [xy])[0]
                cv2.circle(img, (int(round(px[0])), int(round(px[1]))), 15, BOT_COLORS[bot], -1)
        else:
            img = rng.integers(0, 255, (IMG_SIZE, IMG_SIZE, 3), dtype=np.uint8)
        cv2.imwrite(str(track_dir / f"frame_{i:06d}.jpg"), img)


def _write_calibration(fight_id: str, floor_to_image: np.ndarray) -> None:
    floor_pts = [pt for _, pt in C.CALIBRATION_POINTS] + [(S.FLOOR_M / 2, S.FLOOR_M / 2)]
    image_pts = C.apply_homography(floor_to_image, floor_pts)
    H, err = C.compute_homography(image_pts, floor_pts)
    cal = C.Calibration(
        fight_id=fight_id,
        image_points=image_pts.tolist(),
        floor_points=[list(p) for p in floor_pts],
        homography=H.tolist(),
        reprojection_error_m=err,
        source_frame="synthetic",
    )
    C.save_calibration(cal)


def _write_shots(fight_id: str, intervals: list[tuple[float, float, bool]]) -> None:
    shots = SH.Shots(fight_id=fight_id, shots=[SH.Shot(start_t=a, end_t=b, wide=w) for a, b, w in intervals])
    SH.save_shots(shots)


def _shots_from_gaps(gaps: list[tuple[float, float]], duration: float) -> list[tuple[float, float, bool]]:
    bounds = [0.0]
    for a, b in gaps:
        bounds += [a, b]
    bounds.append(duration)
    intervals, wide = [], True
    for i in range(len(bounds) - 1):
        a, b = bounds[i], bounds[i + 1]
        if b > a:
            intervals.append((a, b, wide))
        wide = not wide
    return intervals


def _perfect_click_fn(frame: np.ndarray, bot_names: list[str]) -> dict[str, T.BBox]:
    """Stands in for the human click (spec 9.3): finds each bot's rendered
    blob by colour rather than requiring a GUI in CI."""
    boxes = {}
    for bot in bot_names:
        color = np.array(BOT_COLORS[bot])
        mask = cv2.inRange(frame, np.clip(color - 20, 0, 255), np.clip(color + 20, 0, 255))
        ys, xs = np.where(mask > 0)
        if len(xs) == 0:
            cx, cy = frame.shape[1] // 2, frame.shape[0] // 2
        else:
            cx, cy = int(xs.mean()), int(ys.mean())
        r = 18
        boxes[bot] = (cx - r, cy - r, 2 * r, 2 * r)
    return boxes


@pytest.fixture()
def homography():
    return _floor_to_image_homography()


def test_tracks_synthetic_blobs_under_half_metre_error(homography):
    F.build()
    truth = S.load_tracks(F.FIGHT_ID)

    seg_end = int(F.GAPS[0][0] * F.FPS)  # frames before the first scripted gap
    frames_by_index = {i: truth.frames[i].pos for i in range(seg_end)}
    _write_synthetic_frames(F.FIGHT_ID, frames_by_index, homography)
    _write_calibration(F.FIGHT_ID, homography)
    _write_shots(F.FIGHT_ID, [(0.0, F.GAPS[0][0], True), (F.GAPS[0][0], F.DURATION_S, False)])

    T._run(F.FIGHT_ID, review=False, click_fn=_perfect_click_fn)

    result = S.load_tracks(F.FIGHT_ID)
    assert len(result.frames) == seg_end

    errors = []
    for i in range(seg_end):
        pred, true = result.frames[i].pos, truth.frames[i].pos
        assert pred is not None, f"frame {i} lost tracking entirely"
        for bot in (F.BOT_A, F.BOT_B):
            errors.append(np.linalg.norm(np.array(pred[bot]) - np.array(true[bot])))
    errors = np.array(errors)

    # A hit happens inside this window (t=22s) where the bots pass within ~1m
    # of each other — CSRT is allowed a handful of rough frames there, so the
    # bar is on the typical case, not every single frame.
    assert np.median(errors) < 0.3, f"median error {np.median(errors):.2f} m"
    assert np.mean(errors) < 0.5, f"mean error {np.mean(errors):.2f} m"
    assert np.percentile(errors, 95) < 1.0, f"p95 error {np.percentile(errors, 95):.2f} m"


def test_full_fixture_runs_without_crashing(homography):
    F.build()
    truth = S.load_tracks(F.FIGHT_ID)

    frames_by_index = {i: fr.pos for i, fr in enumerate(truth.frames)}
    _write_synthetic_frames(F.FIGHT_ID, frames_by_index, homography)
    _write_calibration(F.FIGHT_ID, homography)
    _write_shots(F.FIGHT_ID, _shots_from_gaps(F.GAPS, F.DURATION_S))

    T._run(F.FIGHT_ID, review=False, click_fn=_perfect_click_fn)

    result = S.load_tracks(F.FIGHT_ID)
    assert len(result.frames) == len(truth.frames)
    assert result.coverage > 0.6, f"coverage collapsed to {result.coverage:.1%}"

    for fr, tfr in zip(result.frames, truth.frames):
        assert fr.wide == tfr.wide
        if not tfr.wide:
            assert fr.pos is None, "gaps must never carry a position"
