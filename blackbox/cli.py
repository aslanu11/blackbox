"""A4 - the `bb` CLI. One entry point for the whole pipeline.

Unimplemented subcommands exit non-zero with the phase and owner that will
implement them, so a teammate running ahead of the build order gets a useful
message instead of a traceback.
"""

from __future__ import annotations

import shutil
import sys
from typing import Annotated

import typer

app = typer.Typer(
    name="bb",
    help="BLACKBOX - the flight recorder for robot combat.",
    no_args_is_help=True,
    add_completion=False,
)

FightId = Annotated[str, typer.Option("--fight-id", "-f", help="Fight id from data/manifest.yaml.")]

#: STILL-UNIMPLEMENTED subcommand -> (phase, owner). Mirrors TEAM.md.
#: Remove a command from this dict when you implement it - test_cli asserts
#: that everything listed here exits 2 with the owner's name.
OWNERS: dict[str, tuple[str, str]] = {
    "fetch": ("C2", "Aslan"),
    "ingest": ("D1", "Pranav"),
    "shots": ("D2", "Pranav"),
    "calibrate": ("D3", "Pranav"),
    "track": ("D4", "Pranav"),
    "scorecard": ("B4", "Aslan"),
    "attention": ("C2", "Aslan"),
    "overlay": ("D5", "Pranav"),
    "export": ("E4", "Aslan"),
}


def _todo(cmd: str) -> None:
    phase, owner = OWNERS.get(cmd, ("?", "?"))
    typer.secho(
        f"`bb {cmd}` is not implemented yet - phase {phase}, owned by {owner}.\n"
        f"See README.md 'Build order' and TEAM.md before implementing it yourself.",
        fg=typer.colors.YELLOW,
        err=True,
    )
    raise typer.Exit(code=2)


# --------------------------------------------------------------------------
# Implemented
# --------------------------------------------------------------------------


@app.command()
def fixture() -> None:
    """Generate the deterministic synthetic fight (A3). No network, no data."""
    from . import fixtures

    written = fixtures.build()
    for name, path in written.items():
        typer.echo(f"  {name:9s} -> {path}")
    typer.secho(f"fixture {fixtures.FIGHT_ID} written.", fg=typer.colors.GREEN)


@app.command()
def doctor() -> None:
    """Check the local environment. Run this first on a new machine."""
    ok = True

    typer.echo(f"python      {sys.version.split()[0]}")

    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        typer.echo(f"ffmpeg      {ffmpeg}")
    else:
        ok = False
        typer.secho(
            "ffmpeg      MISSING - required by D1 (ingest) and D5 (overlay).\n"
            "            macOS:   brew install ffmpeg\n"
            "            Ubuntu:  sudo apt install ffmpeg\n"
            "            Windows: winget install Gyan.FFmpeg  (then restart the shell)",
            fg=typer.colors.RED,
        )

    try:
        import cv2  # noqa: F401

        typer.echo(f"opencv      {cv2.__version__}")
    except ImportError:
        ok = False
        typer.secho("opencv      MISSING - run `pip install -e .`", fg=typer.colors.RED)

    from . import schemas as S

    typer.echo(f"data dir    {S.DATA_DIR}")

    env = S.ROOT / ".env"
    typer.echo(f".env        {'present' if env.exists() else 'absent (fine until C1/§11)'}")

    if not ok:
        raise typer.Exit(code=1)
    typer.secho("environment OK.", fg=typer.colors.GREEN)


@app.command()
def fights() -> None:
    """List fights that have artifacts on disk."""
    from . import schemas as S

    ids = S.list_fights()
    if not ids:
        typer.echo("No processed fights. Run `bb fixture` to make one.")
        return
    for fid in ids:
        kinds = [k for k in ("meta", "tracks", "events", "telemetry", "attention", "scorecard") if S.exists(fid, k)]
        typer.echo(f"  {fid:16s} {' '.join(kinds)}")


# --------------------------------------------------------------------------
# Stubs - each raises until its phase lands. Signatures are stable; implementers
# fill the body and must not change the flags without a note in DECISIONS.md.
# --------------------------------------------------------------------------


