# BLACKBOX

**The flight recorder for robot combat.**

> `#battlebotsdev` · built at BattleBots Hack Night, London · 28 July 2026

<!-- TODO(F3): hero gif — 6s loop of the overlay video with the three lanes scrubbing underneath -->

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

<!-- TODO(F3): why the data is novel — one paragraph, lead with "this telemetry does not exist anywhere else" -->

<!-- TODO(F3): how Bright Data is used — point at data/fetch_log.jsonl as receipts, one line per request showing which path served it -->

<!-- TODO(F3): backtest methodology + honest caveats — reliability curve, Brier score, and where the model is weak -->

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
