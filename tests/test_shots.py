"""D2 acceptance — "runs end to end on any mp4; classifications are cached so
re-runs cost nothing."

Two layers: a fast, dependency-free unit test of the heuristic border-motion
classifier, and an ffmpeg-backed end-to-end test (skipped without ffmpeg) that
exercises ingest -> shots on a synthetic two-scene clip.
"""

from __future__ import annotations

import shutil
import subprocess

import numpy as np
import pytest

from blackbox import schemas as S
from blackbox.pipeline import ingest as I
from blackbox.pipeline import shots as SH

FIGHT_ID = "test-shots"


def _static_frames(n: int = 8, size: int = 64) -> list[np.ndarray]:
    """A locked-off shot: same background, tiny sensor noise only."""
    rng = np.random.default_rng(0)
    base = np.full((size, size, 3), 120, dtype=np.uint8)
    return [np.clip(base.astype(int) + rng.integers(-1, 2, base.shape), 0, 255).astype(np.uint8) for _ in range(n)]


def _busy_frames(n: int = 8, size: int = 64) -> list[np.ndarray]:
    """A handheld / cutting-around shot: the border moves a lot frame to frame."""
    rng = np.random.default_rng(1)
    return [rng.integers(0, 255, (size, size, 3), dtype=np.uint8) for _ in range(n)]


def test_heuristic_classifies_static_shot_as_wide():
    assert SH.classify_wide_heuristic(_static_frames()) is True


def test_heuristic_classifies_busy_shot_as_not_wide():
    assert SH.classify_wide_heuristic(_busy_frames()) is False


def test_border_motion_score_is_zero_for_a_single_frame():
    assert SH._border_motion_score(_static_frames(n=1)) == 0.0


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not on PATH")
def test_detect_runs_end_to_end_on_a_two_scene_clip():
    S.RAW_DIR.mkdir(parents=True, exist_ok=True)
    raw_path = S.RAW_DIR / f"{FIGHT_ID}.mp4"
    try:
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-f", "lavfi", "-i", "smptebars=duration=3:size=128x128:rate=10",
                "-f", "lavfi", "-i", "testsrc=duration=3:size=128x128:rate=10",
                "-filter_complex", "[0:v][1:v]concat=n=2:v=1:a=0,format=yuv420p[v]",
                "-map", "[v]", str(raw_path),
            ],
            capture_output=True, text=True, check=True,
        )
        S.save_meta(
            S.FightMeta(
                fight_id=FIGHT_ID, bots=["A", "B"],
                video=S.VideoRef(yt_id=None, fight_start_s=0.0, fight_end_s=6.0),
            )
        )
        I.extract(FIGHT_ID)
        path = SH.detect(FIGHT_ID, heuristic=True)
        result = SH.load_shots(FIGHT_ID)

        assert path == SH.shots_path(FIGHT_ID)
        assert len(result.shots) >= 1
        total_covered = sum(s.end_t - s.start_t for s in result.shots)
        assert total_covered == pytest.approx(6.0, abs=0.5)
    finally:
        raw_path.unlink(missing_ok=True)
        shutil.rmtree(S.FRAMES_DIR / FIGHT_ID, ignore_errors=True)
        shutil.rmtree(S.fight_dir(FIGHT_ID), ignore_errors=True)
