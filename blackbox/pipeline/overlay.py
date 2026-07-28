"""D5 — owner: Pranav.

Burn the overlay into an mp4 with OpenCV/ffmpeg: fading position trails in the
FightMeta bot colours, bot labels, hit-flash rings at event times, mobility
bars, a small momentum needle read from telemetry.json, and a recorder-style
footer reading "COVERAGE 81%  CH1 CH2 CH3". 720p, hero segment only, 90 s max.

Do NOT build a live canvas-over-video overlay in the frontend (spec 2.6) -
the overlay is burned into the file.

Two rendering modes, picked automatically:
* **Real footage** — data/frames/<fight_id>/track/*.jpg + calibration.json
  exist: burn onto the actual frames, projecting floor metres to pixels
  through the inverse homography.
* **Schematic** — nothing to burn onto yet (this is how fixture-001 works,
  since the fixture has no video): render a fixed top-down floor canvas
  straight from tracks.json. Same drawing code either way.

events.json (B2) and telemetry.json (B1) are optional inputs — if a fight
hasn't had those phases run yet, overlay still renders trails from tracks.json
alone and skips the hit flashes / momentum needle / mobility bars.

Done when
---------
`bb overlay --fight-id fixture-001` produces a watchable mp4 from synthetic data.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

import cv2
import numpy as np

from . import calibrate as C
from .. import schemas as S

__phase__ = "D5"
__owner__ = "Pranav"

OUT_SIZE = (1280, 720)  # w, h — spec 2.6: 720p
MAX_HERO_S = 90.0
TRAIL_S = 3.0
HIT_FLASH_S = 0.4
KO_CUSHION_S = 5.0
SCHEMATIC_CANVAS = (800, 800)
SCHEMATIC_MARGIN = 40.0

ToPx = Callable[[list[float]], np.ndarray]
GetBase = Callable[[int], np.ndarray]


# --------------------------------------------------------------------------
# Optional inputs — degrade gracefully if B1/B2 haven't landed for this fight.
# --------------------------------------------------------------------------


def _try_load_events(fight_id: str) -> S.Events | None:
    try:
        return S.load_events(fight_id)
    except FileNotFoundError:
        return None


def _try_load_telemetry(fight_id: str) -> S.Telemetry | None:
    try:
        return S.load_telemetry(fight_id)
    except FileNotFoundError:
        return None


def _nearest_series_value(series: list[list[float]], t: float) -> float | None:
    if not series:
        return None
    arr = np.asarray(series)
    i = int(np.argmin(np.abs(arr[:, 0] - t)))
    return float(arr[i, 1])


# --------------------------------------------------------------------------
# Pixel projection — real footage or schematic canvas.
# --------------------------------------------------------------------------


def _real_footage_projection(fight_id: str) -> tuple[ToPx, GetBase, tuple[int, int]] | None:
    frames_dir = S.FRAMES_DIR / fight_id / "track"
    if not (C.calibration_path(fight_id).exists() and frames_dir.exists()):
        return None
    frame_paths = sorted(frames_dir.glob("*.jpg"))
    if not frame_paths:
        return None

    cal = C.load_calibration(fight_id)
    H_inv = C.invert_homography(np.array(cal.homography))
    sample = cv2.imread(str(frame_paths[0]))
    if sample is None:
        return None
    size = (sample.shape[1], sample.shape[0])

    def to_px(xy: list[float]) -> np.ndarray:
        return C.apply_homography(H_inv, [xy])[0]

    def get_base(i: int) -> np.ndarray:
        if 0 <= i < len(frame_paths):
            img = cv2.imread(str(frame_paths[i]))
            if img is not None:
                return img
        return np.full((size[1], size[0], 3), 20, dtype=np.uint8)

    return to_px, get_base, size


def _schematic_projection() -> tuple[ToPx, GetBase, tuple[int, int]]:
    w, h = SCHEMATIC_CANVAS
    scale = (min(w, h) - 2 * SCHEMATIC_MARGIN) / S.FLOOR_M

    def to_px(xy: list[float]) -> np.ndarray:
        return np.array([SCHEMATIC_MARGIN + xy[0] * scale, SCHEMATIC_MARGIN + xy[1] * scale])

    def get_base(_i: int) -> np.ndarray:
        img = np.full((h, w, 3), (22, 22, 22), dtype=np.uint8)
        floor_edge = int(min(w, h) - 2 * SCHEMATIC_MARGIN)
        m = int(SCHEMATIC_MARGIN)
        cv2.rectangle(img, (m, m), (m + floor_edge, m + floor_edge), (48, 48, 48), -1)
        for g in range(int(S.FLOOR_M) + 1):
            off = int(SCHEMATIC_MARGIN + g * scale)
            cv2.line(img, (off, m), (off, m + floor_edge), (34, 34, 34), 1, cv2.LINE_AA)
            cv2.line(img, (m, off), (m + floor_edge, off), (34, 34, 34), 1, cv2.LINE_AA)
        return img

    return to_px, get_base, (w, h)


# --------------------------------------------------------------------------
# Hero segment selection — spec: 90 s max, the interesting part.
# --------------------------------------------------------------------------


def _hero_window(duration_s: float, events: S.Events | None) -> tuple[float, float]:
    if duration_s <= MAX_HERO_S:
        return 0.0, duration_s

    center = None
    if events is not None:
        ko = [e for e in events.events if e.type == "ko"]
        if ko:
            center = ko[0].t + KO_CUSHION_S
        else:
            hits = [e for e in events.events if e.type == "hit" and e.magnitude is not None]
            if hits:
                center = max(hits, key=lambda e: e.magnitude).t
    if center is None:
        center = MAX_HERO_S / 2

    w0 = max(0.0, min(center - MAX_HERO_S / 2, duration_s - MAX_HERO_S))
    return w0, w0 + MAX_HERO_S


# --------------------------------------------------------------------------
# Drawing
# --------------------------------------------------------------------------


def _draw_trail(img: np.ndarray, to_px: ToPx, history: list[list[float] | None], color: tuple[int, int, int]) -> None:
    pts = [to_px(p) for p in history if p is not None]
    n = len(pts)
    for i in range(1, n):
        alpha = i / n
        c = tuple(int(ch * alpha) for ch in color)
        cv2.line(img, tuple(pts[i - 1].astype(int)), tuple(pts[i].astype(int)), c, 2, cv2.LINE_AA)


def _draw_bot(img: np.ndarray, to_px: ToPx, xy: list[float], name: str, color: tuple[int, int, int]) -> None:
    px = to_px(xy).astype(int)
    cv2.circle(img, tuple(px), 9, color, -1, cv2.LINE_AA)
    cv2.circle(img, tuple(px), 9, (255, 255, 255), 1, cv2.LINE_AA)
    cv2.putText(img, name, (px[0] + 12, px[1] - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1, cv2.LINE_AA)


def _draw_hit_flash(img: np.ndarray, to_px: ToPx, xy: list[float], t: float, event_t: float, magnitude: float | None) -> None:
    age = t - event_t
    if not (0 <= age < HIT_FLASH_S):
        return
    frac = 1 - age / HIT_FLASH_S
    radius = int(14 + 40 * (1 - frac) * min(1.0, (magnitude or 5.0) / 10.0))
    px = to_px(xy).astype(int)
    cv2.circle(img, tuple(px), radius, (0, 0, 255), max(1, int(3 * frac)), cv2.LINE_AA)


def _draw_mobility_bars(img: np.ndarray, bots: list[str], colors: dict[str, str], telemetry: S.Telemetry | None, t: float) -> None:
    if telemetry is None:
        return
    x0, y0, w, h, gap = 16, 16, 120, 12, 6
    for i, bot in enumerate(bots):
        series = telemetry.series.mobility.get(bot, [])
        val = _nearest_series_value(series, t)
        if val is None:
            continue
        y = y0 + i * (h + gap)
        color = _hex_to_bgr(colors.get(bot, "#FFFFFF"))
        cv2.rectangle(img, (x0, y), (x0 + w, y + h), (60, 60, 60), 1)
        cv2.rectangle(img, (x0, y), (x0 + int(w * max(0.0, min(1.0, val))), y + h), color, -1)
        cv2.putText(img, f"{bot} mobility", (x0 + w + 8, y + h - 2), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (200, 200, 200), 1, cv2.LINE_AA)


def _draw_momentum_needle(img: np.ndarray, size: tuple[int, int], telemetry: S.Telemetry | None, t: float, bots: list[str]) -> None:
    if telemetry is None or not telemetry.series.momentum:
        return
    val = _nearest_series_value(telemetry.series.momentum, t)
    if val is None:
        return
    w, _h = size
    bar_w, bar_h = 200, 10
    x0, y0 = w - bar_w - 16, 16
    cv2.rectangle(img, (x0, y0), (x0 + bar_w, y0 + bar_h), (60, 60, 60), 1)
    x_needle = int(x0 + bar_w * max(0.0, min(1.0, val)))
    cv2.line(img, (x_needle, y0 - 4), (x_needle, y0 + bar_h + 4), (0, 255, 255), 2, cv2.LINE_AA)
    label = f"{bots[0]} {val:.0%}" if bots else f"{val:.0%}"
    cv2.putText(img, label, (x0, y0 + bar_h + 20), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 200, 200), 1, cv2.LINE_AA)


def _draw_footer(img: np.ndarray, size: tuple[int, int], coverage: float) -> None:
    w, h = size
    text = f"COVERAGE {coverage:.0%}   CH1 MOMENTUM   CH2 EVENTS   CH3 ATTENTION"
    cv2.putText(img, text, (16, h - 14), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 220, 0), 1, cv2.LINE_AA)


def _hex_to_bgr(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    if len(h) != 6:
        return (255, 255, 255)
    r, g, b = (int(h[i : i + 2], 16) for i in (0, 2, 4))
    return (b, g, r)


def _letterbox(img: np.ndarray, target: tuple[int, int] = OUT_SIZE) -> np.ndarray:
    tw, th = target
    h, w = img.shape[:2]
    scale = min(tw / w, th / h)
    nw, nh = int(w * scale), int(h * scale)
    resized = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_AREA)
    canvas = np.zeros((th, tw, 3), dtype=np.uint8)
    x0, y0 = (tw - nw) // 2, (th - nh) // 2
    canvas[y0 : y0 + nh, x0 : x0 + nw] = resized
    return canvas


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------


def render(fight_id: str) -> Path:
    meta = S.load_meta(fight_id)
    tracks = S.load_tracks(fight_id)
    events = _try_load_events(fight_id)
    telemetry = _try_load_telemetry(fight_id)

    if not tracks.frames:
        raise ValueError(f"{fight_id}: tracks.json has no frames — run `bb track` first.")
    fps = tracks.fps
    duration_s = tracks.frames[-1].t

    w0, w1 = _hero_window(duration_s, events)
    i0, i1 = int(w0 * fps), min(len(tracks.frames), int(w1 * fps))
    window_frames = tracks.frames[i0:i1]

    projection = _real_footage_projection(fight_id)
    if projection is not None:
        to_px, get_base, size = projection
    else:
        to_px, get_base, size = _schematic_projection()

    out_path = S.fight_dir(fight_id, create=True) / "overlay.mp4"
    writer = cv2.VideoWriter(str(out_path), cv2.VideoWriter_fourcc(*"mp4v"), fps, OUT_SIZE)

    trail_len = int(TRAIL_S * fps)
    history: dict[str, list[list[float] | None]] = {b: [] for b in meta.bots}

    hit_events = [e for e in (events.events if events else []) if e.type in ("hit", "ko", "hazard")]

    try:
        for offset, tf in enumerate(window_frames):
            img = get_base(i0 + offset)  # get_base ignores the index in schematic mode

            for bot in meta.bots:
                history[bot].append(tf.pos.get(bot) if tf.pos else None)
                if len(history[bot]) > trail_len:
                    history[bot].pop(0)
                _draw_trail(img, to_px, history[bot], _hex_to_bgr(meta.colors.get(bot, "#FFFFFF")))

            if tf.pos:
                for bot, xy in tf.pos.items():
                    _draw_bot(img, to_px, xy, bot, _hex_to_bgr(meta.colors.get(bot, "#FFFFFF")))
                for ev in hit_events:
                    target_xy = tf.pos.get(ev.target) or tf.pos.get(ev.actor)
                    if target_xy is not None:
                        _draw_hit_flash(img, to_px, target_xy, tf.t, ev.t, ev.magnitude)

            _draw_mobility_bars(img, meta.bots, meta.colors, telemetry, tf.t)
            _draw_momentum_needle(img, size, telemetry, tf.t, meta.bots)
            _draw_footer(img, size, tracks.coverage)

            writer.write(_letterbox(img))
    finally:
        writer.release()

    print(f"overlay ({w1 - w0:.0f}s hero segment) -> {out_path}")
    return out_path
