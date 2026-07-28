"""D3 — owner: Pranav.

OpenCV click-tool: a human clicks 4+ known floor points on a chosen wide frame
(print the 48 ft box diagram first: corners, screw hazards). Computes the
homography, saves calibration.json, prints the reprojection error. --check
overlays the projected floor grid for eyeball validation.

The clicking is a HUMAN task (spec 9.3). This module provides the tool.

``calibration.json`` is a Phase-D-only artifact — it is not in schemas.py's
``_ARTIFACTS`` (spec §5 only covers cross-phase contracts). It lives at
``data/processed/<fight_id>/calibration.json`` alongside the contract files.

Done when
---------
A synthetic test with a known H recovers points to under 2% error.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Sequence

import cv2
import numpy as np
from pydantic import BaseModel, ConfigDict, Field

from .. import schemas as S

__phase__ = "D3"
__owner__ = "Pranav"

# --------------------------------------------------------------------------
# The floor reference points a human is asked to click, in order.
#
# The 4 box corners are exact by construction (the BattleBox is a known
# S.FLOOR_M x S.FLOOR_M square, origin at one corner — same convention as
# schemas.py / fixtures.py). Extra points (screw hazard covers, entry gate
# edges) sharpen the fit but their real-world coordinates aren't in this repo
# yet — append them here once an arena diagram is available; the tool already
# accepts any number of points >= 4.
# --------------------------------------------------------------------------
CALIBRATION_POINTS: list[tuple[str, tuple[float, float]]] = [
    ("corner_near_left", (0.0, 0.0)),
    ("corner_near_right", (S.FLOOR_M, 0.0)),
    ("corner_far_right", (S.FLOOR_M, S.FLOOR_M)),
    ("corner_far_left", (0.0, S.FLOOR_M)),
]


class Calibration(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fight_id: str
    image_points: list[list[float]]
    floor_points: list[list[float]]
    #: Row-major 3x3, maps homogeneous image pixels -> homogeneous floor metres.
    homography: list[list[float]]
    reprojection_error_m: float
    source_frame: str


# --------------------------------------------------------------------------
# Pure geometry — no I/O, no GUI. This is what the fixture-replay test and
# track.py both call.
# --------------------------------------------------------------------------


def compute_homography(
    image_points: Sequence[tuple[float, float]],
    floor_points: Sequence[tuple[float, float]],
) -> tuple[np.ndarray, float]:
    """Fit image -> floor homography from point correspondences.

    Returns ``(H, reprojection_error_m)`` where error is the RMS distance, in
    metres, between each floor point and its image point reprojected through H.
    """
    if len(image_points) < 4 or len(floor_points) < 4:
        raise ValueError("need at least 4 point correspondences to fit a homography")
    if len(image_points) != len(floor_points):
        raise ValueError("image_points and floor_points must be the same length")

    img = np.asarray(image_points, dtype=np.float64)
    flr = np.asarray(floor_points, dtype=np.float64)

    method = cv2.LMEDS if len(img) > 4 else 0
    H, _mask = cv2.findHomography(img, flr, method=method)
    if H is None:
        raise ValueError("homography fit failed — points are likely collinear or degenerate")

    reprojected = apply_homography(H, img)
    err = float(np.sqrt(np.mean(np.sum((reprojected - flr) ** 2, axis=1))))
    return H, err


def apply_homography(H: np.ndarray, points: Sequence[tuple[float, float]] | np.ndarray) -> np.ndarray:
    """Project 2D points through a 3x3 homography. Shape (N, 2) in, (N, 2) out."""
    pts = np.asarray(points, dtype=np.float64).reshape(-1, 2)
    homog = np.concatenate([pts, np.ones((len(pts), 1))], axis=1)
    out = homog @ H.T
    out = out[:, :2] / out[:, 2:3]
    return out


def invert_homography(H: np.ndarray) -> np.ndarray:
    return np.linalg.inv(H)


# --------------------------------------------------------------------------
# I/O helpers
# --------------------------------------------------------------------------


def calibration_path(fight_id: str, angle: int | None = None) -> Path:
    """``calibration.json`` (legacy single-camera) or ``calibration_a<N>.json``.

    Broadcast fights cut between several cameras, each needing its own
    homography (see angles.py). Angle 0 is additionally mirrored to the legacy
    path so single-camera consumers keep working unchanged.
    """
    name = "calibration.json" if angle is None else f"calibration_a{angle}.json"
    return S.fight_dir(fight_id) / name


def save_calibration(cal: Calibration, angle: int | None = None) -> Path:
    path = calibration_path(cal.fight_id, angle)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(cal.model_dump(mode="json"), indent=2) + "\n"
    path.write_text(payload, encoding="utf-8")
    if angle == 0:  # keep the legacy path in lockstep with the primary camera
        calibration_path(cal.fight_id).write_text(payload, encoding="utf-8")
    return path


def load_calibration(fight_id: str, angle: int | None = None) -> Calibration:
    path = calibration_path(fight_id, angle)
    if not path.exists():
        raise FileNotFoundError(f"{path} not found — run `bb calibrate --fight-id {fight_id}` first.")
    return Calibration.model_validate_json(path.read_text(encoding="utf-8"))


def load_all_calibrations(fight_id: str) -> dict[int, Calibration]:
    """Every per-angle calibration on disk. The legacy calibration.json counts
    as angle 0 when no explicit calibration_a0.json exists."""
    out: dict[int, Calibration] = {}
    for p in S.fight_dir(fight_id).glob("calibration_a*.json"):
        try:
            n = int(p.stem.rsplit("a", 1)[1])
        except ValueError:
            continue
        out[n] = Calibration.model_validate_json(p.read_text(encoding="utf-8"))
    if 0 not in out and calibration_path(fight_id).exists():
        out[0] = load_calibration(fight_id)
    return out


def _angle_example_frame(fight_id: str, angle: int) -> Path | None:
    """The representative frame angles.py recorded for this camera angle."""
    angles_file = S.fight_dir(fight_id) / "angles.json"
    if not angles_file.exists():
        return None
    data = json.loads(angles_file.read_text(encoding="utf-8"))
    for a in data.get("angles", []):
        if a.get("angle_id") == angle and a.get("example_frame"):
            p = Path(a["example_frame"])
            return p if p.exists() else None
    return None


def _pick_calibration_frame(fight_id: str, angle: int | None = None) -> tuple[np.ndarray, str]:
    """A representative wide frame to click on.

    With an angle given, use that camera cluster's example frame from
    angles.json; otherwise fall back to the first extracted keyframe."""
    if angle is not None:
        p = _angle_example_frame(fight_id, angle)
        if p is not None:
            frame = cv2.imread(str(p))
            if frame is not None:
                return frame, p.name
        print(f"no angles.json example for angle {angle} — falling back to the first keyframe")
    key_dir = S.FRAMES_DIR / fight_id / "key"
    candidates = sorted(key_dir.glob("*.jpg")) if key_dir.exists() else []
    if not candidates:
        track_dir = S.FRAMES_DIR / fight_id / "track"
        candidates = sorted(track_dir.glob("*.jpg")) if track_dir.exists() else []
    if not candidates:
        raise FileNotFoundError(
            f"no extracted frames for {fight_id!r} under {S.FRAMES_DIR / fight_id} — run `bb ingest` first."
        )
    frame = cv2.imread(str(candidates[0]))
    if frame is None:
        raise RuntimeError(f"could not read {candidates[0]}")
    return frame, candidates[0].name


# --------------------------------------------------------------------------
# Interactive click UI
# --------------------------------------------------------------------------


def _click_floor_points(
    frame: np.ndarray, labeled_points: list[tuple[str, tuple[float, float]]]
) -> list[tuple[float, float]]:
    """Prompt a human to click each labelled floor point, in order.

    Left-click records the next point; 'r' undoes the last click; enter/'q'
    confirms once every point is placed; escape aborts.
    """
    clicked: list[tuple[float, float]] = []
    window = "bb calibrate — click floor points in order, r=undo, enter=done, esc=cancel"

    def _redraw() -> np.ndarray:
        img = frame.copy()
        for i, (px, py) in enumerate(clicked):
            cv2.drawMarker(img, (int(px), int(py)), (0, 255, 0), cv2.MARKER_CROSS, 16, 2)
            cv2.putText(
                img, labeled_points[i][0], (int(px) + 10, int(py) - 10),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1, cv2.LINE_AA,
            )
        if len(clicked) < len(labeled_points):
            nxt = labeled_points[len(clicked)][0]
            cv2.putText(
                img, f"click: {nxt}", (16, 28),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2, cv2.LINE_AA,
            )
        return img

    def _on_mouse(event: int, x: int, y: int, flags: int, userdata: object) -> None:
        if event == cv2.EVENT_LBUTTONDOWN and len(clicked) < len(labeled_points):
            clicked.append((float(x), float(y)))

    cv2.namedWindow(window, cv2.WINDOW_NORMAL)
    cv2.setMouseCallback(window, _on_mouse)
    try:
        while True:
            cv2.imshow(window, _redraw())
            key = cv2.waitKey(20) & 0xFF
            if key == ord("r") and clicked:
                clicked.pop()
            elif key in (13, ord("q")) and len(clicked) == len(labeled_points):
                break
            elif key == 27:
                raise RuntimeError("calibration cancelled by user")
    finally:
        cv2.destroyWindow(window)
    return clicked


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------


def calibrate(fight_id: str, check: bool = False, angle: int | None = None) -> Path:
    if check:
        return _render_check(fight_id, angle=angle)

    frame, frame_name = _pick_calibration_frame(fight_id, angle=angle)
    labels = [lbl for lbl, _ in CALIBRATION_POINTS]
    floor_pts = [pt for _, pt in CALIBRATION_POINTS]
    which = f" (camera angle {angle})" if angle is not None else ""
    print(f"Click {len(labels)} floor points on {frame_name}{which} in this order: {', '.join(labels)}")

    image_pts = _click_floor_points(frame, CALIBRATION_POINTS)
    H, err = compute_homography(image_pts, floor_pts)

    cal = Calibration(
        fight_id=fight_id,
        image_points=[list(p) for p in image_pts],
        floor_points=[list(p) for p in floor_pts],
        homography=H.tolist(),
        reprojection_error_m=err,
        source_frame=frame_name,
    )
    path = save_calibration(cal, angle=angle)
    print(f"reprojection error: {err:.3f} m ({100 * err / S.FLOOR_M:.2f}% of floor edge)")
    print(f"{path.name} -> {path}")
    return path


def _render_check(fight_id: str, angle: int | None = None) -> Path:
    """Overlay the projected floor grid (1 m spacing) for eyeball validation."""
    cal = load_calibration(fight_id, angle=angle)
    frame, _ = _pick_calibration_frame(fight_id, angle=angle)
    H_inv = invert_homography(np.array(cal.homography))

    img = frame.copy()
    n = int(round(S.FLOOR_M))
    for i in range(n + 1):
        floor_line = [(float(i), y) for y in np.linspace(0, S.FLOOR_M, 30)]
        px = apply_homography(H_inv, floor_line)
        for a, b in zip(px[:-1], px[1:]):
            cv2.line(img, tuple(a.astype(int)), tuple(b.astype(int)), (0, 200, 0), 1, cv2.LINE_AA)
        floor_line = [(x, float(i)) for x in np.linspace(0, S.FLOOR_M, 30)]
        px = apply_homography(H_inv, floor_line)
        for a, b in zip(px[:-1], px[1:]):
            cv2.line(img, tuple(a.astype(int)), tuple(b.astype(int)), (0, 200, 0), 1, cv2.LINE_AA)

    out_path = S.fight_dir(fight_id, create=True) / "calibration_check.png"
    cv2.imwrite(str(out_path), img)
    print(f"calibration_check.png -> {out_path}")

    try:
        cv2.imshow("bb calibrate --check (any key to close)", img)
        cv2.waitKey(0)
        cv2.destroyAllWindows()
    except cv2.error:
        print("(no display available — inspect the saved PNG instead)")
    return out_path
