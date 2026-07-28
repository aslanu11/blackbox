"""E4 - owner: Aslan.

Copy data/processed/* JSON + PNGs + overlay mp4s into web/public/data/ and
write index.json - the manifest of exported fights the frontend loads at
startup.

Done when
---------
`bb export && cd web && npm run dev` shows the fixture fight end to end.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

from . import schemas as S

__phase__ = "E4"
__owner__ = "Aslan"

WEB_DATA = S.ROOT / "web" / "public" / "data"

#: Per-fight artifacts worth shipping. Missing ones are simply skipped -
#: the frontend renders honest empty states.
_FILES = (
    "meta.json",
    "tracks.json",
    "events.json",
    "telemetry.json",
    "attention.json",
    "scorecard.json",
    "overlay.mp4",
)


def _copy_video(src: Path, dst: Path) -> None:
    """Ship the overlay as browser-playable H.264.

    OpenCV's VideoWriter emits mp4v (MPEG-4 part 2), which <video> cannot
    decode in any current browser - the page shows a dead player with no
    error. Transcode on export when ffmpeg is available; otherwise copy
    as-is and warn. Skipped when the destination is already up to date.
    """
    if dst.exists() and dst.stat().st_mtime >= src.stat().st_mtime:
        return
    if shutil.which("ffmpeg"):
        proc = subprocess.run(
            [
                "ffmpeg", "-y", "-v", "error",
                "-i", str(src),
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
                "-pix_fmt", "yuv420p", "-movflags", "+faststart",
                str(dst),
            ],
            capture_output=True,
            text=True,
        )
        if proc.returncode == 0:
            return
        print(f"  [export] ffmpeg transcode failed, copying raw: {proc.stderr[-300:]}", file=sys.stderr)
    else:
        print("  [export] warning: ffmpeg not found - overlay copied as mp4v and will NOT play in a browser", file=sys.stderr)
    shutil.copy2(src, dst)


def export(fight_id: str | None = None) -> Path:
    """Copy artifacts for one fight (or all) and rebuild index.json."""
    fights = [fight_id] if fight_id else S.list_fights()

    for fid in fights:
        src = S.fight_dir(fid)
        if not (src / "meta.json").exists():
            continue
        dst = WEB_DATA / fid
        dst.mkdir(parents=True, exist_ok=True)
        for name in _FILES:
            if not (src / name).exists():
                continue
            if name.endswith(".mp4"):
                _copy_video(src / name, dst / name)
            else:
                shutil.copy2(src / name, dst / name)
        # Heatmap PNGs are named per bot - copy whatever exists.
        for png in src.glob("*.png"):
            shutil.copy2(png, dst / png.name)

    # League-wide artifacts.
    WEB_DATA.mkdir(parents=True, exist_ok=True)
    for name in ("media_value.json", "calibration.png"):
        src = S.PROCESSED_DIR / name
        if src.exists():
            shutil.copy2(src, WEB_DATA / name)

    # The index the frontend loads at startup: id + meta + which artifacts exist.
    entries = []
    for d in sorted(WEB_DATA.iterdir()):
        if not d.is_dir() or not (d / "meta.json").exists():
            continue
        meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
        entries.append(
            {
                "fight_id": meta["fight_id"],
                "bots": meta["bots"],
                "colors": meta.get("colors", {}),
                "role": meta.get("role"),
                "result": meta.get("result"),
                "has": {name.split(".")[0]: (d / name).exists() for name in _FILES},
            }
        )

    index_path = WEB_DATA / "index.json"
    index_path.write_text(json.dumps({"fights": entries}, indent=2) + "\n", encoding="utf-8")
    return index_path
