"""D4.5 - owner: Aslan (integration fix, 28 Jul evening).

Broadcast footage cuts between MULTIPLE wide-ish camera angles. The homography
from D3 is only valid for the one angle the human calibrated, so projecting a
different wide angle through it produces garbage floor coordinates that LOOK
plausible. This stage protects the contract's honesty guarantee:

    only frames seen by the calibrated camera carry positions;
    every other angle is an explicit gap, never a wrong number.

How: each wide shot gets a small blurred grayscale thumbnail of its mid-frame
as an "angle signature" (at 48x27 the static arena background dominates the
moving robots). Signatures are greedily clustered by cosine similarity; the
cluster with the most screen time is the dominant angle. Wide shots outside
the dominant cluster are rewritten to wide=False in shots.json - downstream
(track.py, telemetry, the frontend's hatched voids) already treats that
correctly with no code changes.

The full clustering is preserved in angles.json so a second angle can be
promoted later (calibrate it, re-run with --keep-angle N).

Run AFTER `bb shots`, BEFORE `bb calibrate` / `bb track`.
"""

from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np

from . import shots as SH
from .. import schemas as S

__phase__ = "D4.5"
__owner__ = "Aslan"

#: Thumbnail size for angle signatures (w, h). Small enough that two robots
#: (~5% of frame area each) cannot dominate the correlation.
_SIG_SIZE = (48, 27)
#: Cosine similarity above this joins an existing angle cluster. Real broadcast
#: lighting (hit strobes, sparks) perturbs same-camera signatures; 0.80
#: fragmented the hero fight's elevated camera into 4 clusters.
_SIM_THRESHOLD = 0.70
#: A cluster must hold at least this much total time to be listed at all.
_MIN_CLUSTER_S = 1.0
#: Yellow wall-padding centroid above this frame fraction (0 = top) reads as
#: "elevated camera". The BattleBox's padding is a saturated yellow band: seen
#: from the elevated wide it sits in the top ~40% of frame; from a floor-level
#: cam it crosses the middle (ep1's low cams measure 0.52-0.66). 0.48 admits
#: mid-height cameras (ep4's 35s workhorse cam sits at 0.457) whose homography
#: is still serviceable, while genuine floor-level cams stay excluded.
_ELEVATED_MAX_FRAC = 0.48


def angles_path(fight_id: str) -> Path:
    return S.fight_dir(fight_id) / "angles.json"


def _signature(frame_path: Path) -> np.ndarray | None:
    img = cv2.imread(str(frame_path))
    if img is None:
        return None
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    small = cv2.resize(gray, _SIG_SIZE, interpolation=cv2.INTER_AREA).astype(np.float32)
    small = cv2.GaussianBlur(small, (3, 3), 0)
    v = small.flatten()
    v -= v.mean()
    n = np.linalg.norm(v)
    return v / n if n > 1e-6 else None


def _mid_frame(fight_id: str, shot: SH.Shot) -> Path | None:
    mid_t = 0.5 * (shot.start_t + shot.end_t)
    key_dir = S.FRAMES_DIR / fight_id / "key"
    track_dir = S.FRAMES_DIR / fight_id / "track"
    return SH._nearest_frame(key_dir, mid_t, fps=1) or SH._nearest_frame(track_dir, mid_t, fps=10)


#: Frames sampled per shot for the averaged signature.
_SIG_SAMPLES = 5


def _yellow_band_frac(frame_path: Path) -> float | None:
    """Mean image row (as a 0-1 fraction from the top) of saturated-yellow
    pixels - the arena's wall padding. None when there's no meaningful yellow
    (close-ups, crowd shots)."""
    img = cv2.imread(str(frame_path))
    if img is None:
        return None
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, (18, 90, 90), (38, 255, 255))
    ys = np.nonzero(mask)[0]
    if len(ys) < 0.001 * mask.size:  # under 0.1% of pixels: not the arena band
        return None
    return float(ys.mean() / mask.shape[0])


def _shot_signature(fight_id: str, shot: SH.Shot) -> np.ndarray | None:
    """Average the signature over several frames spread through the shot.

    A single frame's signature can be dominated by the robots (they are the
    highest-contrast thing on a dark floor); averaged across the shot they
    smear out while the static arena background reinforces. Measured on a
    synthetic two-camera rig, this flips same-camera similarity from ~0.04
    (single frame, robot-position-driven) to >0.9.
    """
    track_dir = S.FRAMES_DIR / fight_id / "track"
    paths = SH._frames_in_range(track_dir, shot.start_t, shot.end_t, fps=10, limit=_SIG_SAMPLES)
    if not paths:  # fall back to the single mid-frame (key dir at 1 fps)
        mid = _mid_frame(fight_id, shot)
        return _signature(mid) if mid is not None else None
    sigs = [s for p in paths if (s := _signature(p)) is not None]
    if not sigs:
        return None
    avg = np.mean(sigs, axis=0)
    n = np.linalg.norm(avg)
    return avg / n if n > 1e-6 else None


