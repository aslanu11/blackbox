"""A3 acceptance — the synthetic fight is valid, deterministic, and matches its
own ground truth.

These tests are the contract between the fixture and every downstream module.
If a downstream module cannot hit its acceptance number, check here first: the
fixture is allowed to be hard, but it must not be wrong.
"""

from __future__ import annotations

import json

import numpy as np
import pytest

from blackbox import fixtures as F
from blackbox import schemas as S


@pytest.fixture(scope="module")
def built():
    F.build()
    return {
        "meta": S.load_meta(F.FIGHT_ID),
        "tracks": S.load_tracks(F.FIGHT_ID),
        "attention": S.load_attention(F.FIGHT_ID),
        "truth": json.loads((S.fight_dir(F.FIGHT_ID) / "expected_events.json").read_text(encoding="utf-8")),
    }


def test_artifacts_validate_against_schemas(built):
    assert isinstance(built["meta"], S.FightMeta)
    assert isinstance(built["tracks"], S.Tracks)
    assert isinstance(built["attention"], S.Attention)


def test_generation_is_deterministic(built):
    first = S.load_tracks(F.FIGHT_ID).model_dump_json()
    F.build()
    assert S.load_tracks(F.FIGHT_ID).model_dump_json() == first


def test_frame_count_and_fps(built):
    tr = built["tracks"]
    assert tr.fps == F.FPS
    assert len(tr.frames) == int(F.DURATION_S * F.FPS)


def test_coverage_is_about_eighty_percent(built):
    assert built["tracks"].coverage == pytest.approx(built["truth"]["expected_coverage"], abs=0.005)
    assert 0.75 <= built["tracks"].coverage <= 0.85


def test_gaps_are_explicit_and_never_interpolated(built):
    for fr in built["tracks"].frames:
        in_gap = any(g0 <= fr.t < g1 for g0, g1 in F.GAPS)
        assert fr.wide is not in_gap, f"t={fr.t} wide flag disagrees with the scripted gaps"
        assert (fr.pos is None) == in_gap, f"t={fr.t} must carry pos=None inside a gap"


def test_positions_stay_inside_the_box(built):
    for fr in built["tracks"].frames:
        if fr.pos is None:
            continue
        for xy in fr.pos.values():
            assert 0.0 <= xy[0] <= S.FLOOR_M
            assert 0.0 <= xy[1] <= S.FLOOR_M


def _series(tracks: S.Tracks, bot: str):
    ts = np.array([f.t for f in tracks.frames])
    xy = np.array([f.pos[bot] if f.pos else [np.nan, np.nan] for f in tracks.frames])
    return ts, xy


def test_bots_are_close_at_each_scripted_hit(built):
    """events.py requires separation under 2.5 m at a hit."""
    tr = built["tracks"]
    ts, a = _series(tr, F.BOT_A)
    _, b = _series(tr, F.BOT_B)
    sep = np.linalg.norm(a - b, axis=1)
    for hit in built["truth"]["hits"]:
        i = int(np.argmin(np.abs(ts - hit["t"])))
        assert sep[i] < 2.5, f"hit at t={hit['t']} has separation {sep[i]:.2f} m"


def _wide_segments(tracks: S.Tracks) -> list[tuple[int, int]]:
    """Contiguous runs of wide frames, as [start, end) index pairs."""
    segs, start = [], None
    for i, fr in enumerate(tracks.frames):
        if fr.wide and start is None:
            start = i
        elif not fr.wide and start is not None:
            segs.append((start, i))
            start = None
    if start is not None:
        segs.append((start, len(tracks.frames)))
    return segs


def _joint_delta_v(tracks: S.Tracks) -> np.ndarray:
    """Joint |dv| per frame, computed the way the pipeline will compute it.

    Savitzky-Golay smoothing first, per contiguous wide segment only and never
    across a gap (spec §B1). Without smoothing this measurement is dominated by
    the 3 cm of tracker noise baked into the fixture and shows nothing.
    """
    from scipy.signal import savgol_filter

    n = len(tracks.frames)
    joint = np.full(n, np.nan)
    for s, e in _wide_segments(tracks):
        if e - s < 11:
            continue
        acc = np.zeros(e - s - 2)
        for bot in (F.BOT_A, F.BOT_B):
            xy = np.array([tracks.frames[i].pos[bot] for i in range(s, e)])
            xy = savgol_filter(xy, window_length=9, polyorder=2, axis=0)
            vel = np.diff(xy, axis=0) * F.FPS
            acc += np.linalg.norm(np.diff(vel, axis=0), axis=1) * F.FPS
        joint[s + 1 : e - 1] = acc
    return joint


@pytest.fixture(scope="module")
def impact(built):
    """Joint |dv| plus its baseline — computed once, it is not cheap."""
    tr = built["tracks"]
    joint = _joint_delta_v(tr)
    return {
        "ts": np.array([f.t for f in tr.frames]),
        "joint": joint,
        "baseline": float(np.nanmedian(joint)),
    }


