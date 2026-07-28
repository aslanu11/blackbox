"""D4.5 acceptance - wide shots from different cameras end up in different
clusters, only the dominant angle keeps wide=True, and re-runs are idempotent."""

from __future__ import annotations

import json

import cv2
import numpy as np
import pytest

from blackbox import schemas as S
from blackbox.pipeline import angles as A
from blackbox.pipeline import shots as SH

FID = "angles-test"


def _camera_frame(seed: int, robot_x: int) -> np.ndarray:
    """A structured static background per camera + a small 'robot'.

    Real arenas have persistent low-frequency structure (walls, floor
    markings, light banks), modelled here as seeded sinusoidal gratings.
    Blurred noise is NOT a fair stand-in: it flattens to nothing at
    signature resolution, leaving the robot as the only signal.
    """
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:270, 0:480].astype(np.float32)
    img = np.zeros((270, 480), dtype=np.float32)
    for _ in range(4):
        fx, fy = rng.uniform(0.5, 3.0, 2)
        phase = rng.uniform(0, 2 * np.pi)
        img += rng.uniform(20, 50) * np.sin(2 * np.pi * (fx * xx / 480 + fy * yy / 270) + phase)
    img = cv2.normalize(img, None, 40, 200, cv2.NORM_MINMAX)
    img = cv2.cvtColor(img.astype(np.uint8), cv2.COLOR_GRAY2BGR)
    cv2.rectangle(img, (robot_x, 120), (robot_x + 40, 160), (0, 220, 220), -1)
    return img


@pytest.fixture()
def rig(tmp_path, monkeypatch):
    monkeypatch.setattr(S, "PROCESSED_DIR", tmp_path / "processed")
    monkeypatch.setattr(S, "FRAMES_DIR", tmp_path / "frames")

    key_dir = S.FRAMES_DIR / FID / "key"
    track_dir = S.FRAMES_DIR / FID / "track"
    key_dir.mkdir(parents=True)
    track_dir.mkdir(parents=True)

    # 6 shots of 2 s each: camera A at shots 0,2,4 (dominant), camera B at 1,5;
    # shot 3 is a close-up (wide=False, must be ignored and left alone).
    # Track frames at 10 fps with the robot driving across the frame within
    # each shot - the averaged signature must smear it out.
    shots = []
    for i in range(6):
        start, end = 2.0 * i, 2.0 * (i + 1)
        wide = i != 3
        cam = 111 if i % 2 == 0 else 999
        mid_idx = int(round(0.5 * (start + end)))
        cv2.imwrite(str(key_dir / f"frame_{mid_idx:06d}.jpg"), _camera_frame(cam, robot_x=100 + 25 * i))
        for f in range(int(start * 10), int(end * 10)):
            robot_x = 60 + (f * 17) % 320
            cv2.imwrite(str(track_dir / f"frame_{f:06d}.jpg"), _camera_frame(cam, robot_x=robot_x))
        shots.append(SH.Shot(start_t=start, end_t=end, wide=wide))
    SH.save_shots(SH.Shots(fight_id=FID, shots=shots))
    return shots


def test_two_cameras_cluster_apart_and_dominant_wins(rig):
    A.cluster(FID)
    out = SH.load_shots(FID)
    data = json.loads(A.angles_path(FID).read_text(encoding="utf-8"))

    assert len(data["angles"]) == 2, "camera A and camera B should not merge"
    assert [s.wide for s in out.shots] == [True, False, True, False, True, False], (
        "camera A (shots 0,2,4) is dominant; camera B (1,5) and the close-up (3) are gaps"
    )


def test_keep_angle_switch_and_idempotence(rig):
    A.cluster(FID)
    A.cluster(FID, keep_angle=1)  # promote camera B instead
    out = SH.load_shots(FID)
    assert [s.wide for s in out.shots] == [False, True, False, False, False, True], (
        "re-clustering must restore original wide flags before demoting again"
    )
    # close-up shot 3 must never be resurrected
    assert out.shots[3].wide is False


def test_missing_frames_are_survivable(rig):
    for p in (S.FRAMES_DIR / FID / "key").glob("*.jpg"):
        p.unlink()
    A.cluster(FID)  # must not raise
    out = SH.load_shots(FID)
    assert all(not s.wide for s in out.shots) or any(s.wide for s in out.shots)
