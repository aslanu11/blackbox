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

## TEMPLATE — copy this

## YYYY-MM-DD — <one-line decision>

**What:**

**Why:**

**Revisit if:**
