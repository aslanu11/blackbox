"""B4 - owner: Aslan.

The modern BattleBots rubric, 11 points: Damage 5, Aggression 3, Control 3.

Mode (a) full-telemetry, for hero fights with tracks:
    damage     <- opponent mobility decay + LLM damage delta
    aggression <- approach-initiation rate share (who closed distance)
    control    <- integral of control(t)
Mode (b) cheap-lane, for corpus fights with no tracking:
    per-minute keyframes -> llm.score_rubric(frames) structured scores

robbery_score = the disagreement margin vs the official verdict, 0 if we agree.
`bb scorecard --leaderboard` aggregates the Robbery Leaderboard to CSV + JSON.

Done when
---------
Runs in both modes; the mock-LLM test passes; the leaderboard sorts correctly.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np

from .. import llm
from .. import schemas as S
from .telemetry import mobility_series, smoothed_positions, wide_segments

__phase__ = "B4"
__owner__ = "Aslan"

DAMAGE_TOTAL, AGGRESSION_TOTAL, CONTROL_TOTAL = 5, 3, 3


def _split(total: int, share_a: float) -> list[int]:
    """Split `total` points by bots[0]'s share, clamped so both get >= 0."""
    a = int(round(np.clip(share_a, 0.0, 1.0) * total))
    return [a, total - a]


# --------------------------------------------------------------------------
# Mode (a): full telemetry
# --------------------------------------------------------------------------


def _score_full(fight_id: str, meta: S.FightMeta) -> S.RubricScores:
    tracks = S.load_tracks(fight_id)
    telemetry = S.load_telemetry(fight_id)
    bots = meta.bots

    # Damage <- how much MORE the opponent's mobility decayed than yours.
    # (The LLM damage delta joins in when keyframes exist - keyframes come from
    # D1 ingest, so on synthetic fights this is mobility-only.)
    def end_mobility(bot: str) -> float:
        m = mobility_series(tracks, bot)
        ok = m[~np.isnan(m)]
        return float(np.median(ok[-min(100, len(ok)) :])) if len(ok) else 1.0

    decay_a = 1.0 - min(end_mobility(bots[0]), 1.0)  # damage bots[0] SUSTAINED
    decay_b = 1.0 - min(end_mobility(bots[1]), 1.0)

    key_dir = S.FRAMES_DIR / fight_id / "key"
    if key_dir.exists():
        keys = sorted(key_dir.glob("*.jpg")) or sorted(key_dir.glob("*.png"))
        if len(keys) >= 2:
            for i, bot in enumerate(bots):
                delta = llm.damage_assess(keys[0], keys[-1], bot)["damage_delta"]
                if i == 0:
                    decay_a = 0.5 * decay_a + 0.5 * delta
                else:
                    decay_b = 0.5 * decay_b + 0.5 * delta

    total_decay = decay_a + decay_b
    damage_share_a = decay_b / total_decay if total_decay > 0 else 0.5  # you DEALT what they sustained

    # Aggression <- who initiated approaches: frames where the gap is closing
    # and this bot is moving toward the opponent faster than the opponent is.
    pos_a = smoothed_positions(tracks, bots[0])
    pos_b = smoothed_positions(tracks, bots[1])
    init_a = init_b = 0
    for s, e in wide_segments(tracks):
        if e - s < 3:
            continue
        va = np.diff(pos_a[s:e], axis=0) * tracks.fps
        vb = np.diff(pos_b[s:e], axis=0) * tracks.fps
        gap = pos_b[s : e - 1] - pos_a[s : e - 1]
        dist = np.linalg.norm(gap, axis=1, keepdims=True)
        dist[dist == 0] = 1e-9
        u = gap / dist
        appr_a = np.einsum("ij,ij->i", va, u)  # bots[0] closing speed
        appr_b = np.einsum("ij,ij->i", vb, -u)
        closing = (appr_a + appr_b) > 0.3
        init_a += int(np.sum(closing & (appr_a > appr_b)))
        init_b += int(np.sum(closing & (appr_b > appr_a)))
    aggression_share_a = init_a / (init_a + init_b) if (init_a + init_b) else 0.5

    # Control <- integral of control(t) mapped from [-1, 1] to a share.
    ctrl = np.array([v for _, v in telemetry.series.control]) if telemetry.series.control else np.array([0.0])
    control_share_a = float((ctrl.mean() + 1.0) / 2.0)

    damage = _split(DAMAGE_TOTAL, damage_share_a)
    aggression = _split(AGGRESSION_TOTAL, aggression_share_a)
    control = _split(CONTROL_TOTAL, control_share_a)

    pts_a = damage[0] + aggression[0] + control[0]
    pts_b = damage[1] + aggression[1] + control[1]
    margin = abs(pts_a - pts_b) / (DAMAGE_TOTAL + AGGRESSION_TOTAL + CONTROL_TOTAL)
    return S.RubricScores(
        damage=damage,
        aggression=aggression,
        control=control,
        winner="A" if pts_a >= pts_b else "B",
        margin=round(margin, 2),
    )


