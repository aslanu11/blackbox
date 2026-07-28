"""A5 acceptance - mock mode is stable, the cache short-circuits the network."""

from __future__ import annotations

import numpy as np
import pytest
from PIL import Image

from blackbox import llm


@pytest.fixture(autouse=True)
def _mock_env(monkeypatch):
    monkeypatch.setenv("LLM_MOCK", "1")


@pytest.fixture()
def frame(tmp_path):
    """A synthetic 1280x720 'broadcast frame'."""
    rng = np.random.default_rng(7)
    img = Image.fromarray(rng.integers(0, 255, (720, 1280, 3), dtype=np.uint8))
    p = tmp_path / "frame.png"
    img.save(p)
    return p


def test_mock_mode_is_detected():
    assert llm.mock_mode()


def test_classify_wide_is_deterministic(frame):
    first = llm.classify_wide(frame)
    assert isinstance(first, bool)
    assert all(llm.classify_wide(frame) == first for _ in range(3))


def test_score_rubric_shape_and_sums(frame):
    result = llm.score_rubric([frame], ["Minotaur", "Bloodsport"])
    assert sum(result["damage"]) == 5
    assert sum(result["aggression"]) == 3
    assert sum(result["control"]) == 3


def test_damage_assess_bounded(frame, tmp_path):
    rng = np.random.default_rng(8)
    later = tmp_path / "later.png"
    Image.fromarray(rng.integers(0, 255, (720, 1280, 3), dtype=np.uint8)).save(later)
    result = llm.damage_assess(frame, later, "Minotaur")
    assert 0.0 <= result["damage_delta"] <= 1.0


def test_images_are_downsampled(frame):
    jpeg = llm._encode_image(frame)
    from io import BytesIO

    with Image.open(BytesIO(jpeg)) as im:
        assert max(im.size) <= llm.MAX_IMAGE_EDGE


def test_cache_round_trip(tmp_path, monkeypatch):
    """A cached result must be returned without reaching the network path."""
    monkeypatch.setenv("LLM_MOCK", "0")  # force the real path...
    key = llm._cache_key("classify_wide", llm.MODEL_FAST, b"payload")
    llm._cache_put(key, "classify_wide", llm.MODEL_FAST, {"wide": True})
    try:
        # ...which must short-circuit at the cache before any client is built.
        assert llm._cache_get(key) == {"wide": True}
    finally:
        llm._cache_path(key).unlink(missing_ok=True)


def test_network_path_raises_under_mock():
    """If a task slips past its mock branch, tests must fail loudly, not call out."""
    with pytest.raises(RuntimeError, match="LLM_MOCK"):
        llm._call(
            task="classify_wide",
            model=llm.MODEL_FAST,
            system="x",
            content=[],
            schema={},
            cache_payload=b"never-cached-payload",
        )
