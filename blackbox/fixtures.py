"""A3 — synthetic fight generator (spec §6, Phase A3).

Deterministic. Produces a 150 s @ 10 fps fight with *known* ground truth so every
downstream module can be built and accepted before real footage exists.

What is scripted
----------------
* Two bots on smooth curved paths inside the 48 ft box.
* Five hits: the pair closes to ~1 m, then separates sharply. The sharp
  separation is the joint velocity spike that ``events.py`` must recover.
* Mobility decay for ``bots[1]`` beginning at t=100 s (it slows and pins).
* KO at t=141.5 s.
* Three non-wide gaps totalling 30 s (20% of frames), present in ``tracks.json``
  as frames with ``pos=None`` — never interpolated across.
* An attention curve: baseline noise + gaussian bumps on each hit + a large
  bump at the KO.

The ground truth is also written to ``expected_events.json`` for tests. That file
is fixture-only scaffolding; it is not part of the §5 data contract.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

from . import schemas as S

# --------------------------------------------------------------------------
# Script — every constant here is ground truth the tests assert against.
# --------------------------------------------------------------------------

FIGHT_ID = "fixture-001"
BOT_A = "Minotaur"
BOT_B = "Bloodsport"
COLORS = {BOT_A: "#D4AF37", BOT_B: "#1E6FD9"}

DURATION_S = 150.0
FPS = 10
SEED = 20260728

#: (time, magnitude, actor). Actor is the bot with the higher approach velocity.
HITS: list[tuple[float, float, str]] = [
    (22.0, 6.2, BOT_A),
    (48.5, 8.9, BOT_A),
    (62.0, 4.5, BOT_B),
    (88.4, 7.4, BOT_A),
    (108.0, 9.6, BOT_A),
]

#: Bot B's mobility starts falling here and bottoms out at MOBILITY_FLOOR.
MOBILITY_ONSET_S = 100.0
MOBILITY_END_S = 114.0
MOBILITY_FLOOR = 0.12

KO_T = 141.5
KO_WINNER = BOT_A

#: Non-wide camera segments (close-ups / crowd / replays).
GAPS: list[tuple[float, float]] = [(30.0, 40.0), (75.0, 85.0), (128.0, 138.0)]

#: A hazard event, for the events lane to have a third glyph type.
HAZARD_T = 71.0
HAZARD_MAG = 5.0

# Geometry
_CENTER = np.array([S.FLOOR_M / 2, S.FLOOR_M / 2])
_MARGIN = 0.6
_MID_AMP = 2.4
_SEP_BASE = 3.6
_SEP_OSC = 1.2
_APPROACH_S = 1.6
_REBOUND_S = 2.6

# --------------------------------------------------------------------------
# Path model
# --------------------------------------------------------------------------


def _smoothstep(x: np.ndarray | float) -> np.ndarray | float:
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3.0 - 2.0 * x)


def _midpoint(t: np.ndarray) -> np.ndarray:
    """Slow Lissajous wander of the pair's midpoint. Shape (N, 2)."""
    x = _CENTER[0] + _MID_AMP * np.sin(2 * math.pi * t / 19.0)
    y = _CENTER[1] + _MID_AMP * np.sin(2 * math.pi * t / 23.0 + 1.1)
    return np.stack([x, y], axis=1)


def _direction(t: np.ndarray) -> np.ndarray:
    """Unit vector from B toward A, slowly rotating. Shape (N, 2)."""
    theta = 2 * math.pi * t / 27.0 + 0.4
    return np.stack([np.cos(theta), np.sin(theta)], axis=1)


