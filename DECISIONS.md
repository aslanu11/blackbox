# Decisions

Append-only. One entry per judgment call that isn't obvious from the code.
Never edit someone else's entry — add a new one that supersedes it.

Format: `## <date> — <decision>` then **What**, **Why**, and **Revisit if**.

---

## 2026-07-28 — Windows is a first-class dev environment

**What:** The spec assumes macOS/Linux. Aslan's machine is Windows 11. The repo
stays OS-agnostic: `pathlib` everywhere, no shell-outs except `ffmpeg` and
`yt-dlp`, and `bb doctor` prints a per-OS install hint.

**Why:** Rewriting the toolchain assumption costs more than staying portable.

**Revisit if:** the OpenCV click-tools (D3/D4) misbehave under Windows — the
`cv2.imshow` window and mouse callbacks are the likeliest place this bites. If
so, that work moves to Pranav's machine, which is where it lives anyway.

---

## 2026-07-28 — `ffmpeg` is not installed on Aslan's machine

**What:** `bb doctor` reports it missing. This blocks D1 (ingest) and D5
(overlay) locally, and nothing else.

**Why it doesn't matter yet:** both are Pranav's, and everything else in the
repo runs on synthetic fixtures with no ffmpeg dependency.

**Action:** `winget install Gyan.FFmpeg`, then restart the shell.

---

## 2026-07-28 — `expected_events.json` is not a §5 contract artifact

**What:** The fixture writes ground truth alongside the contract files, but it
is deliberately not a pydantic model and not in `schemas._ARTIFACTS`.

**Why:** It exists only so tests can assert against known truth. Promoting it to
a contract would imply real fights have ground truth, which is exactly the thing
this project doesn't have and is manufacturing.

---

## 2026-07-28 — Fixture separation is exact by construction

**What:** In `fixtures.py`, bot A's position is derived from bot B's
(`pos_a = pos_b + d*u`) rather than both being placed around a shared midpoint.
Out-of-bounds pairs are translated as a unit, never clipped independently.

**Why:** The first version placed both bots symmetrically about a midpoint. Once
bot B's mobility decay pins it in place, the midpoint model breaks down and the
true separation stops matching the modelled `d(t)` — the 5th scripted hit ended
up 2.7 m apart and read as bots moving *together*, which would have made it
undetectable by B2's `separation < 2.5 m` gate. Independent clipping had the
same class of bug. Deriving A from B makes separation exact at every frame.

**Revisit if:** the fixture ever needs three or more bots.

---

## 2026-07-28 — Attention baseline is the 20th percentile, not the median

**What:** `Attention.stats.baseline` is `percentile(vals, 20)`.

**Why:** The median of a bump-heavy curve is inflated by the bumps themselves.
With a median baseline, `event_lift` on a real hit came out at ~1.1 — below the
1.5 that B5's acceptance requires — not because the bump was small but because
the denominator was wrong. The 20th percentile tracks the quiet stretches, which
is what "baseline attention" is supposed to mean.

**Revisit if:** a real fight is more than ~60% high-attention, where even the
20th percentile stops being quiet.

---

## 2026-07-28 — Hit magnitude is a peak rate, not an averaged one

**What:** Hit magnitude is recovered as the *peak instantaneous* separation rate
in the ~0.3 s after contact, not an average over a longer window.

**Why:** The rebound completes in well under half a second for a hard hit, so a
0.5 s average saturates at `(separation_before - 1 m) / 0.5` — which is the same
number regardless of how hard the hit was. Averaged, a 9.6-magnitude hit and a
4.5-magnitude hit are indistinguishable. The peak preserves the ordering.

**Consequence for B2:** smooth positions (Savitzky–Golay) *before*
differentiating. Raw 10 fps positions carry ~3 cm of tracker noise; twice
differentiated, that noise completely buries every hit in the fixture.

---

## 2026-07-28 — B2's acceptance tolerates one marginal hit

**What:** The fixture's weakest scripted hit (magnitude 4.5) spikes ~3.7× over
baseline where the others clear 4×. The test asserts every hit leaves *some*
trace (>3×) and that at least 4 of 5 spike clearly (>4×).

**Why:** This mirrors the spec's own B2 criterion ("≥4 of 5 hits recovered").
Real fights have glancing blows. A fixture where every hit is trivially
detectable would not be evidence that the detector works.

---

## 2026-07-28 — Mobility index: rolling p90 over self-baseline, not rolling-30s max

