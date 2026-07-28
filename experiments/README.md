# experiments/

Side experiments that are **not** part of the Phase D/B/C/E/F split in
[`TEAM.md`](../TEAM.md) — nothing under here touches `blackbox/schemas.py`,
`blackbox/fixtures.py`, `blackbox/sources/`, the B-phase pipeline modules, or
`blackbox/cli.py`. That split has zero file overlap by design; this directory
exists so an experiment can be tried without putting a foot in it.

## prebout/ — a second, independent win-probability model

`blackbox/pipeline/momentum.py` (B3) predicts P(bots[0] wins) **during** a
fight from CV telemetry — control, hit differential, mobility. It's the
"CH1 MOMENTUM" lane on screen, and it can only run on hero fights with real
tracking.

`experiments/prebout/` predicts the same quantity **before** the fight, from
roster data (weapon class) and prior results (a shrinkage-seeded Elo rating,
updated walk-forward). It needs no tracking data, so it scores every fight in
the manifest that has a recorded winner — corpus and proleague fights
included, not just hero fights. That makes it a useful backtest baseline to
compare momentum.py against, not a replacement for it: two different
questions ("what do we expect going in" vs "what does the footage say right
now") answered two different ways.

**It only reads artifacts, never another module's internals** — the same
contract the rest of the pipeline follows (spec §5):

| Reads | Written by | Owner | If missing |
|---|---|---|---|
| `data/bots.csv` | `blackbox/sources/specs.py` (`roster()`) | Aslan, C4 | weapon class defaults to `"other"` for every bot |
| `data/wiki/*_history.csv` | `blackbox/sources/wiki.py` (`bot_history()`) | Aslan, C3 | no Elo seed; every bot starts at 1500 |
| `data/processed/<fight_id>/meta.json` | the Phase D/B pipeline | both | fight is skipped, not scored |
| `data/processed/<fight_id>/telemetry.json` | `blackbox/pipeline/momentum.py` | Aslan, B3 | paired comparison against momentum is skipped for that fight |

Nothing here ever writes into `data/processed/<fight_id>/`. Its own outputs
go to `data/processed/experiments/prebout/` — a separate namespace so it can
never collide with a `schemas._ARTIFACTS` file.

### Running it

Needs no network access if `data/bots.csv` and `data/wiki/` already exist —
`backtest` just reads whatever's on disk and reports honestly on what isn't
there yet (`roster_coverage`, `history_coverage`, `n_fights_with_result` in
the output all say so explicitly, rather than silently scoring on defaults
and calling it real).

```
python -m experiments.prebout.cli backtest
```

To pull real data first (optional — goes through `blackbox/net.py`, so it
picks up `BRIGHTDATA_API_TOKEN`/`BRIGHTDATA_UNLOCKER_ZONE` from your local
`.env` automatically if set, same as the rest of the repo, and degrades to
plain `httpx` if not):

```
python -m experiments.prebout.cli fetch-roster
python -m experiments.prebout.cli fetch-history
```

`fetch-roster`/`fetch-history` call `specs.roster()` / `wiki.bot_history()`
directly — the exact functions `bb` will call once C3/C4 are wired into the
main CLI, just triggered by hand in the meantime.

### Reading the backtest report

`data/processed/experiments/prebout/backtest_report.json`:

- `prebout.brier` / `prebout.log_loss` / `prebout.reliability` — the model
  scored against every fight with a known winner.
- `paired_comparison` — the *same* fights, scored against momentum.py's
  **earliest** in-fight sample (closest to t=0), not its final value. Using
  the final value would compare a genuine pre-fight forecast against a model
  that has already watched the whole fight — that flatters momentum for free
  and isn't a fair fight. If `paired_comparison.n_fights` is 0, no fight yet
  has both a recorded result *and* processed telemetry; that's expected
  early in the day, not a bug.

### Design choices, briefly

- **Elo, not a trained classifier.** With maybe a dozen real results by the
  end of the day, a logistic regression or anything with more than a couple
  of free parameters would just memorise the corpus. Elo degrades gracefully
  to "no information" (0.5) for an unseen bot instead of extrapolating from
  nothing.
- **Shrinkage everywhere data is thin**: the wiki win-rate seed and the
  weapon-class matchup table both scale their influence by sample count, so
  one lucky/unlucky early result can't swing a prediction to near-certainty.
- **Walk-forward only.** `predict()` is called strictly before `update()` for
  every fight in the backtest — a model is never scored against a result it
  already knows.

### Tests

`experiments/prebout/tests/` — not under the top-level `tests/` package
(TEAM.md's F1–F3 lane), and not in `pyproject.toml`'s `testpaths`, so a plain
`pytest` run from the repo root won't pick them up. Run them explicitly:

```
python -m pytest experiments/prebout/tests -q
```
