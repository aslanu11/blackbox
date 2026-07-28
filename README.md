# BLACKBOX

**The flight recorder for robot combat.**

> `#battlebotsdev` · built at BattleBots Hack Night, London · 28 July 2026
>
> **⚠ PROTOTYPE** — built in one day, by two people and their agents. The
> pipeline is real and every number shown is genuinely measured, but the
> metrics are experimental, coverage is partial, and calibration is early.
> Nothing here is a betting product or an official statistic.

BattleBots produces almost no telemetry. There are no position feeds, no speed
traces, no impact sensors — just broadcast footage and a judges' verdict. So we
manufacture the telemetry: computer vision over fight footage gives us
positions, speed, control and impact events, and we fuse that with YouTube's
public "most replayed" data to work out which moments and which robots actually
drive an audience.

---

## What's on screen

1. **Hero fight video** with a telemetry overlay burned in — position trails,
   hit flashes, mobility bars, a momentum needle.
2. **Three synced timeline lanes** under the video, sharing one time axis:
   - `CH1 MOMENTUM` — live win probability
   - `CH2 EVENTS` — hits sized by magnitude, hazards, KO
   - `CH3 ATTENTION` — YouTube most-replayed
3. **Objective judging scorecard** — "VAR for BattleBots". Our rubric model vs
   the official verdict, with an agreement rate and a **Robbery Leaderboard** of
   historical fights we think were scored wrong.
4. **Media Value table** — screen time × attention per robot, plus a
   Wins-vs-Watches scatter showing which robots are worth more than their record.
5. **Sponsor Index** — a 0–100 sponsorship attractiveness score per robot
   (see below).

---

## The computer vision lane

This telemetry does not exist anywhere else — we manufacture it from the
broadcast:

- **Ingest**: each fight clip is cut from the episode by its chapter offsets
  and decomposed to frames at 10 fps.
- **Shot understanding**: PySceneDetect finds every camera cut (a cut every
  ~2.5 s in this production); a vision LLM classifies each shot wide/not-wide,
  disk-cached so re-runs are free.
- **Multi-angle handling** — the hard part. Broadcasts cut between 12–16
  distinct cameras per fight, and a floor homography is only valid for one of
  them. We cluster wide shots by a background signature (averaged over frames
  so the moving robots wash out), rank camera clusters by geometric
  suitability (the arena's yellow wall padding sits high in frame on elevated
  cameras), and calibrate the top cameras individually — four clicks on the
  arena corners each. The tracker picks the right homography per shot,
  restarts at every cut, and **refuses to produce positions for uncalibrated
  angles** — those stretches render as hatched gaps. Wrong-but-plausible
  coordinates are the one failure mode a VAR product cannot survive.
- **Tracking**: CSRT trackers per robot per shot, colour-histogram drift
  checks and re-acquisition after cuts, pixel centroids projected to floor
  metres. Our hero fight tracks at ~50% of fight time, honestly reported.
- **Derived physics**: Savitzky–Golay smoothing (never across a gap), speed,
  a control signal (centre occupancy + wall pressure), mobility decay, and
  impact detection from joint velocity spikes under a 2.5 m separation gate.

## The heatmaps

Each robot's **control heat** map is its measured floor presence over the
fight — a Gaussian-smoothed 2D histogram of tracked positions on a √ scale,
so the full trajectory reads while pinned-in-place time stays hottest. Click
to enlarge in the app. How to read one: centre presence is cage control; a
bright smear on a wall is a robot being controlled or dying there. In our ep4
hero fight you can watch Bloodsport's heat pool against the right wall —
that's Minotaur's control, measured, and it matches the official result.

## Backtesting

Two models, both backtested against reality:

- **Momentum (in-fight)**: `bb momentum --calibrate` replays every processed
  fight, buckets predicted win probability against actual outcomes, and
  reports a reliability curve + Brier score. Momentum's evidence channels are
  deliberately bounded (tanh-squashed hit differential, logit clamped to
  5–95% outside a KO) — an early version reached 99.99% certainty mid-fight
  on saturated inputs, which the backtest exposed and the clamp fixed.
- **Pre-bout (Elo)**: an Elo/roster model fit on the scraped 373-fight
  history corpus, backtested on held-out fights — the baseline any in-fight
  model has to beat, and the prior the momentum curve starts from.
