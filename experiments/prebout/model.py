"""Pre-bout win-probability model — a second, independent lane.

blackbox/pipeline/momentum.py predicts P(bots[0] wins) *during* a fight, from
CV telemetry (control, hit differential, mobility). It needs tracking data,
so it only ever runs on hero fights.

This model predicts the same quantity *before* the fight, from roster data
(weapon class) and prior results (Elo, seeded from career win rate). It needs
no tracking data at all, so it can score every fight in the manifest —
including corpus and proleague fights momentum.py can never touch — which
makes it useful as an independent backtest baseline, not a replacement.

It reads two artifacts other modules own and never writes to them:
  - data/bots.csv        (blackbox/sources/specs.py, C4)
  - data/wiki/*_history.csv (blackbox/sources/wiki.py, C3)
Both are optional. Missing either degrades to a weaker prior, never a crash —
same "a number we didn't measure doesn't get drawn" rule the rest of the repo
follows (see README.md).
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path

from blackbox import schemas as S

RATING_DEFAULT = 1500.0
ELO_SCALE = 400.0

#: K-factor for established bots; larger while a bot has few recorded fights
#: (chess-style provisional rating) so early results move it quickly.
K_ESTABLISHED = 24.0
K_PROVISIONAL = 40.0
PROVISIONAL_GAMES = 10

#: Shrinkage for the one-time wiki win-rate seed: seed_shift maxes out at
#: +/-200 Elo and needs ~5 recorded fights before it means much.
HISTORY_PRIOR_MAX_SHIFT = 200.0
HISTORY_PRIOR_HALF_LIFE = 5.0

#: Shrinkage for the weapon-class matchup table: with zero same-pair fights
#: seen, matchup contributes nothing (falls back to 0.5); it needs
#: MATCHUP_BLEND_K same-pair fights before it counts as much as Elo.
MATCHUP_PRIOR_WINS = 2.0
MATCHUP_BLEND_K = 8.0


def _clip01(p: float, eps: float = 1e-6) -> float:
    return min(1.0 - eps, max(eps, p))


def load_roster(path: Path | None = None) -> dict[str, str]:
    """bot name (lowercased) -> weapon_class, from data/bots.csv. {} if absent."""
    path = path or (S.DATA_DIR / "bots.csv")
    if not path.exists():
        return {}
    out: dict[str, str] = {}
    with path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            name = (row.get("name") or "").strip().lower()
            cls = (row.get("weapon_class") or "other").strip() or "other"
            if name:
                out[name] = cls
    return out


def load_history(
    wiki_dir: Path | None = None,
    exclude_pairs: set[frozenset[str]] | None = None,
) -> dict[str, tuple[int, int]]:
    """bot name (lowercased) -> (wins, fights), aggregated from data/wiki/*_history.csv.

    A bot with no file, or a file with no parseable rows, is simply absent —
    callers treat that as "no prior", not zero wins.

    Two defensive filters, both load-bearing for backtest correctness:

    - Rows with no `method` are unplayed fixtures (round-robin groups list
      the whole schedule, including matches marked "TBD"), not losses. Fandom's
      own result text for a TBD row still fails `startswith("w")`, so
      wiki.py's `won` column reads False for a match that hasn't happened -
      counting that as a loss would be silently wrong, not just uninformative.
    - `exclude_pairs` drops rows matching a fight this history is about to be
      used to *predict*. Without this, seeding an Elo prior from a bot's full
      wiki history leaks that fight's own already-scraped result into its
      own pre-fight prediction the moment the fight has been played and the
      wiki page updated - which, for the current round-robin group, is
      immediately.
    """
    wiki_dir = wiki_dir or (S.DATA_DIR / "wiki")
    exclude_pairs = exclude_pairs or set()
    out: dict[str, tuple[int, int]] = {}
    if not wiki_dir.exists():
        return out
    for csv_path in wiki_dir.glob("*_history.csv"):
        wins = fights = 0
        with csv_path.open(newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                bot = (row.get("bot") or "").strip().lower()
                opponent = (row.get("opponent") or "").strip().lower()
                if not bot or not (row.get("method") or "").strip():
                    continue  # no bot name, or an unplayed fixture
                if opponent and frozenset((bot, opponent)) in exclude_pairs:
                    continue
                fights += 1
                if str(row.get("won", "")).strip().lower() in ("true", "1", "yes"):
                    wins += 1
        if fights and bot:
            prev_w, prev_f = out.get(bot, (0, 0))
            out[bot] = (prev_w + wins, prev_f + fights)
    return out


@dataclass
class PreboutModel:
    """Sequential Elo + weapon-matchup predictor.

    Call `predict(a, b)` for a pre-fight P(a wins), then `update(a, b, winner)`
    once the result is known. Never call update before predict for the same
    fight — that would be leaking the answer into its own prediction, which is
    the one thing a walk-forward backtest must not do.
    """

    weapon_class: dict[str, str] = field(default_factory=dict)
    ratings: dict[str, float] = field(default_factory=dict)
    games_played: dict[str, int] = field(default_factory=dict)
    #: (class_a, class_b) -> (wins_for_a, n). Both directions of a pair are
    #: tracked independently so the table stays a plain win-rate lookup.
    matchup: dict[tuple[str, str], list[float]] = field(default_factory=dict)

    @classmethod
    def seeded(cls, roster: dict[str, str] | None = None, history: dict[str, tuple[int, int]] | None = None) -> "PreboutModel":
        roster = roster or {}
        history = history or {}
        m = cls(weapon_class=dict(roster))
        for bot, (wins, fights) in history.items():
            if fights <= 0:
                continue
            win_rate = wins / fights
            shrink = fights / (fights + HISTORY_PRIOR_HALF_LIFE)
            m.ratings[bot] = RATING_DEFAULT + 2 * HISTORY_PRIOR_MAX_SHIFT * (win_rate - 0.5) * shrink
        return m

    def _rating(self, bot: str) -> float:
        return self.ratings.get(bot.lower(), RATING_DEFAULT)

    def _cls(self, bot: str) -> str:
        return self.weapon_class.get(bot.lower(), "other")

    def _elo_p(self, a: str, b: str) -> float:
        diff = self._rating(a) - self._rating(b)
        return 1.0 / (1.0 + 10 ** (-diff / ELO_SCALE))

    def _matchup_p(self, a: str, b: str) -> tuple[float, float]:
        """(P(a wins) from the matchup table, weight to give it)."""
        key = (self._cls(a), self._cls(b))
        wins, n = self.matchup.get(key, [0.0, 0.0])
        p = (wins + MATCHUP_PRIOR_WINS) / (n + 2 * MATCHUP_PRIOR_WINS)
        weight = n / (n + MATCHUP_BLEND_K)
        return p, weight

    def predict(self, a: str, b: str) -> float:
        """P(a wins) before the fight. Read-only — call `update` separately."""
        elo_p = self._elo_p(a, b)
        matchup_p, w = self._matchup_p(a, b)
        return _clip01((1 - w) * elo_p + w * matchup_p)

    def update(self, a: str, b: str, winner: str) -> None:
        """Advance Elo ratings and the matchup table by one known result."""
        outcome_a = 1.0 if winner == a else 0.0
        elo_p = self._elo_p(a, b)

        for bot, outcome, opp_p in ((a, outcome_a, elo_p), (b, 1 - outcome_a, 1 - elo_p)):
            key = bot.lower()
            games = self.games_played.get(key, 0)
            k = K_PROVISIONAL if games < PROVISIONAL_GAMES else K_ESTABLISHED
            self.ratings[key] = self._rating(bot) + k * (outcome - opp_p)
            self.games_played[key] = games + 1

        key_ab = (self._cls(a), self._cls(b))
        key_ba = (self._cls(b), self._cls(a))
        wins_ab, n_ab = self.matchup.get(key_ab, [0.0, 0.0])
        self.matchup[key_ab] = [wins_ab + outcome_a, n_ab + 1]
        wins_ba, n_ba = self.matchup.get(key_ba, [0.0, 0.0])
        self.matchup[key_ba] = [wins_ba + (1 - outcome_a), n_ba + 1]
