# Who builds what

Two people, two Claude Code sessions, one repo, working at the same time.

Repo: https://github.com/aslanu11/blackbox — public from the first commit; it
is the submission.

## Session kickoff prompts

**Pranav — paste this into your Claude Code session after cloning:**

> Read TEAM.md, DECISIONS.md, and BLACKBOX_claude_code_handover.md sections 5,
> 6 (Phase D), 9 and 11 if Aslan has shared it — otherwise TEAM.md has
> everything binding. You own Phase D only: ingest.py, shots.py, calibrate.py,
> track.py, overlay.py, and notebooks/sam2_track.ipynb. Do not edit
> schemas.py, fixtures.py, anything under sources/, the B-phase pipeline
> modules, or web/. In cli.py edit only the bodies of your own subcommands.
> Start with D4 (track.py) against the fixture-replay test, then D1/D2/D3 to
> feed it, then D5. Build shots.py behind --heuristic first; wire
> llm.classify_wide in when Aslan lands llm.py. Fixture-first: everything
> passes on fixture-001 before real footage. Run `bb doctor` first. Commit
> small with conventional messages, pull --rebase before every push, push
> straight to main. Never commit media or secrets.

**Aslan — paste this into your Claude Code session in the repo:**

> Read TEAM.md and DECISIONS.md. You own A5 (llm.py), Phase B (telemetry,
> events, momentum, scorecard, fuse), Phase C (net, sources/), Phase E (web/,
> export.py) and Phase F (Makefile targets, tests, README). Do not edit the
> Phase D pipeline modules (ingest/shots/calibrate/track/overlay) or the
> notebook — Pranav's session owns those. Build order: llm.py first (D2 is
> waiting on it), then B1 → B2 → B5 → E1 → E2 → B3 → B4 → E3 → C → F.
> Every module passes its acceptance test on fixture-001 before touching real
> data. Acceptance numbers live in
> data/processed/fixture-001/expected_events.json (regenerate with
> `bb fixture`). Commit small with conventional messages, pull --rebase before
> every push, push straight to main. Never commit media or secrets.

The split below is chosen for **zero file overlap**. Neither of you should ever
need to edit a file the other is editing. That is the whole design — it is more
important than an even workload.

---

## The split

### Pranav — the CV lane (Phase D)

You own everything that turns pixels into positions. This is the hard,
risky, GPU-less part and it is the **Gate 1 blocker**, so it outranks
everything else in the repo.

| Phase | File | What |
|---|---|---|
| D1 | `blackbox/pipeline/ingest.py` | ffmpeg: cut the fight clip, extract frames at 10 fps |
| D2 | `blackbox/pipeline/shots.py` | PySceneDetect + wide-shot classification |
| D3 | `blackbox/pipeline/calibrate.py` | Homography click-tool |
| D4 | `blackbox/pipeline/track.py` | **CSRT tracking — the guaranteed path** |
| D5 | `blackbox/pipeline/overlay.py` | Burn trails / hit flashes / momentum needle into mp4 |
| D6 | `notebooks/sam2_track.ipynb` | Colab SAM2 upgrade path, same `tracks.json` contract |

**Build order: D4 first, then D1/D2/D3 to feed it, then D5, then D6.**
D4 is what Gate 1 is measured on. Everything else in your lane exists to
get frames into D4 or to make D4's output watchable.

**You are not blocked on Aslan.** Two notes:
- D2's primary path calls `llm.classify_wide()`, which Aslan owns (A5).
  Build D2 behind `--heuristic` first (border-region frame-diff variance).
  When A5 lands, wire the LLM path in. Do not wait.
