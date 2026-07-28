"""B5 - owner: Aslan.

Attention x telemetry fusion, and the league-wide media-value table.

event_lift = mean attention in a +/-5 s window around each event / the fight's
baseline attention. The baseline is the QUIET baseline (20th percentile) - see
DECISIONS.md; a median baseline flattens every lift.

media_value = screen_s * attn_index, where screen_s is the bot's wide-coverage
seconds and attn_index is mean fight attention / baseline. The formula is
deliberately simple: seconds on screen, weighted by how much people actually
rewatched them. perf_score = wins / fights from FightMeta results.

Done when
---------
Fixture attention bumps give event_lift above 1.5 on the scripted hits and
roughly baseline elsewhere.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from .. import schemas as S

__phase__ = "B5"
__owner__ = "Aslan"

LIFT_WINDOW_S = 5.0


def event_lift(attention: S.Attention, events: S.Events) -> list[S.EventLift]:
    """Mean attention in +/-LIFT_WINDOW_S around each event, over baseline."""
    if not attention.points:
        return []
    pts = np.array(attention.points)
    ts, vals = pts[:, 0], pts[:, 1]
    baseline = attention.stats.baseline or float(np.percentile(vals, 20))
    if baseline <= 0:
        return []

    lifts: list[S.EventLift] = []
    for e in events.events:
        window = vals[np.abs(ts - e.t) <= LIFT_WINDOW_S]
        if len(window) == 0:
            continue
        lifts.append(
            S.EventLift(event_t=e.t, type=e.type, lift=round(float(window.mean() / baseline), 2))
        )
    return lifts


def fuse(fight_id: str) -> Path:
    """attention.json + events.json -> attention.json with event_lift filled."""
    attention = S.load_attention(fight_id)
    events = S.load_events(fight_id)
    attention.event_lift = event_lift(attention, events)
    return S.save_attention(attention)


# --------------------------------------------------------------------------
# League-wide media value
# --------------------------------------------------------------------------


def _screen_seconds(tracks: S.Tracks) -> float:
    """Wide-coverage seconds. Both bots share the wide shot, so both get credit."""
    return sum(1.0 / tracks.fps for f in tracks.frames if f.wide)


def media_value() -> Path:
    """Aggregate every processed fight into media_value.json."""
    bots: dict[str, dict] = {}

    for fid in S.list_fights():
        if not S.exists(fid, "meta"):
            continue
        meta = S.load_meta(fid)

        attn_index = 0.0
        if S.exists(fid, "attention"):
            attention = S.load_attention(fid)
            if attention.points and attention.stats.baseline > 0:
                vals = np.array(attention.points)[:, 1]
                attn_index = float(vals.mean() / attention.stats.baseline)

        screen_s = 0.0
        if S.exists(fid, "tracks"):
            screen_s = _screen_seconds(S.load_tracks(fid))
        elif meta.video.duration_s:
            # No tracking (proleague/corpus roles): the whole clip counts.
            screen_s = float(meta.video.duration_s)

        for b in meta.bots:
            entry = bots.setdefault(
                b, {"fights": 0, "screen_s": 0.0, "attn_sum": 0.0, "attn_n": 0, "wins": 0, "losses": 0}
            )
            entry["fights"] += 1
            entry["screen_s"] += screen_s
            if attn_index > 0:
                entry["attn_sum"] += attn_index
                entry["attn_n"] += 1
            if meta.result.winner == b:
                entry["wins"] += 1
            elif meta.result.winner is not None:
                entry["losses"] += 1

    rows: list[S.BotMediaValue] = []
    for name, e in bots.items():
        attn_index = e["attn_sum"] / e["attn_n"] if e["attn_n"] else 0.0
        decided = e["wins"] + e["losses"]
        rows.append(
            S.BotMediaValue(
                name=name,
                fights=e["fights"],
                screen_s=round(e["screen_s"], 1),
                attn_index=round(attn_index, 2),
                media_value=round(e["screen_s"] * attn_index, 1),
                record=f"{e['wins']}-{e['losses']}",
                perf_score=round(e["wins"] / decided, 2) if decided else 0.0,
            )
        )
    rows.sort(key=lambda r: r.media_value, reverse=True)
    return S.save_media_value(S.MediaValue(bots=rows))
