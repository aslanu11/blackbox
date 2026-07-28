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

---

## Handover — Pranav's session → Aslan (2026-07-28, ~18:00)

Pranav's Claude Code session is stepping back here; this section is
everything it did and found, so a fresh session (or Aslan) can pick up
without re-deriving it.

### Phase D status: done, tested, on `main`

D1–D6 are all implemented and merged (rebased cleanly onto Aslan's
A5/B1–B5/C1–C4/E1–E4/F1 push earlier today). 74/74 tests pass, including a
fixture-replay test for D4 that renders synthetic tracked blobs and confirms
CSRT + histogram re-acquisition recovers floor positions to well under the
0.5 m bar. `bb overlay --fight-id fixture-001` produces a real 90 s / 720p
mp4 end to end, with a schematic-floor fallback so it works even with no
real footage yet.

Two environment landmines hit and fixed along the way (both logged in
DECISIONS.md with full remediation steps — read those before reinstalling):
1. A stray `.venv` built on Python 3.10 instead of the required ≥3.11 —
   looked like a hung network install, was actually pip's resolver retrying
   forever.
2. OpenCV 5.x dropped `cv2.TrackerCSRT` entirely. Fixed via
   `opencv-contrib-python<5`, plus a follow-up fix: `scenedetect`'s own
   `install_requires` pulls in plain `opencv-python` unconditionally, which
   silently clobbers `opencv-contrib-python`'s files on any fresh
   `pip install -e ".[dev]"`. **If `bb track` ever complains "no
   cv2.TrackerCSRT constructor found" again**, don't uninstall just
   `opencv-python` (it deletes contrib's files too) — uninstall both and
   reinstall fresh. Full detail in DECISIONS.md.

**Still blocked on:** `data/manifest.yaml` still has 6 `TODO` fields
(yt_id / fight offsets) and `data/raw/` is empty — real footage was never
supplied today, so D1–D4 have only run against the synthetic fixture, never
real video. That's the actual Gate 1 gap, not a code gap.

### Bright Data — what's on the account, and where it fits

Pranav's session tested the account's Bright Data access at the user's
request (see chat, not reproduced here). **The API key was pasted into a
chat session — it must never go in this file, in any committed file, or
anywhere in the repo (public from commit one).** It belongs in `.env` only
(gitignored, see `.env.example`) — whoever wires this in should get a fresh
key from the Bright Data dashboard and rotate the old one out. Endpoint
shape only, key omitted:

```python
# trigger:
POST https://api.brightdata.com/dca/trigger
  ?collector=c_ms4yfrun1dayux9o7y&queue_next=1
  headers: Authorization: Bearer <token from .env>
  body: [{"url": "https://battlebots.com/robots/"}]
# -> {"collection_id": "...", "start_eta": "..."}

# poll/fetch:
GET https://api.brightdata.com/dca/dataset?id=<collection_id>
  -> 202 {"status":"collecting", ...} while running
  -> 200 [ {...one object per robot...} ]  when done (took ~4 min this run)
```

**Account has one other provisioned zone:** `scraping_browser1`
(`type: browser_api`) — Bright Data's Scraping Browser, a remote headless
browser with unlocking/proxy rotation/CAPTCHA handling built in, reachable
over a CDP/Playwright-style endpoint. Separate product from the collector
above; general-purpose, not battlebots-specific.

**Live-site note:** hitting `battlebots.com/robots/` directly in a plain
browser returned "Database Error" (WordPress DB failure) twice in a row
during this session. The Bright Data collector still returned clean data on
the same URL — real evidence for routing C-phase fetches through it rather
than plain `httpx`, which is exactly what `net.py`'s job description already
says (`Bright Data / plain fetch + fetch_log.jsonl`).

**Collector output** — one object per robot, 7 robots returned for the
current roster page:

```json
{
  "robot_name": "Malice",
  "robot_type": "Horizontal Drum Spinner",
  "team_name": "Team Malice",
  "builder_name": "Adrian \"Bunny\" Liaw",
  "hometown": "San Jose, California",
  "image_urls": ["https://battlebots.com/wp-content/uploads/2022/11/BB2022-Malice-team.jpg", "...bot.jpg", "...captain.jpg", "...(8 more, mostly unrelated roster thumbnails on the page)"],
  "career_stats": {"total_matches": 21, "win_percentage": "52%", "total_wins": 11, "losses": 10},
  "match_history": [],
  "website_urls": ["https://teammalice.com/", "https://www.facebook.com/malicebattlebot", "..."],
  "product_page_url": "https://battlebots.com/robot/malice-wcvii/"
}
```

Other robots seen: Double Tap, Captain Shrederator, Cobalt, Tantrum,
Slammo!, SawBlaze — same shape, `career_stats` varies (2–35 matches,
20–100% win rate). `match_history` was empty for all 7 on the roster index
page; it may only populate on each robot's own `product_page_url` — worth
a follow-up collector run per-bot if that field matters.

**Where each field fits:**

| Field | Feeds | Note |
|---|---|---|
| `robot_name`, `robot_type` | C4 `sources/specs.py` → `data/bots.csv` | `robot_type` is free text ("Bar spinner (horizontal)", "Hammer Saw", "Puncher", "Grappler") — needs a small mapping into `schemas.WEAPON_CLASSES`. Most map cleanly; "Puncher" has no obvious bucket, falls to `"other"`. |
| `career_stats` (wins/losses/win%) | B4 `scorecard.py` → `BotMediaValue.record` / `perf_score` | Both fields already exist in `schemas.py` with no real source wired in yet — this is one, zero manual entry needed. |
| `image_urls` (first 2–3 per bot) | E-phase frontend | Real bot/team photos instead of placeholders. |
| `product_page_url` | Deeper C4 crawl | Likely has full spec sheet + populated `match_history` per bot — could automate what `data/manifest.yaml`'s corpus section currently marks `# Human fills`. |
| Scraping Browser zone | C1 `net.py`, C3 `sources/wiki.py`, C2 `sources/yt.py` | For JS-heavy / anti-bot pages — Fandom fight tables and YouTube's most-replayed heatmap JSON are exactly this kind of target. |

None of `net.py`, `sources/specs.py`, `sources/wiki.py`, `sources/yt.py`
were touched by Pranav's session (out of scope per the split above) — this
is research only, handed off for whoever picks up C1/C4 next.
