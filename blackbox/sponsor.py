"""S1 — owner: Pranav. Sponsorship signal.

Answers one question a sponsor actually asks: **which robot buys me the most
attention per pound?** Not "who wins" — who is on screen during the seconds
audiences rewind and rewatch, and who *causes* those seconds.

This module is deliberately standalone. It reads only §5 contract artifacts
(``meta.json``, ``attention.json``, ``events.json``, ``tracks.json``) plus
optional Bright Data roster enrichment, and writes one new artifact,
``data/processed/sponsor_index.json``. It defines its own models here rather
than widening ``schemas.py``, which is frozen (TEAM.md). Nothing in Aslan's
lane is imported for mutation — ``net.fetch`` is consumed read-only.

The score (0-100), attention-weighted by design
-----------------------------------------------
``SPOTLIGHT`` (w=0.45)
    Critical-moment airtime. Seconds of this bot's fights whose most-replayed
    value clears the league-wide critical threshold, scaled by how hot those
    seconds ran. This is the "most watched / most replayed" term and it is the
    heaviest single component.

``AUTHORSHIP`` (w=0.30)
    Did the bot *cause* the rewatched moment, or merely stand in it? Credit for
    each hit/KO is the attention value at that instant times the event's
    magnitude, split between actor and target. A bot that lands the hits people
    rewind scores here; a punching bag does not.

``PERFORMANCE`` (w=0.25)
    Win rate with a KO premium. Sponsors like winners, but a spectacular loser
    outsells a boring winner — hence the smallest weight.

Attention terms therefore carry 0.75 of the score, per the brief's "priority to
most replayed and most watched".

Three corrections this module makes deliberately
------------------------------------------------
1. **Adaptive event window.** YouTube ships exactly 100 heatmap buckets per
   video, so a 22-minute episode has ~13 s buckets. A fixed +/-5 s lift window
   is *narrower than one bucket* and silently finds nothing for ~20% of events.
   ``_lift_window`` derives the window from the observed bucket spacing instead,
   so no event is dropped without being counted as unmeasured.
2. **Episode-relative attention, not ratio-to-local-baseline.** yt-dlp's heatmap
   is already normalised to the episode peak, so the raw values are directly
   comparable between fights of the same episode. Dividing by a fight-local 20th
   percentile — which can be near zero for a fight sitting in a quiet stretch —
   inflates quiet fights enormously. We use the normalised values as they come.
3. **Confidence is explicit.** A bot scored without CV events cannot have a real
   authorship term. Rather than quietly scoring it as average, every row carries
   ``confidence`` and ``basis``. A number we didn't measure doesn't get drawn —
   the same rule the README applies to coverage.

Done when
---------
``python -m blackbox.sponsor`` writes ``sponsor_index.json`` for every processed
fight, and the fixture's KO winner outranks its victim.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

import numpy as np
from pydantic import BaseModel, ConfigDict, Field

from . import schemas as S

__phase__ = "S1"
__owner__ = "Pranav"

# --------------------------------------------------------------------------
# Tunables — every one of these is a judgment call, so it lives here in the open
# --------------------------------------------------------------------------

#: Component weights. Attention-derived terms sum to 0.75 by design.
W_SPOTLIGHT = 0.45
W_AUTHORSHIP = 0.30
W_PERFORMANCE = 0.25

#: A moment is "critical" if its episode-normalised attention sits at or above
#: this quantile of every attention point we have league-wide. Pooling across
#: fights keeps the threshold consistent between bots.
CRITICAL_QUANTILE = 0.70

#: Winning by KO is worth this much of a bonus over a decision win.
KO_PREMIUM = 0.25

#: An event's attention window is at least this wide, and at least this many
#: heatmap buckets wide — whichever is larger. See correction (1) above.
MIN_WINDOW_S = 5.0
WINDOW_BUCKETS = 1.5

#: Bright Data Data Collector that returns the battlebots.com roster as
#: structured JSON. Overridable so a fresh collector id needs no code change.
DEFAULT_COLLECTOR = "c_ms4yfrun1dayux9o7y"
DCA_TRIGGER = "https://api.brightdata.com/dca/trigger"
DCA_DATASET = "https://api.brightdata.com/dca/dataset"
ROSTER_CACHE = S.DATA_DIR / "brightdata" / "roster.json"

SPONSOR_INDEX_PATH = S.PROCESSED_DIR / "sponsor_index.json"


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SponsorComponents(_Model):
    """The three terms, each already normalised to 0-1 across the league."""

    spotlight: float = 0.0
    authorship: float = 0.0
    performance: float = 0.0


class SponsorRow(_Model):
    name: str
    #: 0-100. The headline number.
    sponsor_score: float = 0.0
    components: SponsorComponents = Field(default_factory=SponsorComponents)
    #: Seconds of critical-moment airtime, before normalisation. Sponsor-legible.
    critical_seconds: float = 0.0
    #: Mean most-replayed value across this bot's critical seconds, 0-1.
    peak_attention: float = 0.0
    fights: int = 0
    record: str | None = None
    #: 0-1. Drops when a bot's fights lack CV events or attention entirely.
    confidence: float = 0.0
    #: Which artifacts actually backed this row, e.g. ["attention", "events"].
    basis: list[str] = Field(default_factory=list)
    #: Bright Data roster enrichment, when the collector has this bot.
    weapon_class: str | None = None
    team_name: str | None = None
    social_urls: list[str] = Field(default_factory=list)


class SponsorIndex(_Model):
    #: Absolute attention value at/above which a moment counts as critical.
    critical_threshold: float = 0.0
    #: Fight ids that contributed at least one attention point.
    fights_scored: list[str] = Field(default_factory=list)
    #: Fights skipped for want of attention data, so the gap is visible.
    fights_missing_attention: list[str] = Field(default_factory=list)
    weights: dict[str, float] = Field(default_factory=dict)
    bots: list[SponsorRow] = Field(default_factory=list)


# --------------------------------------------------------------------------
# Bright Data — roster enrichment
# --------------------------------------------------------------------------


def _token() -> str | None:
    # net.py already load_dotenv()s the repo .env at import; importing it here
    # is enough to populate os.environ without duplicating that logic.
    from . import net  # noqa: F401

    return os.environ.get("BRIGHTDATA_API_TOKEN") or None


def _merge_roster(existing: list[dict], incoming: list[dict]) -> list[dict]:
    """Union two collector runs by robot name, newest record winning.

    The collector returns a *different subset* of the roster on each run — 7
    robots one call, 14 the next, overlapping only partially. Overwriting the
    cache would therefore lose bots we had already resolved. Accumulating means
    coverage only ever improves, and `--refresh-roster` can be run repeatedly to
    fill the roster in.
    """
    merged = {str(r.get("robot_name", "")).strip().lower(): r for r in existing if r.get("robot_name")}
    for row in incoming:
        name = str(row.get("robot_name", "")).strip().lower()
        if name:
            merged[name] = row
    return sorted(merged.values(), key=lambda r: str(r.get("robot_name", "")))


def fetch_roster(force: bool = False, timeout_s: float = 420.0) -> list[dict]:
    """Bright Data Data Collector -> battlebots.com roster as structured JSON.

    Cached to disk and *accumulated* across runs (see ``_merge_roster``); a
    second call costs nothing. Returns ``[]`` when no token is configured, so
    the whole module still runs offline on the fixture.

    Prefer this over scraping the roster HTML: the collector returns typed
    fields, and it kept serving data on 2026-07-28 while battlebots.com itself
    was returning "Error establishing a database connection".
    """
    cached: list[dict] = []
    if ROSTER_CACHE.exists():
        cached = json.loads(ROSTER_CACHE.read_text(encoding="utf-8"))
        if not force:
            return cached

    token = _token()
    if not token:
        return cached

    import httpx

    collector = os.environ.get("BRIGHTDATA_SPECS_COLLECTOR", DEFAULT_COLLECTOR)
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    trigger = httpx.post(
        DCA_TRIGGER,
        headers=headers,
        params={"collector": collector, "queue_next": "1"},
        json=[{"url": "https://battlebots.com/robots/"}],
        timeout=60.0,
    )
    trigger.raise_for_status()
    collection_id = trigger.json().get("collection_id")
    if not collection_id:
        return cached

    # The collector runs asynchronously; 202 means "still collecting".
    deadline = time.time() + timeout_s
    rows: list[dict] = []
    while time.time() < deadline:
        resp = httpx.get(DCA_DATASET, headers=headers, params={"id": collection_id}, timeout=60.0)
        if resp.status_code == 200 and resp.text.strip() not in ("", "[]"):
            rows = resp.json()
            break
        time.sleep(8.0)

    if not rows:
        return cached

    merged = _merge_roster(cached, rows)
    ROSTER_CACHE.parent.mkdir(parents=True, exist_ok=True)
    ROSTER_CACHE.write_text(
        json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return merged


def _roster_by_name(rows: list[dict]) -> dict[str, dict]:
    return {str(r.get("robot_name", "")).strip().lower(): r for r in rows if r.get("robot_name")}


# --------------------------------------------------------------------------
# Attention helpers
# --------------------------------------------------------------------------


def _lift_window(ts: np.ndarray) -> float:
    """Half-width of the window used to read attention around an event.

    YouTube gives 100 buckets per video regardless of length, so bucket spacing
    scales with episode duration. A window narrower than the spacing finds
    nothing. Always at least MIN_WINDOW_S so the fixture (1.5 s spacing) keeps a
    sane window rather than collapsing to near-zero.
    """
    if len(ts) < 2:
        return MIN_WINDOW_S
    spacing = float(np.median(np.diff(np.sort(ts))))
    return max(MIN_WINDOW_S, WINDOW_BUCKETS * spacing)


def _attention_at(ts: np.ndarray, vals: np.ndarray, t: float, half_width: float) -> float | None:
    """Mean attention within +/-half_width of t, or None if genuinely unmeasured."""
    window = vals[np.abs(ts - t) <= half_width]
    if len(window) == 0:
        return None
    return float(window.mean())


def _bucket_seconds(ts: np.ndarray, duration_s: float | None) -> float:
    """How many seconds each attention point represents."""
    if len(ts) >= 2:
        return float(np.median(np.diff(np.sort(ts))))
    return float(duration_s) if duration_s else 0.0


def _load_attention_points(fight_id: str) -> tuple[np.ndarray, np.ndarray] | None:
    if not S.exists(fight_id, "attention"):
        return None
    attention = S.load_attention(fight_id)
    if not attention.points:
        return None
    pts = np.asarray(attention.points, dtype=float)
    return pts[:, 0], pts[:, 1]


# --------------------------------------------------------------------------
# Per-fight accumulation
# --------------------------------------------------------------------------


def _accumulate_fight(
    fight_id: str,
    threshold: float,
    acc: dict[str, dict[str, Any]],
) -> bool:
    """Fold one fight into the per-bot accumulator. True if it contributed."""
    if not S.exists(fight_id, "meta"):
        return False
    meta = S.load_meta(fight_id)
    loaded = _load_attention_points(fight_id)
    if loaded is None:
        return False
    ts, vals = loaded

    per_point_s = _bucket_seconds(ts, meta.video.duration_s)
    critical = vals >= threshold
    critical_seconds = float(critical.sum()) * per_point_s
    peak_attention = float(vals[critical].mean()) if critical.any() else 0.0

    # Both bots share the wide shot, so both bank the same critical airtime.
    # Authorship is what separates them.
    for bot in meta.bots:
        entry = acc.setdefault(
            bot,
            {
                "critical_seconds": 0.0,
                "peak_sum": 0.0,
                "peak_n": 0,
                "fights": 0,
                "wins": 0,
                "losses": 0,
                "kos": 0,
                "credit": 0.0,
                "basis": set(),
            },
        )
        entry["fights"] += 1
        entry["critical_seconds"] += critical_seconds
        if peak_attention > 0:
            entry["peak_sum"] += peak_attention
            entry["peak_n"] += 1
        entry["basis"].add("attention")

        if meta.result.winner == bot:
            entry["wins"] += 1
            if meta.result.method == "ko":
                entry["kos"] += 1
        elif meta.result.winner is not None:
            entry["losses"] += 1

    _accumulate_authorship(fight_id, meta, ts, vals, acc)
    return True


def _accumulate_authorship(
    fight_id: str,
    meta: S.FightMeta,
    ts: np.ndarray,
    vals: np.ndarray,
    acc: dict[str, dict[str, Any]],
) -> None:
    """Attention-weighted credit for causing the moments people rewatch."""
    if not S.exists(fight_id, "events"):
        return
    events = S.load_events(fight_id)
    if not events.events:
        return

    half_width = _lift_window(ts)
    for event in events.events:
        attention = _attention_at(ts, vals, event.t, half_width)
        if attention is None:
            # Genuinely unmeasured — the honest move is to skip, not to guess.
            continue
        magnitude = float(event.magnitude) if event.magnitude else 1.0
        weight = attention * magnitude

        # The bot landing the blow earns most of the credit; the one absorbing
        # it earns a little, because taking a spectacular hit is also content.
        if event.actor and event.actor in acc:
            acc[event.actor]["credit"] += weight
            acc[event.actor]["basis"].add("events")
        if event.target and event.target in acc:
            acc[event.target]["credit"] += weight * 0.25
            acc[event.target]["basis"].add("events")


# --------------------------------------------------------------------------
# Scoring
# --------------------------------------------------------------------------


def _normalise(values: dict[str, float]) -> dict[str, float]:
    """Scale to 0-1 by the observed maximum. All-zero stays all-zero."""
    peak = max(values.values(), default=0.0)
    if peak <= 0:
        return {k: 0.0 for k in values}
    return {k: v / peak for k, v in values.items()}


def _critical_threshold(fight_ids: list[str]) -> tuple[float, list[str], list[str]]:
    """Pool every attention point we have and take one league-wide threshold."""
    pooled: list[float] = []
    scored: list[str] = []
    missing: list[str] = []
    for fid in fight_ids:
        loaded = _load_attention_points(fid)
        if loaded is None:
            missing.append(fid)
            continue
        pooled.extend(loaded[1].tolist())
        scored.append(fid)
    if not pooled:
        return 0.0, scored, missing
    return float(np.quantile(pooled, CRITICAL_QUANTILE)), scored, missing


def build_index(fight_ids: list[str] | None = None, enrich: bool = True) -> SponsorIndex:
    """Compute the sponsorship index across every processed fight."""
    fight_ids = fight_ids if fight_ids is not None else S.list_fights()
    threshold, scored, missing = _critical_threshold(fight_ids)

    acc: dict[str, dict[str, Any]] = {}
    for fid in scored:
        _accumulate_fight(fid, threshold, acc)

    if not acc:
        return SponsorIndex(
            critical_threshold=round(threshold, 4),
            fights_scored=scored,
            fights_missing_attention=missing,
            weights=_weights(),
            bots=[],
        )

    spotlight_raw = {
        name: e["critical_seconds"] * (e["peak_sum"] / e["peak_n"] if e["peak_n"] else 0.0)
        for name, e in acc.items()
    }
    authorship_raw = {name: e["credit"] for name, e in acc.items()}
    performance_raw = {}
    for name, e in acc.items():
        decided = e["wins"] + e["losses"]
        win_rate = e["wins"] / decided if decided else 0.0
        ko_rate = e["kos"] / decided if decided else 0.0
        performance_raw[name] = win_rate * (1.0 + KO_PREMIUM * ko_rate)

    spotlight = _normalise(spotlight_raw)
    authorship = _normalise(authorship_raw)
    performance = _normalise(performance_raw)

    roster = _roster_by_name(fetch_roster()) if enrich else {}

    rows: list[SponsorRow] = []
    for name, e in acc.items():
        components = SponsorComponents(
            spotlight=round(spotlight[name], 4),
            authorship=round(authorship[name], 4),
            performance=round(performance[name], 4),
        )
        score = (
            W_SPOTLIGHT * components.spotlight
            + W_AUTHORSHIP * components.authorship
            + W_PERFORMANCE * components.performance
        ) * 100.0

        basis = sorted(e["basis"])
        # Authorship is the term that needs CV output. Without it we are scoring
        # on airtime and results alone, and the row should say so.
        confidence = 1.0 if "events" in basis else 0.6
        if not e["peak_n"]:
            confidence *= 0.5

        info = roster.get(name.strip().lower(), {})
        rows.append(
            SponsorRow(
                name=name,
                sponsor_score=round(score, 2),
                components=components,
                critical_seconds=round(e["critical_seconds"], 1),
                peak_attention=round(e["peak_sum"] / e["peak_n"], 4) if e["peak_n"] else 0.0,
                fights=e["fights"],
                record=f"{e['wins']}-{e['losses']}",
                confidence=round(confidence, 2),
                basis=basis,
                weapon_class=info.get("robot_type"),
                team_name=info.get("team_name"),
                social_urls=list(info.get("website_urls") or []),
            )
        )

    rows.sort(key=lambda r: r.sponsor_score, reverse=True)
    return SponsorIndex(
        critical_threshold=round(threshold, 4),
        fights_scored=scored,
        fights_missing_attention=missing,
        weights=_weights(),
        bots=rows,
    )


def _weights() -> dict[str, float]:
    return {
        "spotlight": W_SPOTLIGHT,
        "authorship": W_AUTHORSHIP,
        "performance": W_PERFORMANCE,
    }


def save_index(index: SponsorIndex) -> Path:
    SPONSOR_INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    SPONSOR_INDEX_PATH.write_text(
        json.dumps(index.model_dump(mode="json"), indent=2) + "\n", encoding="utf-8"
    )
    return SPONSOR_INDEX_PATH


def load_index() -> SponsorIndex:
    if not SPONSOR_INDEX_PATH.exists():
        raise FileNotFoundError(
            f"{SPONSOR_INDEX_PATH} not found. Run `python -m blackbox.sponsor` first."
        )
    return SponsorIndex.model_validate_json(SPONSOR_INDEX_PATH.read_text(encoding="utf-8"))


def compute(enrich: bool = True) -> Path:
    """Build and persist the sponsorship index. The one call worth importing."""
    return save_index(build_index(enrich=enrich))


# --------------------------------------------------------------------------
# Standalone entry point
# --------------------------------------------------------------------------
#
# Deliberately NOT wired into blackbox/cli.py: that file is shared and Aslan is
# committing to it. To expose this as `bb sponsor`, add to cli.py:
#
#     @app.command()
#     def sponsor(enrich: bool = True) -> None:
#         """S1 - sponsorship attractiveness index -> sponsor_index.json."""
#         from . import sponsor as mod
#         typer.echo(f"  sponsor   -> {mod.compute(enrich=enrich)}")


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        prog="python -m blackbox.sponsor",
        description="Sponsorship attractiveness index from most-replayed attention + performance.",
    )
    parser.add_argument(
        "--no-enrich",
        action="store_true",
        help="Skip the Bright Data roster lookup (offline / faster).",
    )
    parser.add_argument(
        "--refresh-roster",
        action="store_true",
        help="Force a fresh Bright Data collector run instead of the disk cache.",
    )
    args = parser.parse_args(argv)

    if args.refresh_roster:
        rows = fetch_roster(force=True)
        print(f"  roster    -> {len(rows)} robots via Bright Data")

    index = build_index(enrich=not args.no_enrich)
    path = save_index(index)

    print(f"  critical threshold {index.critical_threshold:.4f} "
          f"({len(index.fights_scored)} fights scored, "
          f"{len(index.fights_missing_attention)} without attention)")
    print(f"  {'BOT':<16}{'SCORE':>7}{'SPOT':>7}{'AUTH':>7}{'PERF':>7}{'CRIT s':>9}{'CONF':>7}")
    for row in index.bots:
        c = row.components
        print(
            f"  {row.name[:15]:<16}{row.sponsor_score:>7.1f}{c.spotlight:>7.2f}"
            f"{c.authorship:>7.2f}{c.performance:>7.2f}{row.critical_seconds:>9.1f}"
            f"{row.confidence:>7.2f}"
        )
    print(f"  sponsor   -> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
