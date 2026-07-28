"""S1 acceptance — the sponsorship index is honest, ordered, and offline-safe.

Every test runs with ``enrich=False`` so the suite never touches Bright Data or
the network (spec §9.2). The one test that exercises the collector path asserts
only that a missing token degrades quietly.
"""

from __future__ import annotations

import numpy as np
import pytest

from blackbox import fixtures as F
from blackbox import schemas as S
from blackbox import sponsor as SP


@pytest.fixture(scope="module")
def fixture_index():
    F.build()
    # events.json is B2's output and may not exist on a clean tree; synthesise
    # the scripted ground truth so authorship has something to score.
    if not S.exists(F.FIGHT_ID, "events"):
        S.save_events(
            S.Events(
                fight_id=F.FIGHT_ID,
                events=[
                    S.Event(
                        t=t,
                        type="hit",
                        magnitude=mag,
                        actor=actor,
                        target=F.BOT_B if actor == F.BOT_A else F.BOT_A,
                    )
                    for t, mag, actor in F.HITS
                ]
                + [S.Event(t=F.KO_T, type="ko", actor=F.KO_WINNER, target=F.BOT_B)],
            )
        )
    return SP.build_index(fight_ids=[F.FIGHT_ID], enrich=False)


# --------------------------------------------------------------------------
# Shape and contract
# --------------------------------------------------------------------------


def test_index_round_trips(fixture_index):
    again = SP.SponsorIndex.model_validate_json(fixture_index.model_dump_json())
    assert again == fixture_index


def test_unknown_fields_are_rejected():
    """This module has its own contract; drift must fail loudly like §5 does."""
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        SP.SponsorIndex.model_validate({"bots": [], "extra_lane": 1})


def test_schemas_stays_frozen():
    """S1 must not have smuggled itself into the frozen §5 artifact registry."""
    assert "sponsor" not in S._ARTIFACTS
    assert not hasattr(S, "SponsorRow")


def test_weights_are_attention_dominant():
    """The brief prioritises most-replayed; attention terms must outweigh results."""
    assert SP.W_SPOTLIGHT + SP.W_AUTHORSHIP == pytest.approx(0.75)
    assert SP.W_PERFORMANCE == pytest.approx(0.25)
    assert sum(SP._weights().values()) == pytest.approx(1.0)


# --------------------------------------------------------------------------
# The scoring actually means something
# --------------------------------------------------------------------------


def test_both_fixture_bots_are_scored(fixture_index):
    names = {b.name for b in fixture_index.bots}
    assert names == {F.BOT_A, F.BOT_B}


def test_ko_winner_outranks_its_victim(fixture_index):
    """Minotaur lands 4 of 5 scripted hits and wins by KO. It must rank first."""
    assert fixture_index.bots[0].name == F.KO_WINNER
    winner, loser = fixture_index.bots[0], fixture_index.bots[1]
    assert winner.sponsor_score > loser.sponsor_score
    assert winner.components.authorship > loser.components.authorship


def test_rows_are_sorted_by_score(fixture_index):
    scores = [b.sponsor_score for b in fixture_index.bots]
    assert scores == sorted(scores, reverse=True)


def test_scores_are_bounded(fixture_index):
    for b in fixture_index.bots:
        assert 0.0 <= b.sponsor_score <= 100.0
        for term in (b.components.spotlight, b.components.authorship, b.components.performance):
            assert 0.0 <= term <= 1.0


def test_shared_airtime_is_shared_but_authorship_is_not(fixture_index):
    """Both bots occupy the same wide shot; only authorship separates them."""
    a, b = fixture_index.bots
    assert a.critical_seconds == pytest.approx(b.critical_seconds)
    assert a.components.authorship != b.components.authorship


def test_critical_seconds_never_exceed_fight_duration(fixture_index):
    for b in fixture_index.bots:
        assert 0.0 < b.critical_seconds <= F.DURATION_S


# --------------------------------------------------------------------------
# The three corrections this module exists to make
# --------------------------------------------------------------------------


def test_lift_window_widens_for_coarse_youtube_buckets():
    """A real episode has ~13 s buckets; a fixed +/-5 s window finds nothing."""
    youtube_like = np.arange(0.0, 1298.0, 12.98)
    assert SP._lift_window(youtube_like) >= 12.98

    fixture_like = np.linspace(0.0, 150.0, 100)
    assert SP._lift_window(fixture_like) == pytest.approx(SP.MIN_WINDOW_S)


