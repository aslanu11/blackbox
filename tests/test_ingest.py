"""D1 acceptance — frame counts match the expected duration within 2%.

Uses an ffmpeg-generated synthetic test pattern (lavfi testsrc), never real
footage, so this needs nothing beyond ffmpeg itself. Skipped if ffmpeg isn't
on PATH (see `bb doctor`).
"""

from __future__ import annotations

import shutil
import subprocess

import pytest

from blackbox import schemas as S
from blackbox.pipeline import ingest as I

FIGHT_ID = "test-ingest"

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not on PATH")


@pytest.fixture()
def synthetic_raw_clip():
    S.RAW_DIR.mkdir(parents=True, exist_ok=True)
    raw_path = S.RAW_DIR / f"{FIGHT_ID}.mp4"
    subprocess.run(
        [
            "ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=duration=6:size=64x64:rate=25",
            "-pix_fmt", "yuv420p", str(raw_path),
        ],
        capture_output=True, text=True, check=True,
    )
    S.save_meta(
        S.FightMeta(
            fight_id=FIGHT_ID,
            bots=["A", "B"],
            video=S.VideoRef(yt_id=None, fight_start_s=1.0, fight_end_s=4.0),
        )
    )
    yield raw_path
    raw_path.unlink(missing_ok=True)
    shutil.rmtree(S.FRAMES_DIR / FIGHT_ID, ignore_errors=True)
    shutil.rmtree(S.fight_dir(FIGHT_ID), ignore_errors=True)


def test_frame_counts_match_duration_within_two_percent(synthetic_raw_clip):
    track_dir = I.extract(FIGHT_ID)

    n_track = len(list(track_dir.glob("*.jpg")))
    expected_track = 3.0 * I.TRACK_FPS  # fight_end_s - fight_start_s
    assert abs(n_track - expected_track) / expected_track <= 0.02

    key_dir = S.FRAMES_DIR / FIGHT_ID / "key"
    n_key = len(list(key_dir.glob("*.jpg")))
    expected_key = 3.0 * I.KEY_FPS
    assert abs(n_key - expected_key) <= 1

    assert (track_dir / "frame_000000.jpg").exists(), "frames must be 0-indexed"


def test_missing_raw_footage_raises_clear_error():
    S.save_meta(
        S.FightMeta(
            fight_id="no-such-fight",
            bots=["A", "B"],
            video=S.VideoRef(yt_id=None, fight_start_s=0.0, fight_end_s=1.0),
        )
    )
    try:
        with pytest.raises(FileNotFoundError):
            I.extract("no-such-fight")
    finally:
        shutil.rmtree(S.fight_dir("no-such-fight"), ignore_errors=True)