def _separation(t: np.ndarray) -> np.ndarray:
    """Distance between bots, with a scripted collision profile at each hit."""
    d = _SEP_BASE + _SEP_OSC * np.sin(2 * math.pi * t / 13.0)
    for th, mag, _actor in HITS:
        d_at = float(_SEP_BASE + _SEP_OSC * math.sin(2 * math.pi * th / 13.0))

        # Approach: glide in to ~1 m over APPROACH_S. Gradual — no spike here.
        appr = (t >= th - _APPROACH_S) & (t < th)
        u = (t[appr] - (th - _APPROACH_S)) / _APPROACH_S
        d[appr] = d_at + (1.0 - d_at) * _smoothstep(u)

        # Rebound: separate sharply. Initial rate == `mag` m/s, which is what
        # events.py recovers as the hit magnitude.
        tau = max((d_at - 1.0) / mag, 0.05)
        reb = (t >= th) & (t < th + _REBOUND_S)
        d[reb] = 1.0 + (d_at - 1.0) * (1.0 - np.exp(-(t[reb] - th) / tau))
    return d


def _mobility_b(t: np.ndarray) -> np.ndarray:
    """Bot B's mobility multiplier: 1.0, then a scripted decay, then the KO."""
    m = np.ones_like(t)
    decay = (t >= MOBILITY_ONSET_S) & (t < MOBILITY_END_S)
    u = (t[decay] - MOBILITY_ONSET_S) / (MOBILITY_END_S - MOBILITY_ONSET_S)
    m[decay] = 1.0 - (1.0 - MOBILITY_FLOOR) * _smoothstep(u)
    m[t >= MOBILITY_END_S] = MOBILITY_FLOOR
    m[t >= KO_T] = 0.02
    return m


def _positions(t: np.ndarray, rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray]:
    """Floor positions for both bots. Shapes (N, 2)."""
    mid = _midpoint(t)
    u = _direction(t)
    d = _separation(t)
    mb = _mobility_b(t)

    # As B loses mobility it stops taking its share of the separation motion and
    # its own wander freezes toward wherever it was at decay onset. A is then
    # placed *relative to B*, so the distance between the bots is exactly d(t)
    # at every frame — including through the decay. events.py depends on that:
    # a hit is only a hit when separation < 2.5 m.
    share_b = 0.5 * mb

    onset_i = int(MOBILITY_ONSET_S * FPS)
    pin = mid[min(onset_i, len(mid) - 1)]
    mid_b = mid.copy()
    tail = slice(onset_i, None)
    mid_b[tail] = pin + (mid[tail] - pin) * mb[tail, None]

    pos_b = mid_b - (d[:, None] * share_b[:, None]) * u
    pos_a = pos_b + d[:, None] * u

    # Keep the pair inside the box by translating BOTH bots equally — clipping
    # them independently would corrupt the separation the hits depend on.
    lo, hi = _MARGIN, S.FLOOR_M - _MARGIN
    pair_lo = np.minimum(pos_a, pos_b)
    pair_hi = np.maximum(pos_a, pos_b)
    shift = np.maximum(lo - pair_lo, 0.0) - np.maximum(pair_hi - hi, 0.0)
    pos_a = pos_a + shift
    pos_b = pos_b + shift

    # Tracker noise — a few centimetres, so downstream smoothing has work to do.
    pos_a = pos_a + rng.normal(0.0, 0.03, pos_a.shape)
    pos_b = pos_b + rng.normal(0.0, 0.03, pos_b.shape)
    return pos_a, pos_b


def _is_wide(t: float) -> bool:
    return not any(g0 <= t < g1 for g0, g1 in GAPS)


# --------------------------------------------------------------------------
# Attention model
# --------------------------------------------------------------------------