def test_hits_are_recoverable_at_the_rate_b2_must_achieve(impact, built):
    """Mirrors the B2 acceptance criterion: at least 4 of 5 hits clearly spike.

    The weakest scripted hit is allowed to be marginal — real fights have
    glancing blows, and the spec budgets for missing one. What is NOT allowed is
    a hit that leaves no trace at all.
    """
    ts, joint, baseline = impact["ts"], impact["joint"], impact["baseline"]

    peaks = []
    for hit in built["truth"]["hits"]:
        i = int(np.argmin(np.abs(ts - hit["t"])))
        peak = float(np.nanmax(joint[max(0, i - 5) : i + 6]))
        peaks.append(peak)
        assert peak > 3.0 * baseline, (
            f"hit at t={hit['t']} leaves no trace "
            f"(peak {peak:.2f} vs baseline {baseline:.2f})"
        )

    clear = sum(p > 4.0 * baseline for p in peaks)
    assert clear >= built["truth"]["tolerances"]["min_hits_recovered"], (
        f"only {clear} of {len(peaks)} hits spike clearly; B2 needs at least "
        f"{built['truth']['tolerances']['min_hits_recovered']}"
    )


def test_quiet_stretches_do_not_look_like_hits(impact, built):
    """B2 is allowed at most 1 false positive — the fixture must not be noisy."""
    ts, joint, baseline = impact["ts"], impact["joint"], impact["baseline"]

    near_hit = np.zeros(len(ts), dtype=bool)
    for hit in built["truth"]["hits"]:
        near_hit |= np.abs(ts - hit["t"]) <= 3.0
    quiet = joint[~near_hit]
    assert np.nanmax(quiet) < 4.0 * baseline, "a quiet stretch would trip the hit detector"


def test_hit_magnitudes_are_recoverable_from_the_data(built):
    """A bigger scripted hit must actually look bigger.

    Measured the way events.py will measure it: the PEAK instantaneous
    separation rate just after contact. A 0.5 s average would saturate — the
    rebound completes in well under half a second for the harder hits — and so
    would report every hit as roughly equal.
    """
    tr = built["tracks"]
    ts, a = _series(tr, F.BOT_A)
    _, b = _series(tr, F.BOT_B)
    sep = np.linalg.norm(a - b, axis=1)
    rate = np.diff(sep) * F.FPS

    observed = []
    for hit in built["truth"]["hits"]:
        i = int(np.argmin(np.abs(ts - hit["t"])))
        observed.append(rate[i : i + 3].max())

    scripted = [h["magnitude"] for h in built["truth"]["hits"]]
    assert np.corrcoef(scripted, observed)[0, 1] > 0.85
    # And the recovered rate should be in the right ballpark, not just correlated.
    for s, o in zip(scripted, observed):
        assert 0.4 * s < o < 1.6 * s, f"scripted {s}, observed {o:.2f}"


def test_bot_b_slows_after_the_scripted_decay_onset(built):
    """B1 must be able to find this within 5 s."""
    tr = built["tracks"]
    ts, b = _series(tr, F.BOT_B)
    speed = np.linalg.norm(np.diff(b, axis=0), axis=1) * F.FPS
    mid = ts[:-1]

    before = np.nanmax(speed[(mid > 60) & (mid < F.MOBILITY_ONSET_S)])
    after = np.nanmax(speed[(mid > F.MOBILITY_END_S) & (mid < F.KO_T)])
    assert after < 0.4 * before, f"decay too weak: {before:.2f} -> {after:.2f} m/s"


def test_bot_a_stays_mobile_through_the_decay(built):
    """The decay must be asymmetric, or mobility differential says nothing."""
    tr = built["tracks"]
    ts, a = _series(tr, F.BOT_A)
    speed = np.linalg.norm(np.diff(a, axis=0), axis=1) * F.FPS
    mid = ts[:-1]
    after = np.nanmax(speed[(mid > F.MOBILITY_END_S) & (mid < F.KO_T)])
    assert after > 0.5


def test_attention_peaks_at_the_ko(built):
    at = built["attention"]
    assert at.stats.peak_t == pytest.approx(F.KO_T, abs=6.0)
    assert 0.0 < at.stats.baseline < at.stats.peak <= 1.0


def test_attention_bumps_sit_on_the_scripted_hits(built):
    """B5 acceptance depends on this: event_lift > 1.5 on hits, ~1.0 elsewhere."""
    pts = np.array(built["attention"].points)
    ts, vals = pts[:, 0], pts[:, 1]
    baseline = built["attention"].stats.baseline

    for hit in built["truth"]["hits"]:
        window = vals[np.abs(ts - hit["t"]) <= 5.0]
        assert window.mean() / baseline > 1.15, f"no attention bump at t={hit['t']}"

    quiet = vals[(ts > 5) & (ts < 15)]
    assert quiet.mean() / baseline < 1.15


def test_meta_records_the_ko(built):
    m = built["meta"]
    assert m.bots == [F.BOT_A, F.BOT_B]
    assert m.result.method == "ko"
    assert m.result.winner == F.KO_WINNER
    assert m.result.time_s == pytest.approx(F.KO_T)
    assert set(m.colors) == set(m.bots)
