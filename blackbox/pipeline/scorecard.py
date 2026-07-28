"""B4 — owner: Aslan.

The modern BattleBots rubric, 11 points: Damage 5, Aggression 3, Control 3.

Mode (a) full-telemetry, for hero fights:
    damage     <- opponent mobility decay + LLM damage delta
    aggression <- approach-initiation rate share
    control    <- integral of control(t)
Mode (b) cheap-lane, for corpus fights with no tracking:
    per-minute keyframes -> llm.score_rubric(frames) structured scores

robbery_score = the disagreement margin vs the official verdict, 0 if we agree.
`bb scorecard --leaderboard` aggregates the Robbery Leaderboard to CSV + JSON.

Done when
---------
Runs in both modes; the mock-LLM test passes; the leaderboard sorts correctly.
"""

from __future__ import annotations

from pathlib import Path  # noqa: F401

__phase__ = "B4"
__owner__ = "Aslan"


def score(fight_id: str) -> Path:
    raise NotImplementedError(
        "B4 is not implemented yet — owner: Aslan. See this module's docstring."
    )
