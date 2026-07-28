"""Walk-forward backtest for the pre-bout model, plus an honest side-by-side
against blackbox/pipeline/momentum.py's in-fight model.

This is deliberately a separate report from `bb momentum --calibrate`
(blackbox/pipeline/momentum.py), not a patch to it — see experiments/README.md
for why. It only *reads* blackbox artifacts (schemas.list_fights/load_meta/
load_telemetry) and never writes into data/processed/<fight_id>/, so it can't
collide with anyone else's contract files.

Fair-comparison caveat (read before trusting the numbers)
----------------------------------------------------------
momentum.py produces a value *at every second of the fight*; this model
produces exactly one number, before the fight starts. Comparing prebout's
single number against momentum's *final* value would be comparing a genuine
forecast to a model that has already watched the whole fight - that's not a
fair fight, it's a foregone conclusion. So the paired comparison below uses
momentum's *earliest* available sample (closest to t=0) as the closest
same-information-horizon reference point. Both values are still recorded in
predictions.json so nobody has to take that choice on faith.
"""

from __future__ import annotations

import csv
import json
import math
from pathlib import Path
from typing import Any

from blackbox import schemas as S

from . import model as M

#: Deliberately a sibling of data/processed/, not inside it -
#: schemas.list_fights() treats every subdirectory of data/processed/ as a
#: fight id, so writing our output there would make `bb fights` list a
#: bogus "experiments" fight for everyone else.
OUT_DIR = S.DATA_DIR / "experiments" / "prebout"


def chronological_fights() -> list[S.FightMeta]:
    """Fights with a known winner, ordered by episode (undated fights last)."""
    metas = []
    for fid in S.list_fights():
        if not S.exists(fid, "meta"):
            continue
        meta = S.load_meta(fid)
        if meta.result.winner is not None and meta.result.winner in meta.bots:
            metas.append(meta)
    return sorted(metas, key=lambda m: (m.episode if m.episode is not None else math.inf, m.fight_id))


def _momentum_reference(fight_id: str) -> tuple[float | None, float | None]:
    """(earliest, final) momentum value for bots[0], or (None, None) if untracked."""
    if not S.exists(fight_id, "telemetry"):
        return None, None
    series = S.load_telemetry(fight_id).series.momentum
    if not series:
        return None, None
    series = sorted(series, key=lambda p: p[0])
    return float(series[0][1]), float(series[-1][1])


def _brier(samples: list[tuple[float, int]]) -> float:
    return sum((p - y) ** 2 for p, y in samples) / len(samples)


def _log_loss(samples: list[tuple[float, int]]) -> float:
    total = 0.0
    for p, y in samples:
        p = min(1 - 1e-9, max(1e-9, p))
        total += -(y * math.log(p) + (1 - y) * math.log(1 - p))
    return total / len(samples)


def _reliability_bins(samples: list[tuple[float, int]], n_bins: int = 10) -> list[dict]:
    edges = [i / n_bins for i in range(n_bins + 1)]
    bins = []
    for lo, hi in zip(edges[:-1], edges[1:]):
        bucket = [(p, y) for p, y in samples if lo <= p < hi or (hi == 1.0 and p == 1.0)]
        if bucket:
            bins.append(
                {
                    "range": [lo, hi],
                    "mean_predicted": sum(p for p, _ in bucket) / len(bucket),
                    "actual_win_rate": sum(y for _, y in bucket) / len(bucket),
                    "n": len(bucket),
                }
            )
    return bins


def _plot(samples: list[tuple[float, int]], brier: float, out_path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    bins = _reliability_bins(samples)
    fig, ax = plt.subplots(figsize=(5, 5), dpi=120)
    ax.plot([0, 1], [0, 1], "--", color="#8B98A5", linewidth=1, label="perfect")
    if bins:
        ax.plot(
            [b["mean_predicted"] for b in bins],
            [b["actual_win_rate"] for b in bins],
            "o-",
            color="#1F9E89",
            label="prebout model",
        )
    ax.set_xlabel("predicted P(bots[0] wins)")
    ax.set_ylabel("actual win rate")
    ax.set_title(f"Prebout reliability - Brier {brier:.3f} ({len(samples)} fights)")
    ax.legend()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, bbox_inches="tight")
    plt.close(fig)


def _pick(bots: list[str], p: float | None) -> str | None:
    """Which bot a P(bots[0] wins) value picks, or None if there's no value."""
    if p is None:
        return None
    return bots[0] if p >= 0.5 else bots[1]