# --------------------------------------------------------------------------
# Mode (b): cheap lane
# --------------------------------------------------------------------------


def _score_cheap(fight_id: str, meta: S.FightMeta) -> S.RubricScores:
    key_dir = S.FRAMES_DIR / fight_id / "key"
    keys = sorted(key_dir.glob("*.jpg")) + sorted(key_dir.glob("*.png"))
    if not keys:
        raise FileNotFoundError(
            f"{fight_id}: no keyframes in {key_dir}. Run `bb ingest --fight-id {fight_id}` "
            f"(or this fight can't be scored without tracking)."
        )
    # One frame per minute is plenty for a judge-style read; cap the bill.
    step = max(len(keys) // 6, 1)
    sample = keys[::step][:8]

    result = llm.score_rubric([str(p) for p in sample], meta.bots)
    damage = [int(x) for x in result["damage"]]
    aggression = [int(x) for x in result["aggression"]]
    control = [int(x) for x in result["control"]]

    pts_a = damage[0] + aggression[0] + control[0]
    pts_b = damage[1] + aggression[1] + control[1]
    margin = abs(pts_a - pts_b) / (DAMAGE_TOTAL + AGGRESSION_TOTAL + CONTROL_TOTAL)
    return S.RubricScores(
        damage=damage,
        aggression=aggression,
        control=control,
        winner="A" if pts_a >= pts_b else "B",
        margin=round(margin, 2),
    )


# --------------------------------------------------------------------------
# Entry points
# --------------------------------------------------------------------------


def score(fight_id: str) -> Path:
    """meta (+tracks/telemetry or keyframes) -> scorecard.json."""
    meta = S.load_meta(fight_id)

    if S.exists(fight_id, "tracks") and S.exists(fight_id, "telemetry"):
        ours = _score_full(fight_id, meta)
    else:
        ours = _score_cheap(fight_id, meta)

    # Official verdict from FightMeta. A KO is its own verdict - robbery only
    # applies to judges' decisions, but we still record the winner.
    official = S.OfficialVerdict(winner=None, split=None)
    if meta.result.winner in meta.bots:
        official.winner = "A" if meta.result.winner == meta.bots[0] else "B"

    robbery = 0.0
    if official.winner is not None and meta.result.method == "jd" and official.winner != ours.winner:
        robbery = ours.margin

    return S.save_scorecard(
        S.Scorecard(fight_id=fight_id, ours=ours, official=official, robbery_score=round(robbery, 2))
    )


def leaderboard() -> tuple[Path, Path]:
    """Aggregate every scorecard into the Robbery Leaderboard (JSON + CSV)."""
    rows = []
    for fid in S.list_fights():
        if not (S.exists(fid, "scorecard") and S.exists(fid, "meta")):
            continue
        sc = S.load_scorecard(fid)
        meta = S.load_meta(fid)
        ours = meta.bots[0] if sc.ours.winner == "A" else meta.bots[1]
        official = (
            None
            if sc.official.winner is None
            else meta.bots[0] if sc.official.winner == "A" else meta.bots[1]
        )
        rows.append(
            {
                "fight_id": fid,
                "bots": " vs ".join(meta.bots),
                "our_winner": ours,
                "official_winner": official,
                "split": sc.official.split,
                "robbery_score": sc.robbery_score,
            }
        )
    rows.sort(key=lambda r: r["robbery_score"], reverse=True)

    json_path = S.PROCESSED_DIR / "robbery_leaderboard.json"
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps({"fights": rows}, indent=2) + "\n", encoding="utf-8")

    csv_path = S.PROCESSED_DIR / "robbery_leaderboard.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else ["fight_id"])
        writer.writeheader()
        writer.writerows(rows)
    return json_path, csv_path
