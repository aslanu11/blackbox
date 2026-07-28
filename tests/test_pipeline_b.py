"""B1/B2/B3/B5 acceptance against the fixture's scripted ground truth."""

from __future__ import annotations

import json

import numpy as np
import pytest

from blackbox import fixtures as F
from blackbox import schemas as S
from blackbox.pipeline import events as B2
from blackbox.pipeline import fuse as B5
from blackbox.pipeline import momentum as B3
from blackbox.pipeline import telemetry as B1


@pytest.fixture(scope="module")
def pipeline():
    """Run the whole B-chain once on a fresh fixture."""
    F.build()
    B1.compute(F.FIGHT_ID)
    B2.detect(F.FIGHT_ID)
    B3.compute(F.FIGHT_ID)
    B5.fuse(F.FIGHT_ID)
    B5.media_value()
    return {
        "meta": S.load_meta(F.FIGHT_ID),
        "telemetry": S.load_telemetry(F.FIGHT_ID),
        "events": S.load_events(F.FIGHT_ID),
        "attention": S.load_attention(F.FIGHT_ID),
        "media": S.load_media_value(),
        "truth": json.loads(
            (S.fight_dir(F.FIGHT_ID) / "expected_events.json").read_text(encoding="utf-8")
        ),
    }


# ------------------------------------------------------------------ B1


def test_b1_all_series_present(pipeline):
    s = pipeline["telemetry"].series
    assert s.control, "control series is empty"
    for b in pipeline["meta"].bots:
        assert s.speed[b], f"speed series for {b} is empty"
        assert s.mobility[b], f"mobility series for {b} is empty"


def test_b1_series_are_1hz_and_skip_gaps(pipeline):
    control = np.array(pipeline["telemetry"].series.control)
    ts = control[:, 0]
    assert np.all(ts == np.round(ts)), "control series is not on integer seconds"
    # The scripted gaps (30-40, 75-85, 128-138) must NOT be interpolated over:
    # speed needs positions, so mid-gap seconds must be absent from speed series.
    speed_a = np.array(pipeline["telemetry"].series.speed[F.BOT_A])
    for g0, g1 in pipeline["truth"]["gaps"]:
        mid = (g0 + g1) / 2
        assert not np.any(np.abs(speed_a[:, 0] - mid) < 0.5), f"speed invented data inside gap {g0}-{g1}"


def _decay_onset(ts: np.ndarray, idx: np.ndarray, thresh=0.6, sustain_s=8, back=0.85):
    """First sustained crossing below `thresh`, backdated to where the decline
    began (the last time the index was still >= `back`)."""
    below = np.nan_to_num(idx, nan=9.0) < thresh
    run = 0
    for i in range(len(below)):
        run = run + 1 if below[i] else 0
        if run >= sustain_s:
            cross = i - run + 1
            j = cross
            while j > 0 and not (not np.isnan(idx[j]) and idx[j] >= back):
                j -= 1
            return float(ts[j])
    return None


def test_b1_mobility_decay_detected_within_5s(pipeline):
    """THE B1 acceptance criterion: decay onset within +/-5 s of scripted."""
    truth = pipeline["truth"]["mobility_decay"]
    tol = pipeline["truth"]["tolerances"]["mobility_onset_s"]
    mob = np.array(pipeline["telemetry"].series.mobility[truth["bot"]])
    onset = _decay_onset(mob[:, 0], mob[:, 1])
    assert onset is not None, "no sustained mobility decay found for the decaying bot"
    assert abs(onset - truth["onset_s"]) <= tol, (
        f"decay onset detected at {onset}, scripted {truth['onset_s']} (+/-{tol})"
    )


def test_b1_no_false_decay_on_the_healthy_bot(pipeline):
    mob = np.array(pipeline["telemetry"].series.mobility[F.BOT_A])
    pre_ko = mob[mob[:, 0] < F.KO_T - 5]
    assert _decay_onset(pre_ko[:, 0], pre_ko[:, 1]) is None, "healthy bot shows a sustained decay"


def test_b1_healthy_bot_stays_mobile(pipeline):
    mob = np.array(pipeline["telemetry"].series.mobility[F.BOT_A])
    before_ko = mob[mob[:, 0] < F.KO_T - 5]
    assert np.median(before_ko[:, 1]) > 0.6


def test_b1_heatmaps_written(pipeline):
    for b, png in pipeline["telemetry"].heatmap_png.items():
        assert (S.fight_dir(F.FIGHT_ID) / png).exists(), f"missing heatmap for {b}"


# ------------------------------------------------------------------ B2


