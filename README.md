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

Filling `data/manifest.yaml` with YouTube ids and fight offsets, downloading
footage, and clicking the calibration points are human steps. See
[TEAM.md](TEAM.md).

```bash
bb run --fight-id pl-e04-f2
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