**What:** `telemetry.mobility_series` uses a rolling 10 s 90th-percentile of
speed, divided by the median of that same statistic over the bot's first 60 s.
Windows less than half-full of real frames emit NaN. The spec sketched
"rolling-30s max ÷ first-60s baseline".

**Why:** Measured on the fixture, the rolling-30s max detects bot B's scripted
decay 40 s late — a knockdown rebound (the t=108 hit throws B at ~2.2 m/s)
parks a stale maximum in the window for its full 30 s length. It also reads
garbage right after camera-cut gaps, when the window holds two frames.
Numerator and denominator now use the *same* statistic, so hit rebounds and
quiet wander phases inflate or deflate both equally. With sustained-crossing +
backdating, decay onset lands at 101.9 vs scripted 100 (spec asks ±5 s), with
no false onset on the healthy bot. Contract unchanged — telemetry.json shape
is identical; this is internal math.

**Revisit if:** real footage shows mobility flapping — then raise
MOBILITY_WINDOW_S before touching the percentile.

---

## 2026-07-28 — Hit time = closest approach, not the biggest |dv| frame

**What:** `events.detect_hits` places each hit at the minimum-separation frame
within the spike burst, not at the burst's |dv| argmax.

**Why:** The rebound tail decelerates hard and can out-spike the impact
itself; on the fixture that put two hits 2.2 s late, which also dragged their
attention `event_lift` below threshold (the bump is centred on the true
contact). Closest approach is the physical definition of contact and recovers
all five scripted hits within ±0.5 s.

---

## 2026-07-28 — `.venv` must be built on Python >= 3.11

**What:** Pranav's machine had a stray `.venv` built against the system Python
3.10 (Windows has 3.10/3.12/3.13 all installed). `pyproject.toml` requires
`>=3.11`, so `pip install -e ".[dev]"` against that venv doesn't just fail —
pip's resolver burns 20+ minutes and hundreds of MB re-downloading every
scipy/opencv build back to 1.11 looking for a python-3.10-compatible set that
satisfies `opencv-python>=4.9` (which itself now requires >=3.11). Recreated
`.venv` with `py -3.13`; installed clean in under a minute.

**Why it matters for both of you:** if `pip install -e ".[dev]"` looks like
it's hanging rather than downloading in a straight line, check
`.venv/Scripts/python.exe --version` (or `.venv/bin/python3 --version`)
before waiting it out — a python-version mismatch looks exactly like a slow
network at first glance.

**Revisit if:** we ever need to support a machine without Python 3.11+.

---

## 2026-07-28 — `opencv-python` -> `opencv-contrib-python<5`, pinned below 5.x

**What:** `pyproject.toml` pinned `opencv-python>=4.9` with no upper bound. It
resolved to `opencv-python==5.0.0.93`, and OpenCV 5 dropped `cv2.TrackerCSRT`
from the base package entirely (confirmed: no `cv2.TrackerCSRT_create`, no
`cv2.legacy` namespace at all in 5.0.0). D4 (`track.py`) is written around
CSRT — it's named "the guaranteed path" in this repo for a reason: it's the
one classical tracker robust enough for two bots that collide and rebound.
Switched the dependency to `opencv-contrib-python>=4.9,<5`, which still ships
the legacy tracking module. Capped below 5.0 rather than trusting a very new
`opencv-contrib-python` 5.x release to have carried CSRT forward — that's
unverified and this dependency is load-bearing for Gate 1.

**Why this belongs to both of you:** `opencv-python` and `opencv-contrib-python`
conflict if both installed (`pip install -e ".[dev]"` again after pulling this
picks up the fix cleanly, but if you already have a `.venv` with plain
`opencv-python` in it, `pip uninstall opencv-python` first or just rebuild the
venv).

**Revisit if:** a future `opencv-contrib-python` release restores `TrackerCSRT`
in the 5.x line and there's a reason to want it (smaller wheel, etc).

---

## 2026-07-28 — dropped the `[opencv]` extra from the `scenedetect` dependency

**What:** `scenedetect[opencv]` declares its own dependency on plain
`opencv-python`, which reinstalls it alongside `opencv-contrib-python` —
both packages ship a `cv2/` directory under the same import name, so
whichever installs last wins the file conflict. A routine
`pip install -e ".[dev]"` after this repo already had `opencv-contrib-python`
silently clobbered it back to plain `opencv-python` 5.x (no `TrackerCSRT`,
see the entry above) with no warning. Dropped to plain `scenedetect>=0.6.4`.

