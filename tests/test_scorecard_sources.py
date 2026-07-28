"""B4 + C2/C4 acceptance - mock-LLM scorecard, leaderboard sort, pure parsers."""

from __future__ import annotations

import json

import numpy as np
import pytest
from PIL import Image

from blackbox import fixtures as F
from blackbox import schemas as S
from blackbox.pipeline import scorecard as B4
from blackbox.pipeline import telemetry as B1
from blackbox.sources import specs, yt


@pytest.fixture(autouse=True)
def _mock_env(monkeypatch):
    monkeypatch.setenv("LLM_MOCK", "1")


# ------------------------------------------------------------------ B4


@pytest.fixture(scope="module")
def scored():
    F.build()
    B1.compute(F.FIGHT_ID)
    B4.score(F.FIGHT_ID)
    return S.load_scorecard(F.FIGHT_ID)


def test_full_mode_sums_are_valid(scored):
    assert sum(scored.ours.damage) == 5
    assert sum(scored.ours.aggression) == 3
    assert sum(scored.ours.control) == 3
    assert 0.0 <= scored.ours.margin <= 1.0


def test_full_mode_scores_the_ko_winner(scored):
    """Bot A KOs bot B - our card must not favour the dead robot."""
    assert scored.ours.winner == "A"
    # Damage: B lost all mobility, so A must take the damage category.
    assert scored.ours.damage[0] > scored.ours.damage[1]


def test_ko_fight_is_never_a_robbery(scored):
    assert scored.robbery_score == 0.0


def test_cheap_mode_runs_on_keyframes(tmp_path, monkeypatch):
    """Mode (b): no tracks, just keyframes + the mocked LLM."""
    fid = "corpus-test-001"
    meta = S.FightMeta(
        fight_id=fid,
        bots=["End Game", "Malice"],
        result=S.FightResult(winner="Malice", method="jd", time_s=None),
        role="corpus",
    )
    S.save_meta(meta)
    key_dir = S.FRAMES_DIR / fid / "key"
    key_dir.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(3)
    for i in range(4):
        Image.fromarray(rng.integers(0, 255, (72, 128, 3), dtype=np.uint8)).save(
            key_dir / f"{i:04d}.jpg"
        )
    try:
        B4.score(fid)
        sc = S.load_scorecard(fid)
        assert sum(sc.ours.damage) == 5
        # Mock rubric says A wins; official says Malice (B) won a JD -> robbery.
        assert sc.official.winner == "B"
        assert sc.robbery_score > 0
    finally:
        import shutil

        shutil.rmtree(S.fight_dir(fid), ignore_errors=True)
        shutil.rmtree(S.FRAMES_DIR / fid, ignore_errors=True)


def test_leaderboard_sorts_by_robbery(scored):
    json_path, csv_path = B4.leaderboard()
    data = json.loads(json_path.read_text(encoding="utf-8"))
    scores = [f["robbery_score"] for f in data["fights"]]
    assert scores == sorted(scores, reverse=True)
    assert csv_path.exists()


# ------------------------------------------------------------------ C2 parser


def test_yt_heatmap_normalization():
    raw = [
        {"start_time": 0, "end_time": 10, "value": 0.2},
        {"start_time": 10, "end_time": 20, "value": 0.8},
        {"start_time": 20, "end_time": 30, "value": 0.4},
    ]
    points = yt.normalize_heatmap(raw)
    assert points == [[5.0, 0.25], [15.0, 1.0], [25.0, 0.5]]


def test_yt_heatmap_missing_is_none():
    assert yt.normalize_heatmap(None) is None
    assert yt.normalize_heatmap([]) is None
    assert yt.normalize_heatmap([{"bogus": 1}]) is None


def test_yt_parse_info_tolerates_missing_fields():
    parsed = yt.parse_info({"id": "abc123", "duration": 100})
    assert parsed["yt_id"] == "abc123"
    assert parsed["heatmap"] is None
    assert parsed["view_count"] is None


# ------------------------------------------------------------------ C4 parser


def test_weapon_classification():
    cases = {
        "Vertical spinner, 250lb": "vertical_spinner",
        "Horizontal bar spinner": "horizontal_spinner",
        "Eggbeater drum": "drum",
        "Pneumatic flipper": "flipper",
        "Hammer saw": "hammer",
        "Crushing jaw grabber": "crusher",
        "Wedge and lifter": "control",
        "Mystery box": "other",
    }
    for text, expected in cases.items():
        assert specs.classify_weapon(text) == expected, text
    for cls in set(cases.values()):
        assert cls in S.WEAPON_CLASSES


def test_roster_parser_on_synthetic_html():
    html = """
    <div><a href="/robots/huge/">HUGE</a><p>Weapon: Vertical spinner</p><p>Team: Team HUGE</p></div>
    <div><a href="/robots/minotaur/">Minotaur</a><p>Weapon: Drum</p></div>
    <div><a href="/robots/hydra/">Hydra</a><p>Weapon: Hydraulic flipper</p></div>
    """
    bots = specs.parse_roster(html)
    by_name = {b["name"]: b for b in bots}
    assert by_name["HUGE"]["weapon_class"] == "vertical_spinner"
    assert by_name["Minotaur"]["weapon_class"] == "drum"
    assert by_name["Hydra"]["weapon_class"] == "flipper"