def cluster(fight_id: str, keep_angle: int = 0, keep_top: int = 1) -> Path:
    """Cluster wide shots by camera angle; demote all but the kept angles.

    ``keep_top=N`` keeps the N best-ranked camera angles (elevation first,
    screen time second) - each then gets its own `bb calibrate --angle N`.
    ``keep_angle`` shifts which single cluster is kept when ``keep_top`` is 1.

    Idempotent: re-runs re-cluster from the ORIGINAL wide flags stored in
    angles.json, so switching the keep flags never loses information.
    """
    shots = SH.load_shots(fight_id)

    # Restore original wide flags if a previous run already demoted some.
    prior = None
    if angles_path(fight_id).exists():
        prior = json.loads(angles_path(fight_id).read_text(encoding="utf-8"))
        for i, was_wide in zip(range(len(shots.shots)), prior["original_wide"]):
            shots.shots[i].wide = was_wide

    wide_idx = [i for i, sh in enumerate(shots.shots) if sh.wide]

    # signatures (averaged across the shot - see _shot_signature)
    sigs: dict[int, np.ndarray] = {}
    for i in wide_idx:
        if (sig := _shot_signature(fight_id, shots.shots[i])) is not None:
            sigs[i] = sig

    # greedy clustering against running centroids
    clusters: list[dict] = []  # {"members": [i], "centroid": vec, "time_s": float}
    for i in wide_idx:
        if i not in sigs:
            continue
        dur = shots.shots[i].end_t - shots.shots[i].start_t
        best, best_sim = None, _SIM_THRESHOLD
        for c in clusters:
            sim = float(np.dot(sigs[i], c["centroid"]))
            if sim > best_sim:
                best, best_sim = c, sim
        if best is None:
            clusters.append({"members": [i], "centroid": sigs[i].copy(), "time_s": dur})
        else:
            best["members"].append(i)
            k = len(best["members"])
            best["centroid"] = best["centroid"] * ((k - 1) / k) + sigs[i] * (1 / k)
            n = np.linalg.norm(best["centroid"])
            if n > 1e-6:
                best["centroid"] /= n
            best["time_s"] += dur

    clusters = [c for c in clusters if c["time_s"] >= _MIN_CLUSTER_S]

    if not clusters:
        print("no wide shots to cluster - nothing changed.")
        return angles_path(fight_id)

    # Rank by calibration suitability first, screen time second. A floor-level
    # corner cam can out-time the elevated wide, but its grazing angle makes
    # the floor homography garbage - elevation wins, time breaks ties.
    for c in clusters:
        fracs = [
            f
            for i in c["members"]
            if (p := _mid_frame(fight_id, shots.shots[i])) is not None
            and (f := _yellow_band_frac(p)) is not None
        ]
        band = float(np.median(fracs)) if fracs else 1.0
        c["yellow_band_frac"] = round(band, 3)
        c["elevated"] = band < _ELEVATED_MAX_FRAC
    clusters.sort(key=lambda c: (not c["elevated"], -c["time_s"]))

    if keep_top > 1:
        kept_ids = set(range(min(keep_top, len(clusters))))
    else:
        kept_ids = {keep_angle} if keep_angle < len(clusters) else set()
    keep = {i for n in kept_ids for i in clusters[n]["members"]}
    demoted = 0
    original_wide = [bool(sh.wide) for sh in shots.shots]
    for i in wide_idx:
        if i not in keep:
            shots.shots[i].wide = False
            demoted += 1
    SH.save_shots(shots)

    first_kept = min(kept_ids) if kept_ids else 0
    rep = _mid_frame(fight_id, shots.shots[clusters[first_kept]["members"][0]])
    payload = {
        "fight_id": fight_id,
        "original_wide": original_wide,
        "kept_angles": sorted(kept_ids),
        "angles": [
            {
                "angle_id": n,
                "shots": c["members"],
                "time_s": round(c["time_s"], 2),
                "kept": n in kept_ids,
                "elevated": c["elevated"],
                "yellow_band_frac": c["yellow_band_frac"],
                "example_frame": str(_mid_frame(fight_id, shots.shots[c["members"][0]]) or ""),
            }
            for n, c in enumerate(clusters)
        ],
    }
    angles_path(fight_id).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    kept_s = sum(clusters[n]["time_s"] for n in kept_ids)
    total_s = sum(c["time_s"] for c in clusters)
    print(
        f"{len(clusters)} camera angles across {len(wide_idx)} wide shots; "
        f"kept {sorted(kept_ids)} ({kept_s:.0f}s of {total_s:.0f}s wide, "
        f"{demoted} shots demoted to gaps)"
    )
    print(f"calibrate each kept angle: bb calibrate -f {fight_id} --angle <N>")
    print(f"first kept angle's frame: {rep}")
    for a in payload["angles"]:
        mark = " <- KEPT" if a["kept"] else ""
        el = "elevated" if a["elevated"] else "low     "
        print(f"  angle {a['angle_id']}: {len(a['shots'])} shots, {a['time_s']:6.2f}s  {el}  band={a['yellow_band_frac']}{mark}")
    return angles_path(fight_id)
