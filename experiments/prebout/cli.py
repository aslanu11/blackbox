"""Standalone entry point for the pre-bout backtest experiment.

Deliberately not wired into `bb` (blackbox/cli.py) - this whole experiment
lives outside the owned pipeline split in TEAM.md, so it gets its own
command instead of a shared file edit:

    python -m experiments.prebout.cli backtest
    python -m experiments.prebout.cli fetch-roster
    python -m experiments.prebout.cli fetch-history

fetch-roster/fetch-history call blackbox.sources.specs/wiki directly (the
same functions `bb` will call once C4/C3 are wired up) - they write the
canonical data/bots.csv and data/wiki/*.csv artifacts, they just aren't
triggered through the `bb` CLI yet. Network calls go through blackbox.net,
so BRIGHTDATA_API_TOKEN in your local .env is picked up automatically if
set, and everything degrades to plain httpx if it isn't. Nothing here needs
a network call at all if those two files already exist - `backtest` just
reads whatever's on disk.
"""

from __future__ import annotations

import argparse
import json
import sys

import yaml

from blackbox import net, schemas as S
from blackbox.sources import specs, wiki

from . import backtest


def _manifest_bots() -> list[str]:
    data = yaml.safe_load(S.MANIFEST_PATH.read_text(encoding="utf-8"))
    names: set[str] = set()
    for fight in data.get("fights", []):
        names.update(fight.get("bots", []))
    return sorted(names)


def cmd_backtest(args: argparse.Namespace) -> None:
    report = backtest.run()
    print(json.dumps(report, indent=2))
    if report.get("status") == "insufficient_data":
        print("\nNo scored fights yet - see the note above.", file=sys.stderr)


def cmd_fetch_roster(args: argparse.Namespace) -> None:
    out = specs.roster()
    print(f"wrote {out}")


def cmd_fetch_history(args: argparse.Namespace) -> None:
    bots = args.bots or _manifest_bots()
    for bot in bots:
        try:
            out = wiki.bot_history(bot)
            print(f"{bot}: {out}")
        except (net.httpx.HTTPError, ValueError) as exc:
            print(f"{bot}: skipped ({exc})", file=sys.stderr)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="prebout")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("backtest", help="Run the walk-forward pre-bout backtest.").set_defaults(func=cmd_backtest)

    p_roster = sub.add_parser("fetch-roster", help="Scrape battlebots.com/robots/ -> data/bots.csv.")
    p_roster.set_defaults(func=cmd_fetch_roster)

    p_hist = sub.add_parser("fetch-history", help="Scrape fandom fight-history tables -> data/wiki/.")
    p_hist.add_argument("bots", nargs="*", help="Bot names (default: every bot in data/manifest.yaml).")
    p_hist.set_defaults(func=cmd_fetch_history)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