@app.command()
def fetch(fight_id: FightId = "") -> None:
    """C2 - download footage / video info for a fight. Human-triggered only."""
    _todo("fetch")


@app.command()
def ingest(fight_id: FightId) -> None:
    """D1 - cut the fight clip and extract frames at 10 fps (+1 fps keyframes)."""
    _todo("ingest")


@app.command()
def shots(
    fight_id: FightId,
    heuristic: Annotated[bool, typer.Option("--heuristic", help="Skip the LLM; use frame-diff variance.")] = False,
) -> None:
    """D2 - scene detection + wide-shot classification -> shots.json."""
    _todo("shots")


@app.command()
def calibrate(
    fight_id: FightId,
    check: Annotated[bool, typer.Option("--check", help="Overlay the projected floor grid instead.")] = False,
) -> None:
    """D3 - click 4+ known floor points -> homography -> calibration.json."""
    _todo("calibrate")


@app.command()
def track(
    fight_id: FightId,
    review: Annotated[bool, typer.Option("--review", help="Render a side-by-side to eyeball.")] = False,
) -> None:
    """D4 - CSRT tracking per wide shot -> tracks.json (gaps stay explicit)."""
    _todo("track")


@app.command()
def telemetry(fight_id: FightId) -> None:
    """B1 - speed / control / mobility / heatmaps -> telemetry.json."""
    from .pipeline import telemetry as mod

    typer.echo(f"  telemetry -> {mod.compute(fight_id)}")


@app.command()
def events(fight_id: FightId) -> None:
    """B2 - hit / KO / hazard detection -> events.json."""
    from .pipeline import events as mod

    path = mod.detect(fight_id)
    from . import schemas as S

    ev = S.load_events(fight_id)
    typer.echo(f"  events    -> {path} ({len(ev.events)} events)")


@app.command()
def momentum(
    fight_id: FightId = "",
    calibrate: Annotated[bool, typer.Option("--calibrate", help="Reliability curve + Brier score across the corpus.")] = False,
) -> None:
    """B3 - win-probability curve into telemetry.json."""
    from .pipeline import momentum as mod

    if calibrate:
        result = mod.calibrate()
        typer.echo(f"  Brier {result['brier']:.3f} over {result['n_samples']} samples -> {result['plot']}")
        return
    if not fight_id:
        typer.secho("momentum needs --fight-id (or --calibrate).", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2)
    typer.echo(f"  momentum  -> {mod.compute(fight_id)}")


@app.command()
def scorecard(
    fight_id: FightId = "",
    leaderboard: Annotated[bool, typer.Option("--leaderboard", help="Aggregate the Robbery Leaderboard.")] = False,
) -> None:
    """B4 - rubric model vs official verdict -> scorecard.json."""
    _todo("scorecard")


@app.command()
def attention(fight_id: FightId) -> None:
    """C2 - pull the YouTube most-replayed heatmap -> attention.json."""
    _todo("attention")


@app.command()
def fuse(fight_id: FightId = "") -> None:
    """B5 - align attention to events; write media_value.json."""
    from .pipeline import fuse as mod

    if fight_id:
        typer.echo(f"  fuse      -> {mod.fuse(fight_id)}")
    typer.echo(f"  media     -> {mod.media_value()}")


@app.command()
def overlay(fight_id: FightId) -> None:
    """D5 - burn trails / hit flashes / momentum needle into overlay.mp4."""
    _todo("overlay")


@app.command()
def export(fight_id: FightId = "") -> None:
    """E4 - copy processed artifacts into web/public/data/ and write index.json."""
    _todo("export")


@app.command()
def run(fight_id: FightId) -> None:
    """Full pipeline for one fight: ingest -> ... -> overlay."""
    typer.secho(
        "`bb run` chains ingest -> shots -> track -> telemetry -> events -> "
        "momentum -> fuse -> overlay. It lands once those exist (F1).",
        fg=typer.colors.YELLOW,
        err=True,
    )
    raise typer.Exit(code=2)


if __name__ == "__main__":
    app()