- You do not need `bb fetch` (C2, Aslan's) to get footage. Run `yt-dlp` by
  hand into `data/raw/` and keep moving.

### Aslan — math, data, demo (Phases A5, B, C, E, F)

| Phase | File | What |
|---|---|---|
| A5 | `blackbox/llm.py` | Cached Anthropic client — **land this early, D2 wants it** |
| B1 | `blackbox/pipeline/telemetry.py` | Smoothing, speed, control, mobility, heatmaps |
| B2 | `blackbox/pipeline/events.py` | Hit / KO / hazard detection |
| B3 | `blackbox/pipeline/momentum.py` | Win-probability curve + calibration |
| B4 | `blackbox/pipeline/scorecard.py` | Rubric model + Robbery Leaderboard |
| B5 | `blackbox/pipeline/fuse.py` | Attention alignment + media value |
| C1 | `blackbox/net.py` | Bright Data / plain fetch + `fetch_log.jsonl` |
| C2 | `blackbox/sources/yt.py` | yt-dlp download + most-replayed heatmap parsing |
| C3 | `blackbox/sources/wiki.py` | Fandom fight tables + episode cards |
| C4 | `blackbox/sources/specs.py` | battlebots.com roster → `data/bots.csv` |
| E1–E3 | `web/**` | Vite + React frontend; **E2 TimelineLanes is the signature** |
| E4 | `blackbox/export.py` | Processed artifacts → `web/public/data/` |
| F1–F3 | `Makefile`, `tests/`, `README.md` | Ops + the submission write-up |

**Build order: B1 → B2 → B5 → E1 → E2 → B3 → B4 → E3 → C → F.**
Rationale: get the three lanes on screen from fixture data as early as
possible. That is the demo. Scraping (C) is real but it is not what a judge
looks at, and B3/B4 are the interesting-but-optional depth.

---

## Files neither of you edits casually

| File | Rule |
|---|---|
| `blackbox/schemas.py` | **Frozen.** A change here is a data-contract change and needs Aslan's sign-off (spec §9.6). If your module can't pass its acceptance, fix your module — don't widen the schema. |
| `blackbox/fixtures.py` | **Frozen.** Downstream acceptance numbers are calibrated against it. Changing it silently moves everyone's goalposts. |
| `blackbox/cli.py` | Shared. Edit **only the body of your own subcommand**. Don't reformat, don't reorder, don't touch `OWNERS`. |
| `data/manifest.yaml` | Aslan owns it. Pranav: ask, don't edit. |
| `DECISIONS.md` | Append-only. Both write. Never edit someone else's entry. |

---

## Git protocol

The repo is **public from the first commit** — it is the submission. So:

- **No secrets, ever.** Keys go in `.env`, which is gitignored.
- **No media, ever.** No video, no frames, no audio. `data/raw/`,
  `data/frames/` and every video extension are gitignored. Derived JSON and
  small PNG charts are fine — those are our work product, not someone's
  broadcast.
- Conventional commits (`feat:`, `fix:`, `chore:`), small and frequent. The
  commit history is evidence of what existed when, which matters if the 17:00
  rules say anything about build timing (spec §8).

Because your file sets don't overlap, **push straight to `main`**:

```bash
git pull --rebase && git push
```

Pull-rebase before every push. Use a branch + PR only when you must touch a
shared file from the table above.

If you do collide, the loser of the race rebases. Don't merge-commit; it
makes the history harder to read as evidence.

---

## The two gates

| Clock | Gate | Who is on the hook |
|---|---|---|
| **15:30** | Tracking proof-of-life on real footage, or we pivot | **Pranav** (D1–D4) |
| ~16:15 | `make demo-fixture` green before anyone leaves for the venue | **Aslan** (F1) |
| **19:00** | Hero overlay + real metrics on screen | Both — B/E must consume real JSON with zero code changes |

The pivot at 15:30, if tracking isn't working, is to **Audience Alpha**:
attention analytics with no CV lane. All of C, B5, E and F carry over
untouched. That is why the frontend is built against fixtures and why
attention lives in its own contract — the fallback is not a rewrite.

---

## Fixture-first, always

Every module must run and pass its acceptance check on `fixture-001` before
it ever sees real data. `bb fixture` regenerates it deterministically and
needs no network.

The fixture has known ground truth in
`data/processed/fixture-001/expected_events.json`: 5 hits at known times and
magnitudes, a mobility decay at t=100, a KO at t=141.5, and three coverage
gaps totalling 20% of frames. Your acceptance test asserts against that file.

Real footage arrives mid-afternoon and slots into code that already works.