- **Judging**: our 11-point rubric scorecard is validated against every
  official verdict we scraped; disagreement margin on judges'-decision fights
  is exactly the Robbery Leaderboard.

## Sponsorship scoring

The **Sponsor Index** prices a robot's marketing value from measured
attention, not vibes. Per robot, 0–100:

```
sponsor_score = 45% spotlight + 30% authorship + 25% performance
```

- **Spotlight** — seconds the robot was on screen while episode attention sat
  above the critical threshold (the audience was actually rewatching, not
  just present).
- **Authorship** — the share of detected hits the robot *caused*. Taking
  damage photogenically is worth something; dealing it is worth more.
- **Performance** — competitive results from the scraped record.

Each score carries a **confidence** (fights without published attention data
are faded in the UI, not hidden). The point of the index: sponsorship value
and win-rate diverge — a fan-favourite that loses violently can out-earn a
boring winner, and now there's a number for that argument.

---

## Reading the instruments

The app ships its own manual: the **HOW TO READ** link in the masthead (or
`/#guide`) explains every instrument — what it measures, how it's computed,
and where it can be wrong. The short version:

| Instrument | What it means |
|---|---|
| `CH1 MOMENTUM` | Live win probability from control + hit differential + mobility, each signal bounded; clamped to 5–95% outside a KO — the model never claims mid-fight certainty |
| `CH2 EVENTS` | Detected impacts: hit markers sized by combined velocity change, hazards, KO. Actor = whoever was closing faster (an estimate, not a verdict) |
| `CH3 ATTENTION` | YouTube's real "most replayed" curve in fight-local time; empty until YouTube publishes one — we never fake it |
| Control heat | Where each robot spent the fight (click to enlarge). Centre = control; a bright corner smear = pinned or dead |
| Scorecard | The 11-point rubric (Damage 5 / Aggression 3 / Control 3) computed from telemetry — an independent second opinion vs the judges |
| Robbery score | Our margin of disagreement with an official judges' decision; 0 = we agree |
| Media value | `screen_s × attn_index` — on-screen time weighted by how hard the audience rewatches it. Losing robots can out-earn winners; that's the rate-card argument |

Full formulas and caveats live in the in-app guide and [DECISIONS.md](DECISIONS.md).

---

## Honesty as a design constraint

The CV lane cannot see through a close-up. When the broadcast cuts away from the
wide shot, we have no positions — so the timeline lanes render those stretches
as **hatched voids**, and every fight reports a **coverage percentage**. We
never interpolate across a camera cut. A number we didn't measure doesn't get
drawn.

---

## Run it

Nothing below needs footage, network access, or an API key — the whole pipeline
runs on a deterministic synthetic fight.

```bash
python -m venv .venv && .venv/bin/pip install -e ".[dev]"
```

```bash
bb doctor
```

```bash
make demo-fixture
```

Then `cd web && npm run dev`.

On Windows, use `.venv\Scripts\` instead of `.venv/bin/`. If you don't have
`make`, the targets are thin wrappers — read the `Makefile`, they're one line each.

### Real fights

`data/manifest.yaml` carries the fight registry (YouTube ids + fight offsets,
sourced from the episodes' own chapter markers). Downloading footage and
clicking calibration points are human steps. See [TEAM.md](TEAM.md).

```bash
bb sync
```

```bash
bb fetch --fight-id pl-e01-f2
```

```bash
bb run --fight-id pl-e01-f2
```

---

## Build order

The pipeline is a chain of small CLI steps. Each writes a JSON artifact into
`data/processed/<fight_id>/`; each reads only artifacts, never another module's
internals. The contracts live in [`blackbox/schemas.py`](blackbox/schemas.py) and
are the single source of truth.

```
ingest → shots → calibrate → track → telemetry → events → momentum → fuse → overlay → export
  D1      D2        D3        D4        B1         B2        B3       B5      D5        E4
```

Who owns which phase: [TEAM.md](TEAM.md). Judgment calls: [DECISIONS.md](DECISIONS.md).

---

## What we don't commit

The repo has been public since the first commit. No secrets — everything goes
through `.env` (see `.env.example`). No media — no video, no extracted frames,
no audio; we don't redistribute broadcast footage. Derived JSON and small PNG
charts are committed, because those are our work product.

---

## Team

- **Aslan Usenmez** — math core, data acquisition, frontend
- **Pranav** — computer vision, tracking, overlay

MIT licensed.