def test_no_event_is_silently_dropped_on_coarse_data():
    """The bug this module fixes: probe events must all find an attention value."""
    ts = np.arange(0.0, 300.0, 12.98)
    vals = np.linspace(0.2, 1.0, len(ts))
    half = SP._lift_window(ts)
    probes = np.linspace(ts.min(), ts.max(), 40)
    found = [SP._attention_at(ts, vals, t, half) for t in probes]
    assert all(v is not None for v in found)

    # And the naive +/-5 s window really would have dropped some — i.e. the test
    # above is not vacuous.
    naive = [SP._attention_at(ts, vals, t, 5.0) for t in probes]
    assert any(v is None for v in naive)


def test_quiet_fight_does_not_outscore_a_hot_one():
    """Episode-relative attention, not ratio-to-local-baseline.

    A fight sitting in a quiet stretch has a near-zero local baseline. Dividing
    by it inflates the quiet fight enormously — the artifact that put a 0-1 bot
    at the top of media_value.json. Spotlight must rank the hot fight higher.
    """
    quiet = np.array([0.02, 0.03, 0.025, 0.04, 0.03])
    hot = np.array([0.70, 0.95, 0.85, 1.00, 0.80])

    pooled = np.concatenate([quiet, hot])
    threshold = float(np.quantile(pooled, SP.CRITICAL_QUANTILE))

    assert quiet[quiet >= threshold].size == 0, "quiet fight should own no critical moments"
    assert hot[hot >= threshold].size > 0, "hot fight should own the critical moments"


def test_confidence_drops_without_cv_events(fixture_index, tmp_path, monkeypatch):
    """A bot scored on airtime alone must not claim full confidence."""
    for b in fixture_index.bots:
        assert "events" in b.basis
        assert b.confidence == pytest.approx(1.0)

    # Same fight, events.json hidden: confidence must fall and say why.
    monkeypatch.setattr(S, "exists", lambda fid, kind: False if kind == "events" else S.artifact_path(fid, kind).exists())
    degraded = SP.build_index(fight_ids=[F.FIGHT_ID], enrich=False)
    for b in degraded.bots:
        assert "events" not in b.basis
        assert b.confidence < 1.0


def test_missing_attention_is_reported_not_hidden():
    """Fights without attention.json are named, not silently skipped."""
    index = SP.build_index(fight_ids=["definitely-not-a-fight"], enrich=False)
    assert index.fights_missing_attention == ["definitely-not-a-fight"]
    assert index.bots == []


# --------------------------------------------------------------------------
# Offline safety
# --------------------------------------------------------------------------


def test_roster_fetch_degrades_without_a_token(monkeypatch, tmp_path):
    """No Bright Data token -> empty roster, never an exception, never a request."""
    monkeypatch.setattr(SP, "ROSTER_CACHE", tmp_path / "roster.json")
    monkeypatch.setattr(SP, "_token", lambda: None)
    assert SP.fetch_roster() == []


def test_roster_merge_accumulates_across_runs():
    """The collector returns a different subset each call; coverage must only grow.

    Observed on 2026-07-28: one run returned 7 robots, the next returned 14,
    overlapping on 3. Overwriting would have dropped Malice, which we score.
    """
    run_one = [{"robot_name": "Malice", "team_name": "Team Malice"}, {"robot_name": "Cobalt"}]
    run_two = [{"robot_name": "HyperShock"}, {"robot_name": "Cobalt", "team_name": "RDC"}]

    merged = SP._merge_roster(run_one, run_two)
    names = {r["robot_name"] for r in merged}
    assert names == {"Malice", "Cobalt", "HyperShock"}, "a bot from run one was lost"

    # Newest record wins on collision.
    cobalt = next(r for r in merged if r["robot_name"] == "Cobalt")
    assert cobalt["team_name"] == "RDC"


def test_roster_merge_ignores_nameless_rows():
    assert SP._merge_roster([], [{"team_name": "no name here"}]) == []


def test_cached_roster_survives_a_failed_refresh(monkeypatch, tmp_path):
    """A refresh that yields nothing must not wipe what we already resolved."""
    cache = tmp_path / "roster.json"
    cache.write_text('[{"robot_name": "Malice"}]', encoding="utf-8")
    monkeypatch.setattr(SP, "ROSTER_CACHE", cache)
    monkeypatch.setattr(SP, "_token", lambda: None)

    assert SP.fetch_roster(force=True) == [{"robot_name": "Malice"}]


def test_build_index_never_needs_the_network(fixture_index, monkeypatch):
    """enrich=False must not even consult the roster cache."""
    def explode(*a, **k):  # pragma: no cover - only runs on regression
        raise AssertionError("build_index(enrich=False) attempted a roster fetch")

    monkeypatch.setattr(SP, "fetch_roster", explode)
    index = SP.build_index(fight_ids=[F.FIGHT_ID], enrich=False)
    assert index.bots
