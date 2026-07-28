"""B3 - owner: Aslan.

P(bots[0] wins)(t) = logistic(w . [control, rolling-30s hit-magnitude
differential, mobility differential]).

Hard constraint: from KO-5s the winner's probability ramps to 0.99 - the model
is not allowed to be coy about a robot that is visibly dead.

`bb momentum --calibrate` buckets predictions vs outcomes across every
processed fight -> reliability curve PNG + Brier score. That plot is the
honest-caveats section of the README.

Done when
---------
The fixture curve trends toward the KO winner and crosses 0.5 in the right
direction after the mobility break.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from .. import schemas as S

__phase__ = "B3"
__owner__ = "Aslan"

# Hand-tuned weights. Each channel's contribution is BOUNDED (tanh squash on
# the open-ended hit differential, clamp on the total) so no single stream of
# evidence can saturate the curve. Real fights produce rolling hit
# differentials of +/-17; linear at 0.25/point that alone pinned P at 0.0001
# for most of a fight - false certainty the product must never display.
W_CONTROL = 1.2
W_HITS = 1.5  # cap of the tanh-squashed hit-differential term
HIT_DIFF_SCALE = 8.0  # rolling differential (magnitude points) at ~76% of cap
W_MOBILITY = 2.2
#: Max |logit| outside the KO ramp: probabilities stay within ~[0.05, 0.95].
LOGIT_CLAMP = 3.0
HIT_WINDOW_S = 30.0
KO_RAMP_S = 5.0
KO_CEILING = 0.99


def _logistic(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-x))


def _series_to_grid(series: S.Series, seconds: np.ndarray, fill: float) -> np.ndarray:
    """A sparse 1 Hz [t, v] series onto a dense per-second grid.

    Gaps carry the last known value forward - momentum shouldn't snap back to
    even odds just because the camera cut away.
    """
    out = np.full(len(seconds), fill)
    if not series:
        return out
    arr = np.array(series)
    known_t = arr[:, 0].astype(int)
    known_v = arr[:, 1]
    last = fill
    lookup = dict(zip(known_t.tolist(), known_v.tolist()))
    for i, sec in enumerate(seconds):
        if int(sec) in lookup:
            last = lookup[int(sec)]
        out[i] = last
    return out


def compute(fight_id: str) -> Path:
    """telemetry.json + events.json + meta.json -> momentum series into telemetry.json."""
    meta = S.load_meta(fight_id)
    telemetry = S.load_telemetry(fight_id)
    events = S.load_events(fight_id)
    bots = meta.bots

    # The per-second grid spans whatever telemetry covered.
    all_ts = [p[0] for p in telemetry.series.control]
    for b in bots:
        all_ts.extend(p[0] for p in telemetry.series.mobility.get(b, []))
    if not all_ts:
        raise RuntimeError(f"{fight_id}: telemetry has no series - run `bb telemetry` first")
    seconds = np.arange(0.0, max(all_ts) + 1.0)

    control = _series_to_grid(telemetry.series.control, seconds, 0.0)
    mob_a = _series_to_grid(telemetry.series.mobility.get(bots[0], []), seconds, 1.0)
    mob_b = _series_to_grid(telemetry.series.mobility.get(bots[1], []), seconds, 1.0)

    # Rolling hit-magnitude differential: hits BY bots[0] minus hits ON bots[0].
    hit_diff = np.zeros(len(seconds))
    for e in events.events:
        if e.type not in ("hit", "hazard") or e.magnitude is None:
            continue
        sign = 0.0
        if e.actor == bots[0] or (e.type == "hazard" and e.target == bots[1]):
            sign = 1.0
        elif e.actor == bots[1] or (e.type == "hazard" and e.target == bots[0]):
            sign = -1.0
        window = (seconds >= e.t) & (seconds < e.t + HIT_WINDOW_S)
        hit_diff[window] += sign * e.magnitude

    logit = (
        W_CONTROL * control
        + W_HITS * np.tanh(hit_diff / HIT_DIFF_SCALE)
        + W_MOBILITY * (mob_a - mob_b)
    )
    p = _logistic(np.clip(logit, -LOGIT_CLAMP, LOGIT_CLAMP))

    # KO constraint: ramp the winner to KO_CEILING over the last KO_RAMP_S.
    ko = next((e for e in events.events if e.type == "ko"), None)
    if ko is not None and ko.actor in bots:
        target_p = KO_CEILING if ko.actor == bots[0] else 1.0 - KO_CEILING
        ramp = (seconds >= ko.t - KO_RAMP_S)
        u = np.clip((seconds[ramp] - (ko.t - KO_RAMP_S)) / KO_RAMP_S, 0.0, 1.0)
        p[ramp] = p[ramp] * (1.0 - u) + target_p * u

    telemetry.series.momentum = [[float(s), round(float(v), 4)] for s, v in zip(seconds, p)]
    return S.save_telemetry(telemetry)


# --------------------------------------------------------------------------
# Calibration across the corpus
# --------------------------------------------------------------------------


def calibrate(out_path: Path | None = None) -> dict:
    """Reliability curve + Brier score across every fight with momentum + a result."""
    samples: list[tuple[float, int]] = []  # (predicted P(bots[0]), actual outcome)
    for fid in S.list_fights():
        if not (S.exists(fid, "meta") and S.exists(fid, "telemetry")):
            continue
        meta = S.load_meta(fid)
        if meta.result.winner not in meta.bots:
            continue
        momentum = S.load_telemetry(fid).series.momentum
        if not momentum:
            continue
        outcome = 1 if meta.result.winner == meta.bots[0] else 0
        # Sample mid-fight only - the KO ramp would flatter the score.
        end_t = meta.result.time_s or momentum[-1][0]
        samples.extend((v, outcome) for t, v in momentum if t < end_t - KO_RAMP_S)

    if not samples:
        raise RuntimeError("no fights with momentum + a known result to calibrate on")

    preds = np.array([s[0] for s in samples])
    outcomes = np.array([s[1] for s in samples])
    brier = float(np.mean((preds - outcomes) ** 2))

    edges = np.linspace(0, 1, 11)
    bin_pred, bin_actual, bin_n = [], [], []
    for lo, hi in zip(edges[:-1], edges[1:]):
        mask = (preds >= lo) & (preds < hi)
        if mask.sum() > 0:
            bin_pred.append(float(preds[mask].mean()))
            bin_actual.append(float(outcomes[mask].mean()))
            bin_n.append(int(mask.sum()))

    out_path = out_path or (S.PROCESSED_DIR / "calibration.png")
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(5, 5), dpi=120)
    ax.plot([0, 1], [0, 1], "--", color="#8B98A5", linewidth=1, label="perfect")
    ax.plot(bin_pred, bin_actual, "o-", color="#FF5A1F", label="model")
    ax.set_xlabel("predicted P(bots[0] wins)")
    ax.set_ylabel("actual win rate")
    ax.set_title(f"Reliability - Brier {brier:.3f} ({len(samples)} samples)")
    ax.legend()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, bbox_inches="tight")
    import matplotlib.pyplot as _plt

    _plt.close(fig)

    return {"brier": brier, "n_samples": len(samples), "plot": str(out_path)}
