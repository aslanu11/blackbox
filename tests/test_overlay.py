"""D5 acceptance — `bb overlay --fight-id fixture-001` produces a watchable
mp4 from synthetic data (the fixture has no clip.mp4, so this exercises the
schematic rendering path — the same path any fight without footage yet uses).
"""

from __future__ import annotations

import cv2
import pytest

from blackbox import fixtures as F
from blackbox import schemas as S
from blackbox.pipeline import overlay as O


@pytest.fixture(scope="module")
def rendered():
    F.build()
    return O.render(F.FIGHT_ID)


def test_overlay_file_exists_and_is_nonempty(rendered):
    assert rendered.exists()
    assert rendered.stat().st_size > 1000


def test_overlay_is_a_readable_720p_video(rendered):
    cap = cv2.VideoCapture(str(rendered))
    assert cap.isOpened(), "overlay.mp4 must be a valid, readable video"
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.release()
    assert (w, h) == O.OUT_SIZE
    assert n > 0


def test_overlay_caps_at_ninety_seconds():
    tracks = S.load_tracks(F.FIGHT_ID)
    assert tracks.frames[-1].t > O.MAX_HERO_S, "fixture must exceed 90s for this to be a real test"

    cap = cv2.VideoCapture(str(O.render(F.FIGHT_ID)))
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = tracks.fps
    cap.release()
    assert n <= O.MAX_HERO_S * fps + 5


def test_overlay_first_frame_is_not_blank(rendered):
    cap = cv2.VideoCapture(str(rendered))
    ok, frame = cap.read()
    cap.release()
    assert ok
    assert frame.std() > 1.0, "first frame should have actual content, not a flat colour"
