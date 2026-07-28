"""A4 acceptance — the CLI surface exists and every stub names its owner."""

from __future__ import annotations

from typer.testing import CliRunner

from blackbox.cli import OWNERS, app

runner = CliRunner()

EXPECTED = {
    "fixture", "fetch", "ingest", "shots", "calibrate", "track", "telemetry",
    "events", "momentum", "scorecard", "attention", "fuse", "overlay",
    "export", "run",
}


def test_help_lists_every_subcommand():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for cmd in EXPECTED:
        assert cmd in result.output, f"`bb {cmd}` missing from --help"


def test_fixture_command_runs():
    result = runner.invoke(app, ["fixture"])
    assert result.exit_code == 0, result.output


#: Phase D (Pranav) subcommands whose bodies are implemented — see their own
#: acceptance tests (test_ingest.py, test_shots.py, test_calibrate.py,
#: test_track.py) instead of the generic "still a stub" check below.
IMPLEMENTED = {"ingest", "shots", "calibrate", "track", "overlay"}


def test_unimplemented_commands_exit_two_and_name_an_owner():
    for cmd, (phase, owner) in OWNERS.items():
        if cmd in IMPLEMENTED:
            continue
        result = runner.invoke(app, [cmd, "--fight-id", "fixture-001"])
        assert result.exit_code == 2, f"`bb {cmd}` should exit 2 until implemented"
        assert owner in result.output
        assert phase in result.output


def test_fights_command_sees_the_fixture():
    runner.invoke(app, ["fixture"])
    result = runner.invoke(app, ["fights"])
    assert result.exit_code == 0
    assert "fixture-001" in result.output
