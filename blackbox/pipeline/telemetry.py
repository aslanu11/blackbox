"""B1 - owner: Aslan.

Positions -> physics. Savitzky-Golay smoothing per contiguous wide segment ONLY
(never across a gap), speed, control(t), mobility index, heatmap PNGs. All
series resampled to 1 Hz for the frontend.

control(t) = 0.6 * center-occupancy-share + 0.4 * opponent-wall-proximity,
over a rolling 10 s window. Positive favours bots[0]. In [-1, 1].

mobility index = rolling-10s 90th-percentile speed / the median of that same
statistic over the bot's own first 60 s. Using each bot's OWN baseline makes a
slow bot that stays slow read as 1.0 and a fast bot that halves read as 0.5 -
it measures decay, not absolute speed. (The spec sketched a rolling-30s max;
that holds stale speed for the full window after a knockdown and detects the
fixture decay 40 s late - see DECISIONS.md.) Windows less than half-full of
real frames emit NaN rather than a guess.

Done when
---------
Fixture mobility decay for bots[1] is detected within 5 s of the scripted onset.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from scipy.signal import savgol_filter

from .. import schemas as S

__phase__ = "B1"
__owner__ = "Aslan"

# Tunables - one block, so a rules change at 17:00 is a constant edit.
SMOOTH_WINDOW = 9  # frames (0.9 s at 10 fps); must be odd
SMOOTH_ORDER = 2
CONTROL_WINDOW_S = 10.0
MOBILITY_WINDOW_S = 10.0
MOBILITY_PCT = 90.0
MOBILITY_MIN_FILL = 0.5  # window must be at least this full of real frames
BASELINE_WINDOW_S = 60.0
CENTER_RADIUS_M = 3.5  # "holding the centre" zone
WALL_NEAR_M = 2.0  # opponent within this of a wall counts as pinned
HEATMAP_BINS = 40


# --------------------------------------------------------------------------
# Segments
# --------------------------------------------------------------------------


def wide_segments(tracks: S.Tracks) -> list[tuple[int, int]]:
    """Contiguous runs of wide frames as [start, end) index pairs."""
    segs: list[tuple[int, int]] = []
    start: int | None = None
    for i, fr in enumerate(tracks.frames):
        if fr.wide and start is None:
            start = i
        elif not fr.wide and start is not None:
            segs.append((start, i))
            start = None
    if start is not None:
        segs.append((start, len(tracks.frames)))
    return segs


def smoothed_positions(tracks: S.Tracks, bot: str) -> np.ndarray:
    """(N, 2) positions, Savitzky-Golay smoothed per wide segment, NaN in gaps."""
    n = len(tracks.frames)
    out = np.full((n, 2), np.nan)
    for s, e in wide_segments(tracks):
        xy = np.array([tracks.frames[i].pos[bot] for i in range(s, e)])
        if e - s >= SMOOTH_WINDOW:
            xy = savgol_filter(xy, SMOOTH_WINDOW, SMOOTH_ORDER, axis=0)
        out[s:e] = xy
    return out


def speeds(tracks: S.Tracks, bot: str) -> np.ndarray:
    """(N,) speed in m/s from smoothed positions. NaN in gaps and at seams.

    Differentiated inside each segment independently so a gap never produces a
    huge phantom velocity across a camera cut.
    """
    n = len(tracks.frames)
    out = np.full(n, np.nan)
    pos = smoothed_positions(tracks, bot)
    for s, e in wide_segments(tracks):
        if e - s < 2:
            continue
        v = np.linalg.norm(np.diff(pos[s:e], axis=0), axis=1) * tracks.fps
        out[s + 1 : e] = v
        out[s] = v[0]  # first frame of a segment borrows its neighbour
    return out


# --------------------------------------------------------------------------
# Metrics
# --------------------------------------------------------------------------


def _rolling_mean(x: np.ndarray, window: int) -> np.ndarray:
    """NaN-tolerant trailing rolling mean."""
    out = np.full_like(x, np.nan, dtype=float)
    for i in range(len(x)):
        w = x[max(0, i - window + 1) : i + 1]
        if not np.all(np.isnan(w)):
            out[i] = np.nanmean(w)
    return out


def _rolling_pct(x: np.ndarray, window: int, q: float, min_fill: float) -> np.ndarray:
    """Trailing rolling percentile. Under-filled windows (gaps) emit NaN -
    a statistic computed over two frames after a camera cut is noise."""
    out = np.full_like(x, np.nan, dtype=float)
    need = max(int(window * min_fill), 2)
    for i in range(len(x)):
        w = x[max(0, i - window + 1) : i + 1]
        ok = w[~np.isnan(w)]
        if len(ok) >= need:
            out[i] = np.percentile(ok, q)
    return out


def control_series(tracks: S.Tracks, bots: list[str]) -> np.ndarray:
    """(N,) control in [-1, 1], positive favouring bots[0]."""
    pos_a = smoothed_positions(tracks, bots[0])
    pos_b = smoothed_positions(tracks, bots[1])
    center = np.array([S.FLOOR_M / 2, S.FLOOR_M / 2])

    in_center_a = (np.linalg.norm(pos_a - center, axis=1) < CENTER_RADIUS_M).astype(float)
    in_center_b = (np.linalg.norm(pos_b - center, axis=1) < CENTER_RADIUS_M).astype(float)
    in_center_a[np.isnan(pos_a[:, 0])] = np.nan
    in_center_b[np.isnan(pos_b[:, 0])] = np.nan

    def wall_dist(p: np.ndarray) -> np.ndarray:
        return np.minimum.reduce([p[:, 0], p[:, 1], S.FLOOR_M - p[:, 0], S.FLOOR_M - p[:, 1]])

    # Your score rises when the OPPONENT is near a wall.
    pinned_b = (wall_dist(pos_b) < WALL_NEAR_M).astype(float)
    pinned_a = (wall_dist(pos_a) < WALL_NEAR_M).astype(float)
    pinned_b[np.isnan(pos_b[:, 0])] = np.nan
    pinned_a[np.isnan(pos_a[:, 0])] = np.nan

    window = int(CONTROL_WINDOW_S * tracks.fps)
    center_share = _rolling_mean(in_center_a, window) - _rolling_mean(in_center_b, window)
    wall_share = _rolling_mean(pinned_b, window) - _rolling_mean(pinned_a, window)
    return np.clip(0.6 * center_share + 0.4 * wall_share, -1.0, 1.0)


def mobility_series(tracks: S.Tracks, bot: str) -> np.ndarray:
    """(N,) mobility index: rolling p90 speed over the bot's own baseline.

    Baseline = median of the SAME rolling statistic over the first 60 s, so
    the numerator and denominator have identical response to hit rebounds and
    quiet phases. 1.0 = moving like it did fresh; near 0 = dead."""
    v = speeds(tracks, bot)
    window = int(MOBILITY_WINDOW_S * tracks.fps)
    rolling = _rolling_pct(v, window, MOBILITY_PCT, MOBILITY_MIN_FILL)

    baseline_window = rolling[window : int(BASELINE_WINDOW_S * tracks.fps)]
    ok = baseline_window[~np.isnan(baseline_window)]
    if len(ok) == 0:
        return np.full_like(v, np.nan)
    baseline = float(np.median(ok))
    if baseline <= 0:
        return np.full_like(v, np.nan)
    return np.clip(rolling / baseline, 0.0, 1.5)


# --------------------------------------------------------------------------
# Resampling + output
# --------------------------------------------------------------------------


def to_1hz(ts: np.ndarray, values: np.ndarray, duration_s: float) -> S.Series:
    """[t, value] pairs at 1 Hz. Seconds with no data in gaps are skipped -
    the frontend renders the absence, we never invent a number."""
    out: S.Series = []
    for sec in range(int(duration_s) + 1):
        mask = (ts >= sec) & (ts < sec + 1) & ~np.isnan(values)
        if mask.any():
            out.append([float(sec), round(float(values[mask].mean()), 4)])
    return out


def heatmap_png(tracks: S.Tracks, bot: str, color: str, out_dir: Path) -> str:
    """2D presence histogram, transparent background, bot-coloured."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import LinearSegmentedColormap

    pos = smoothed_positions(tracks, bot)
    ok = ~np.isnan(pos[:, 0])
    fig, ax = plt.subplots(figsize=(4, 4), dpi=120)
    if ok.any():
        cmap = LinearSegmentedColormap.from_list("bot", [(0, 0, 0, 0), color])
        ax.hist2d(
            pos[ok, 0], pos[ok, 1],
            bins=HEATMAP_BINS, range=[[0, S.FLOOR_M], [0, S.FLOOR_M]], cmap=cmap,
        )
    ax.set_xlim(0, S.FLOOR_M)
    ax.set_ylim(0, S.FLOOR_M)
    ax.set_aspect("equal")
    ax.axis("off")

    name = f"{bot.lower().replace(' ', '_')}_heat.png"
    out_dir.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_dir / name, transparent=True, bbox_inches="tight", pad_inches=0)
    plt.close(fig)
    return name


def compute(fight_id: str) -> Path:
    """tracks.json + meta.json -> telemetry.json (+ heatmap PNGs)."""
    meta = S.load_meta(fight_id)
    tracks = S.load_tracks(fight_id)
    bots = meta.bots
    ts = np.array([f.t for f in tracks.frames])
    duration = float(ts[-1]) if len(ts) else 0.0
    out_dir = S.fight_dir(fight_id, create=True)

    control = control_series(tracks, bots)
    series = S.TelemetrySeries(
        momentum=[],  # B3 fills this; an empty lane is honest until then
        control=to_1hz(ts, control, duration),
        speed={b: to_1hz(ts, speeds(tracks, b), duration) for b in bots},
        mobility={b: to_1hz(ts, mobility_series(tracks, b), duration) for b in bots},
    )
    heatmaps = {
        b: heatmap_png(tracks, b, meta.colors.get(b, "#888888"), out_dir) for b in bots
    }

    telemetry = S.Telemetry(fight_id=fight_id, series=series, heatmap_png=heatmaps)
    return S.save_telemetry(telemetry)