def test_b2_recovers_enough_hits(pipeline):
    """THE B2 acceptance criterion: >=4 of 5 within 1 s, <=1 false positive."""
    truth_hits = [h["t"] for h in pipeline["truth"]["hits"]]
    tol = pipeline["truth"]["tolerances"]
    detected = [e for e in pipeline["events"].events if e.type == "hit"]

    matched = 0
    unmatched_detections = 0
    remaining = list(truth_hits)
    for e in detected:
        close = [t for t in remaining if abs(t - e.t) <= tol["hit_t_s"]]
        if close:
            matched += 1
            remaining.remove(close[0])
        else:
            unmatched_detections += 1

    assert matched >= tol["min_hits_recovered"], (
        f"only {matched} of {len(truth_hits)} hits matched; "
        f"detected at {[e.t for e in detected]}, truth {truth_hits}"
    )
    assert unmatched_detections <= tol["max_false_positives"], (
        f"{unmatched_detections} false positives at {[e.t for e in detected]}"
    )


def test_b2_ko_time(pipeline):
    truth = pipeline["truth"]["ko"]
    tol = pipeline["truth"]["tolerances"]
    kos = [e for e in pipeline["events"].events if e.type == "ko"]
    assert len(kos) == 1
    assert abs(kos[0].t - truth["t"]) <= tol["ko_t_s"]
    assert kos[0].actor == truth["winner"]
    assert kos[0].target == truth["loser"]


def test_b2_hit_actors_are_plausible(pipeline):
    """The fixture scripts most hits with BOT_A as the aggressor."""
    truth_by_t = {h["t"]: h["actor"] for h in pipeline["truth"]["hits"]}
    detected = [e for e in pipeline["events"].events if e.type == "hit"]
    checked = agreed = 0
    for e in detected:
        close = [t for t in truth_by_t if abs(t - e.t) <= 1.0]
        if close:
            checked += 1
            agreed += e.actor == truth_by_t[close[0]]
    assert checked > 0
    assert agreed / checked >= 0.6, f"actor attribution only {agreed}/{checked}"


# ------------------------------------------------------------------ B3


def test_b3_momentum_present_and_bounded(pipeline):
    m = np.array(pipeline["telemetry"].series.momentum)
    assert len(m) > 100
    assert np.all((m[:, 1] >= 0) & (m[:, 1] <= 1))


def test_b3_curve_ends_at_the_winner(pipeline):
    """THE B3 acceptance criterion."""
    m = np.array(pipeline["telemetry"].series.momentum)
    ts, p = m[:, 0], m[:, 1]
    # Winner is bots[0]: after the KO the curve must be pinned near the ceiling.
    assert p[ts >= F.KO_T][-1] >= 0.98
    # After the mobility break the curve must favour bots[0]...
    post_break = p[(ts > F.MOBILITY_END_S) & (ts < F.KO_T)]
    assert np.median(post_break) > 0.5
    # ...and by more than it did in the early, even part of the fight.
    early = p[ts < 60]
    assert np.median(post_break) > np.median(early)


# ------------------------------------------------------------------ B5


def test_b5_event_lift_on_hits(pipeline):
    """THE B5 acceptance criterion: lift > 1.5 on scripted hits."""
    min_lift = pipeline["truth"]["tolerances"]["min_event_lift"]
    lifts = {el.event_t: el.lift for el in pipeline["attention"].event_lift}
    assert lifts, "no event_lift computed"

    truth_hits = [h["t"] for h in pipeline["truth"]["hits"]]
    lifted = 0
    for t in truth_hits:
        close = [lift for et, lift in lifts.items() if abs(et - t) <= 1.5]
        if close and max(close) > min_lift:
            lifted += 1
    assert lifted >= 4, f"only {lifted} of {len(truth_hits)} hits show lift > {min_lift}: {lifts}"


def test_b5_ko_has_the_biggest_lift(pipeline):
    ko_lifts = [el.lift for el in pipeline["attention"].event_lift if el.type == "ko"]
    hit_lifts = [el.lift for el in pipeline["attention"].event_lift if el.type == "hit"]
    assert ko_lifts and hit_lifts
    assert max(ko_lifts) >= max(hit_lifts)


def test_b5_media_value_table(pipeline):
    """Robust to real fights coexisting with the fixture in data/processed:
    the fixture contributes one win for BOT_A and one loss for BOT_B, so we
    assert directional facts, not exact records."""
    media = pipeline["media"]
    names = {b.name for b in media.bots}
    assert {F.BOT_A, F.BOT_B} <= names
    winner = next(b for b in media.bots if b.name == F.BOT_A)
    wins, losses = (int(x) for x in (winner.record or "0-0").split("-"))
    assert wins >= 1, f"fixture win missing from {winner.record}"
    assert winner.perf_score > 0
    assert winner.fights >= 1
    assert all(b.media_value >= 0 for b in media.bots)
