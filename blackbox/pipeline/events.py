"""B2 - owner: Aslan.

Hit    = joint |dv| spike (both bots, summed, above threshold) while separation
         is under HIT_MAX_SEP_M. Magnitude = peak separation rate just after
         contact (see DECISIONS.md - an averaged rate saturates and loses the
         ordering). Actor = the bot with the higher approach velocity.
KO     = mobility index under KO_MOBILITY sustained KO_SUSTAIN_S, or taken from
         FightMeta.result when the broadcast told us.
Hazard = an impulse inside a hazard zone (the wall strip) without opponent
         proximity.

Done when
---------
At least 4 of the 5 fixture hits recovered within 1 s, at most 1 false
positive; KO time within 3 s.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from .. import schemas as S
from .telemetry import mobility_series, smoothed_positions, wide_segments

__phase__ = "B2"
__owner__ = "Aslan"

# Tunables.
HIT_MAX_SEP_M = 2.5  # bots must be at least this close for a spike to be a hit
HIT_SPIKE_FACTOR = 4.0  # joint |dv| must exceed factor * median to trigger
HIT_DEBOUNCE_S = 3.0  # merge triggers within this window into one hit
KO_MOBILITY = 0.15
KO_SUSTAIN_S = 10.0
HAZARD_MARGIN_M = 1.2  # hazard strip along the walls (screws/saws live there)
HAZARD_MIN_SEP_M = 3.0  # an impulse with the opponent this far away isn't a hit


def _joint_delta_v(tracks: S.Tracks, bots: list[str]) -> np.ndarray:
    """Summed |dv| per frame from smoothed positions, NaN outside wide segments."""
    n = len(tracks.frames)
    joint = np.full(n, np.nan)
    per_bot = {b: smoothed_positions(tracks, b) for b in bots}
    for s, e in wide_segments(tracks):
        if e - s < 4:
            continue
        acc = np.zeros(e - s - 2)
        for b in bots:
            vel = np.diff(per_bot[b][s:e], axis=0) * tracks.fps
            acc += np.linalg.norm(np.diff(vel, axis=0), axis=1) * tracks.fps
        joint[s + 1 : e - 1] = acc
    return joint


def _separation(tracks: S.Tracks, bots: list[str]) -> np.ndarray:
    a = smoothed_positions(tracks, bots[0])
    b = smoothed_positions(tracks, bots[1])
    return np.linalg.norm(a - b, axis=1)


def detect_hits(tracks: S.Tracks, bots: list[str]) -> list[S.Event]:
    ts = np.array([f.t for f in tracks.frames])
    joint = _joint_delta_v(tracks, bots)
    sep = _separation(tracks, bots)
    baseline = float(np.nanmedian(joint))
    if not np.isfinite(baseline) or baseline <= 0:
        return []

    pos = {b: smoothed_positions(tracks, b) for b in bots}
    vel = {b: np.gradient(pos[b], axis=0) * tracks.fps for b in bots}

    # Candidate frames: spike + proximity.
    candidates = np.where((joint > HIT_SPIKE_FACTOR * baseline) & (sep < HIT_MAX_SEP_M))[0]

    events: list[S.Event] = []
    last_t = -1e9
    i = 0
    while i < len(candidates):
        # Group the contiguous burst of candidate frames around one contact.
        j = i
        while j + 1 < len(candidates) and ts[candidates[j + 1]] - ts[candidates[j]] < HIT_DEBOUNCE_S:
            j += 1
        burst = candidates[i : j + 1]
        # The contact moment is the CLOSEST APPROACH within the burst, not the
        # biggest |dv| frame - the rebound tail also decelerates hard and can
        # out-spike the impact itself (it cost 2.2 s of timing error; see
        # DECISIONS.md). Expand the burst by a few frames each side so the
        # true minimum isn't clipped off.
        lo = max(int(burst[0]) - 5, 0)
        hi = min(int(burst[-1]) + 6, len(sep))
        window = np.arange(lo, hi)
        peak = int(window[np.nanargmin(sep[window])])
        t_hit = float(ts[peak])

        if t_hit - last_t >= HIT_DEBOUNCE_S:
            # Magnitude: peak separation rate in the ~0.5 s after contact.
            look = slice(peak, min(peak + 6, len(sep)))
            rate = np.diff(sep[look]) * tracks.fps
            magnitude = (
                float(np.nanmax(rate))
                if len(rate) and not np.all(np.isnan(rate))
                else float(joint[peak] / 2)
            )

            # Actor: higher approach velocity toward the opponent just before contact.
            pre = max(peak - 3, 0)
            gap = pos[bots[1]][pre] - pos[bots[0]][pre]
            norm = float(np.linalg.norm(gap))
            if norm > 0 and not np.any(np.isnan(gap)):
                u = gap / norm
                appr_a = float(np.dot(vel[bots[0]][pre], u))
                appr_b = float(np.dot(vel[bots[1]][pre], -u))
                actor, target = (bots[0], bots[1]) if appr_a >= appr_b else (bots[1], bots[0])
            else:
                actor, target = bots[0], bots[1]

            events.append(
                S.Event(
                    t=round(t_hit, 2),
                    type="hit",
                    magnitude=round(max(magnitude, 0.5), 2),
                    actor=actor,
                    target=target,
                )
            )
            last_t = t_hit
        i = j + 1
    return events


def detect_ko(tracks: S.Tracks, meta: S.FightMeta) -> S.Event | None:
    """KO from the broadcast result when present, else from mobility collapse."""
    bots = meta.bots
    if meta.result.method == "ko" and meta.result.time_s is not None:
        loser = next((b for b in bots if b != meta.result.winner), bots[1])
        return S.Event(t=round(meta.result.time_s, 2), type="ko", actor=meta.result.winner, target=loser)

    ts = np.array([f.t for f in tracks.frames])
    sustain = int(KO_SUSTAIN_S * tracks.fps)
    for b in bots:
        m = mobility_series(tracks, b)
        run = 0
        for i in range(len(m)):
            run = run + 1 if (not np.isnan(m[i]) and m[i] < KO_MOBILITY) else 0
            if run >= sustain:
                winner = next(x for x in bots if x != b)
                return S.Event(t=round(float(ts[i - sustain + 1]), 2), type="ko", actor=winner, target=b)
    return None


def detect_hazards(tracks: S.Tracks, bots: list[str]) -> list[S.Event]:
    """An impulse in the wall strip while the opponent is far away."""
    ts = np.array([f.t for f in tracks.frames])
    joint = _joint_delta_v(tracks, bots)
    sep = _separation(tracks, bots)
    baseline = float(np.nanmedian(joint))
    if not np.isfinite(baseline) or baseline <= 0:
        return []

    pos = {b: smoothed_positions(tracks, b) for b in bots}

    def in_hazard_zone(p: np.ndarray) -> np.ndarray:
        d = np.minimum.reduce([p[:, 0], p[:, 1], S.FLOOR_M - p[:, 0], S.FLOOR_M - p[:, 1]])
        return d < HAZARD_MARGIN_M

    events: list[S.Event] = []
    last_t = -1e9
    for b in bots:
        zone = in_hazard_zone(pos[b])
        idx = np.where((joint > HIT_SPIKE_FACTOR * baseline) & zone & (sep > HAZARD_MIN_SEP_M))[0]
        for i in idx:
            t = float(ts[i])
            if t - last_t >= HIT_DEBOUNCE_S:
                events.append(
                    S.Event(t=round(t, 2), type="hazard", magnitude=round(float(joint[i] / 2), 2), actor=None, target=b)
                )
                last_t = t
    return events


def detect(fight_id: str) -> Path:
    """tracks.json + meta.json -> events.json, sorted by time."""
    meta = S.load_meta(fight_id)
    tracks = S.load_tracks(fight_id)

    events = detect_hits(tracks, meta.bots)
    events.extend(detect_hazards(tracks, meta.bots))
    ko = detect_ko(tracks, meta)
    if ko is not None:
        # Anything "detected" after the KO is debris settling, not a fight event.
        events = [e for e in events if e.t < ko.t - 1.0]
        events.append(ko)
    events.sort(key=lambda e: e.t)

    return S.save_events(S.Events(fight_id=fight_id, events=events))