def comparison_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """actual winner vs the generic (prebout) pick vs the main (momentum) pick,
    one row per fight - the quick side-by-side, independent of the fuller
    Brier/reliability stats above."""
    out = []
    for r in rows:
        bots = r["bots"]
        generic_pick = _pick(bots, r["prebout_p"])
        main_pick = _pick(bots, r["momentum_earliest_p"])
        out.append(
            {
                "fight_id": r["fight_id"],
                "bots": bots,
                "actual_winner": r["winner"],
                "generic_pick": generic_pick,
                "generic_p": r["prebout_p"],
                "generic_correct": generic_pick == r["winner"],
                "main_pick": main_pick,
                "main_p": r["momentum_earliest_p"],
                "main_correct": None if main_pick is None else main_pick == r["winner"],
            }
        )
    return out


def _write_comparison(rows: list[dict[str, Any]], out_dir: Path) -> None:
    comp = comparison_rows(rows)
    (out_dir / "comparison.json").write_text(json.dumps(comp, indent=2), encoding="utf-8")

    with (out_dir / "comparison.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "fight_id", "bots", "actual_winner",
                "generic_pick", "generic_p", "generic_correct",
                "main_pick", "main_p", "main_correct",
            ],
        )
        w.writeheader()
        for row in comp:
            w.writerow({**row, "bots": " vs ".join(row["bots"])})

    lines = [
        "| Fight | Actual winner | Generic (prebout) pick | Main (momentum) pick |",
        "|---|---|---|---|",
    ]
    for row in comp:
        generic = f"{row['generic_pick']} ({row['generic_p']:.2f}) {'✅' if row['generic_correct'] else '❌'}"
        if row["main_p"] is None:
            main = "not tracked yet"
        else:
            main = f"{row['main_pick']} ({row['main_p']:.2f}) {'✅' if row['main_correct'] else '❌'}"
        lines.append(f"| {row['fight_id']} ({' vs '.join(row['bots'])}) | {row['actual_winner']} | {generic} | {main} |")
    (out_dir / "comparison.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def run(out_dir: Path | None = None) -> dict[str, Any]:
    out_dir = out_dir or OUT_DIR
    fights = chronological_fights()

    exclude_pairs = {frozenset((m.bots[0].lower(), m.bots[1].lower())) for m in fights}
    roster = M.load_roster()
    history = M.load_history(exclude_pairs=exclude_pairs)
    engine = M.PreboutModel.seeded(roster, history)

    rows: list[dict[str, Any]] = []
    for meta in fights:
        a, b = meta.bots[0], meta.bots[1]
        p = engine.predict(a, b)
        outcome = 1 if meta.result.winner == a else 0
        mom_early, mom_final = _momentum_reference(meta.fight_id)
        rows.append(
            {
                "fight_id": meta.fight_id,
                "episode": meta.episode,
                "bots": [a, b],
                "winner": meta.result.winner,
                "prebout_p": round(p, 4),
                "outcome": outcome,
                "momentum_earliest_p": mom_early,
                "momentum_final_p": mom_final,
            }
        )
        engine.update(a, b, meta.result.winner)

    report: dict[str, Any] = {
        "n_fights_with_result": len(rows),
        "roster_coverage": len(roster),
        "history_coverage": len(history),
    }

    if not rows:
        report["status"] = "insufficient_data"
        report["note"] = (
            "No fight in data/processed/<fight_id>/meta.json has a recorded "
            "winner yet. This report will fill in as `bb ingest`/manifest "
            "results land - it is not an error, there is just nothing to "
            "score yet."
        )
    else:
        prebout_samples = [(r["prebout_p"], r["outcome"]) for r in rows]
        report["prebout"] = {
            "brier": round(_brier(prebout_samples), 4),
            "log_loss": round(_log_loss(prebout_samples), 4),
            "reliability": _reliability_bins(prebout_samples),
        }

        paired = [
            (r["momentum_earliest_p"], r["outcome"])
            for r in rows
            if r["momentum_earliest_p"] is not None
        ]
        if paired:
            paired_prebout = [
                (r["prebout_p"], r["outcome"]) for r in rows if r["momentum_earliest_p"] is not None
            ]
            report["paired_comparison"] = {
                "n_fights": len(paired),
                "note": (
                    "Both scores use the same information horizon: prebout's "
                    "only number, and momentum's earliest in-fight sample. "
                    "momentum's final-value Brier score is NOT included here "
                    "because by the end of the fight it has seen the whole "
                    "fight - that comparison would flatter momentum for free."
                ),
                "prebout_brier": round(_brier(paired_prebout), 4),
                "momentum_earliest_brier": round(_brier(paired), 4),
            }
        else:
            report["paired_comparison"] = {
                "n_fights": 0,
                "note": "No fight has both a recorded result and telemetry - nothing to pair yet.",
            }

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "predictions.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")
    (out_dir / "backtest_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    if rows:
        _write_comparison(rows, out_dir)
    if rows and "prebout" in report:
        _plot(prebout_samples, report["prebout"]["brier"], out_dir / "reliability_prebout.png")

    return report
