"""A5 — owner: Aslan.

The ONLY place the Anthropic API is called from (spec 2.4). No inline API calls
anywhere else, ever.

Tiers: a fast model for classify_wide (yes/no on one thumbnail); a stronger
model for score_rubric and damage_assess (structured JSON via tool use).
Mandatory disk cache: key = SHA256(task_name + model + input bytes) ->
data/llm_cache/. Check it before every call; re-runs must cost zero.
Budget guard: log a running call counter, warn at 200, hard-confirm at 500.
Downsample images to 768 px on the longest edge before sending.
LLM_MOCK=1 returns deterministic fixtures for tests.

Done when
---------
Mock mode returns stable values, and a repeated live call hits the cache and
makes no network request.
"""

from __future__ import annotations

from pathlib import Path  # noqa: F401

__phase__ = "A5"
__owner__ = "Aslan"


def classify_wide(image_path: str) -> bool:
    raise NotImplementedError(
        "A5 is not implemented yet — owner: Aslan. See this module's docstring."
    )