def _attention(rng: np.random.Generator, n_points: int = 100) -> S.Attention:
    """Baseline noise + gaussian bumps on hits + a big bump at the KO."""
    ts = np.linspace(0.0, DURATION_S, n_points)
    vals = 0.30 + 0.04 * np.sin(2 * math.pi * ts / 41.0) + rng.normal(0.0, 0.015, n_points)

    for th, mag, _a in HITS:
        vals += (0.055 * mag) * np.exp(-((ts - th) ** 2) / (2 * 2.5**2))
    vals += 0.20 * np.exp(-((ts - HAZARD_T) ** 2) / (2 * 2.5**2))
    vals += 0.95 * np.exp(-((ts - KO_T) ** 2) / (2 * 4.5**2))

    vals = np.clip(vals, 0.0, None)
    vals = vals / vals.max() * 0.97  # YouTube heatmaps peak at ~1.0, not exactly

    peak_i = int(np.argmax(vals))
    return S.Attention(
        video_id=None,
        fight_id=FIGHT_ID,
        points=[[round(float(a), 3), round(float(b), 4)] for a, b in zip(ts, vals)],
        stats=S.AttentionStats(
            # The QUIET baseline, not the median — the median of a bump-heavy
            # curve is inflated by the bumps and would flatten every event_lift.
            baseline=round(float(np.percentile(vals, 20)), 4),
            peak=round(float(vals[peak_i]), 4),
            peak_t=round(float(ts[peak_i]), 2),
        ),
        event_lift=[],  # filled by fuse.py (B5) — deliberately empty here
    )


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------


def build() -> dict[str, Path]:
    """Generate the fixture fight and write all artifacts. Returns paths written."""
    rng = np.random.default_rng(SEED)
    t = np.arange(0.0, DURATION_S, 1.0 / FPS)
    pos_a, pos_b = _positions(t, rng)

    frames: list[S.TrackFrame] = []
    n_wide = 0
    for i, ti in enumerate(t):
        wide = _is_wide(float(ti))
        n_wide += wide
        frames.append(
            S.TrackFrame(
                t=round(float(ti), 2),
                wide=wide,
                pos=(
                    {
                        BOT_A: [round(float(pos_a[i, 0]), 3), round(float(pos_a[i, 1]), 3)],
                        BOT_B: [round(float(pos_b[i, 0]), 3), round(float(pos_b[i, 1]), 3)],
                    }
                    if wide
                    else None
                ),
            )
        )

    meta = S.FightMeta(
        fight_id=FIGHT_ID,
        episode=0,
        bots=[BOT_A, BOT_B],
        colors=COLORS,
        result=S.FightResult(winner=KO_WINNER, method="ko", time_s=KO_T),
        video=S.VideoRef(yt_id=None, fight_start_s=0.0, fight_end_s=DURATION_S),
        role="hero",
    )
    tracks = S.Tracks(
        fight_id=FIGHT_ID,
        fps=FPS,
        coverage=round(n_wide / len(frames), 3),
        frames=frames,
    )
    attention = _attention(rng)

    written = {
        "meta": S.save_meta(meta),
        "tracks": S.save_tracks(tracks),
        "attention": S.save_attention(attention),
        "expected": _write_expected(),
    }
    return written


def _write_expected() -> Path:
    """Ground truth for tests. Fixture-only — not a §5 contract artifact."""
    truth = {
        "fight_id": FIGHT_ID,
        "fps": FPS,
        "duration_s": DURATION_S,
        "hits": [
            {"t": th, "magnitude": mag, "actor": actor, "target": BOT_B if actor == BOT_A else BOT_A}
            for th, mag, actor in HITS
        ],
        "hazard": {"t": HAZARD_T, "magnitude": HAZARD_MAG, "target": BOT_B},
        "ko": {"t": KO_T, "winner": KO_WINNER, "loser": BOT_B},
        "mobility_decay": {"bot": BOT_B, "onset_s": MOBILITY_ONSET_S, "floor": MOBILITY_FLOOR},
        "gaps": [list(g) for g in GAPS],
        "expected_coverage": round(1.0 - sum(b - a for a, b in GAPS) / DURATION_S, 3),
        "tolerances": {
            "hit_t_s": 1.0,
            "ko_t_s": 3.0,
            "mobility_onset_s": 5.0,
            "min_hits_recovered": 4,
            "max_false_positives": 1,
            "min_event_lift": 1.5,
        },
    }
    path = S.fight_dir(FIGHT_ID, create=True) / "expected_events.json"
    path.write_text(json.dumps(truth, indent=2) + "\n", encoding="utf-8")
    return path