**It is not actually fixed, just less likely:** `scenedetect` 0.7.1's own
`install_requires` pulls in plain `opencv-python` regardless of the `[opencv]`
extra (`pip show scenedetect` lists it under `Requires` unconditionally).
So both packages always end up installed side by side either way; the extra
only controlled a second, redundant declaration. Which one's files "win" on
disk depends on pip's install order, which isn't a documented guarantee —
it has come out in `opencv-contrib-python`'s favour twice in a row here
(alphabetically after `opencv-python`, if that's why), but that's an
observation, not a contract.

**If `bb doctor`'s opencv line looks right but `bb track` complains "no
cv2.TrackerCSRT constructor found":** don't `pip uninstall opencv-python`
alone — its RECORD file lists paths that `opencv-contrib-python` has since
overwritten, so uninstalling it deletes contrib's files too and breaks `cv2`
entirely. Instead: `pip uninstall -y opencv-python opencv-contrib-python`
(both), then `pip install -e ".[dev]"` fresh.

**Revisit if:** this bites a third time — worth vendoring a `pip check`-style
guard into `bb doctor` at that point (checks `hasattr(cv2, 'TrackerCSRT_create')`
explicitly) rather than trusting install order.

---

## 2026-07-28 — Overlay ships to the web as H.264, transcoded at export

**What:** `export.py` transcodes `overlay.mp4` with ffmpeg
(`libx264 -crf 23 -movflags +faststart`) when copying into `web/public/data/`,
cached by mtime. Without ffmpeg it copies raw and prints a loud warning.

**Why:** D5 writes through OpenCV's `VideoWriter`, whose `mp4v` fourcc is
MPEG-4 part 2 — no current browser decodes it, so the page showed a dead
player with no error (readyState 0). Transcoding at the export seam keeps
overlay.py free to use whatever writer is convenient, and shrank the fixture
overlay 76 MB → 33 MB as a bonus. Verified in-browser: readyState 4, seek
works.

**Revisit if:** export ever becomes the demo bottleneck — then write H.264
directly in D5 instead and drop the transcode.

---

## TEMPLATE — copy this

## YYYY-MM-DD — <one-line decision>

**What:**

**Why:**

**Revisit if:**

---

## 2026-07-28 — Fight windows come from the broadcast, not the chapter markers

**What:** pl-e01-f2's chapter runs 630-837s but the fight ends at clip t=74 —
the broadcast's own "KNOCKOUT: 74sec" graphic and the arena clock (01:46
remaining at t=74) both say so. 77s-170s of the chapter is interviews and
celebrations. Window corrected to 630-712 (+8s buffer for the KO attention
bump); `method: ko, time_s: 74` now in the manifest.

**Why it looked like a CV crisis:** with interviews included, wide coverage
read 29% and a "93-second dead zone" — the cameras weren't hostile, the fight
was just over. Within actual combat, wide coverage is ~76%.

**Revisit if:** other chapters bundle build-up before the opening bell too —
check the arena clock in the first seconds of each clip.

---

## 2026-07-28 — Multi-angle tracking: per-angle homographies, honesty first

**What:** Broadcast fights cut between many cameras (ep1: 12 clusters, ep4:
16). A homography is valid for exactly one camera, so `angles.py` (D4.5)
clusters wide shots by a background signature (48x27 blurred gray thumbnails,
AVERAGED over ~5 frames per shot so the moving robots wash out — a single
frame's signature is robot-dominated and useless). Clusters are ranked
elevation-first (the arena's yellow wall padding sits high in frame on an
elevated camera; centroid < 0.48 of frame height), screen time second, because
a floor-level cam can out-time the elevated wide while its grazing-angle
homography is garbage. Top N (default 3) survive; each gets its own
`bb calibrate --angle N` -> `calibration_a<N>.json`; `track.py` picks the
right H per shot, splits tracker runs at every camera cut, and leaves any
uncalibrated angle as an explicit gap. Legacy single-camera path (the
fixture) is untouched: no angles.json means calibration.json applies
everywhere.

**The rule that matters:** a frame seen by an uncalibrated camera never gets
a position. Wrong-but-plausible coordinates are the one failure mode this
product cannot survive on stage.

**Measured:** ep4 hero keeps 70s of 94s wide across 4 angles; ep1 keeps 26s
of 57s across 5 (its production leans on floor cams, but it has the episode's
only most-replayed heatmap — so ep1 showcases the attention lane, ep4 the CV
lane).

**Revisit if:** the click budget (4 corners x N angles x 2 fights) is too
much at the venue — drop to --keep-top 1 and accept elevated-only coverage.
