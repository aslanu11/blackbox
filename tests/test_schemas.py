"""A2 acceptance — the §5 contracts round-trip."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from blackbox import schemas as S


def test_floor_is_48_feet():
    assert S.FLOOR_M == pytest.approx(14.63, abs=0.01)


def test_fight_meta_round_trip():
    m = S.FightMeta(
        fight_id="pl-e04-f2",
        episode=4,
        bots=["Minotaur", "Bloodsport"],
        colors={"Minotaur": "#D4AF37", "Bloodsport": "#1E6FD9"},
        result=S.FightResult(winner="Minotaur", method="ko", time_s=141.5),
        video=S.VideoRef(yt_id="abc123", fight_start_s=812.0, fight_end_s=962.0),
        role="hero",
    )
    again = S.FightMeta.model_validate_json(m.model_dump_json())
    assert again == m
    assert again.video.duration_s == pytest.approx(150.0)


def test_tracks_round_trip_preserves_explicit_gaps():
    t = S.Tracks(
        fight_id="x",
        fps=10,
        coverage=0.8,
        frames=[
            S.TrackFrame(t=0.0, wide=True, pos={"A": [1.0, 2.0], "B": [3.0, 4.0]}),
            S.TrackFrame(t=0.1, wide=False, pos=None),
        ],
    )
    again = S.Tracks.model_validate_json(t.model_dump_json())
    assert again == t
    assert again.frames[1].pos is None, "gaps must survive serialisation as null"


def test_each_artifact_round_trips():
    cases = [
        S.Events(fight_id="x", events=[S.Event(t=41.2, type="hit", magnitude=7.9, actor="A", target="B")]),
        S.Telemetry(
            fight_id="x",
            series=S.TelemetrySeries(momentum=[[0, 0.5]], control=[[0, 0.1]], speed={"A": [[0, 1.2]]}, mobility={"A": [[0, 1.0]]}),
            heatmap_png={"A": "a_heat.png"},
        ),
        S.Attention(video_id="v", fight_id="x", points=[[0, 0.31]], stats=S.AttentionStats(baseline=0.3, peak=0.97, peak_t=141.0)),
        S.Scorecard(
            fight_id="x",
            ours=S.RubricScores(damage=[3, 2], aggression=[2, 1], control=[2, 1], winner="A", margin=0.62),
            official=S.OfficialVerdict(winner="B", split="2-1"),
            robbery_score=0.62,
        ),
        S.MediaValue(bots=[S.BotMediaValue(name="HUGE", fights=2, screen_s=412, attn_index=1.9, media_value=783, record="1-1", perf_score=0.44)]),
    ]
    for model in cases:
        assert type(model).model_validate_json(model.model_dump_json()) == model


def test_unknown_fields_are_rejected():
    """Contract drift must fail loudly, not get silently absorbed."""
    with pytest.raises(ValidationError):
        S.Events.model_validate({"fight_id": "x", "events": [], "extra_lane": 1})


def test_rubric_totals_eleven_points():
    """Damage 5 + Aggression 3 + Control 3 (spec §B4)."""
    r = S.RubricScores(damage=[3, 2], aggression=[2, 1], control=[2, 1], winner="A", margin=0.62)
    assert sum(r.damage) == 5
    assert sum(r.aggression) == 3
    assert sum(r.control) == 3


def test_artifact_paths_resolve_under_processed():
    p = S.artifact_path("fixture-001", "tracks")
    assert p.name == "tracks.json"
    assert p.parent.name == "fixture-001"
    assert p.parent.parent == S.PROCESSED_DIR


def test_unknown_artifact_kind_raises():
    with pytest.raises(KeyError):
        S.artifact_path("fixture-001", "nonsense")
