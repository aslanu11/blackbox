"""A5 - owner: Aslan.

The ONLY place the Anthropic API is called from (spec 2.4). No inline API calls
anywhere else, ever.

Tiers: a fast model for classify_wide (yes/no on one thumbnail); a stronger
model for score_rubric and damage_assess (structured JSON).
Mandatory disk cache: key = SHA256(task_name + model + input bytes) ->
data/llm_cache/. Checked before every call; re-runs cost zero.
Budget guard: a running call counter, warn at 200, hard-confirm at 500.
Images are downsampled to 768 px on the longest edge before sending.
LLM_MOCK=1 returns deterministic fixtures for tests.

Done when
---------
Mock mode returns stable values, and a repeated live call hits the cache and
makes no network request.
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import sys
from pathlib import Path
from typing import Any

from . import schemas as S

__phase__ = "A5"
__owner__ = "Aslan"

# --------------------------------------------------------------------------
# Model tiers (spec 11). Change them here and nowhere else.
# --------------------------------------------------------------------------

#: Fast and cheap. One thumbnail, a yes/no answer, potentially thousands of calls.
MODEL_FAST = "claude-haiku-4-5"

#: Stronger. Judgment calls over several frames - the rubric and damage deltas.
MODEL_STRONG = "claude-opus-5"

#: Longest image edge in pixels before upload.
MAX_IMAGE_EDGE = 768

#: Budget guard thresholds.
WARN_AT_CALLS = 200
CONFIRM_AT_CALLS = 500

_COUNTER_PATH = S.LLM_CACHE_DIR / "_call_count.json"


def mock_mode() -> bool:
    """Tests and CI run here. Never touches the network."""
    return os.environ.get("LLM_MOCK", "0") == "1"


# --------------------------------------------------------------------------
# Cache
# --------------------------------------------------------------------------


def _cache_key(task: str, model: str, payload: bytes) -> str:
    h = hashlib.sha256()
    h.update(task.encode("utf-8"))
    h.update(b"\x00")
    h.update(model.encode("utf-8"))
    h.update(b"\x00")
    h.update(payload)
    return h.hexdigest()


def _cache_path(key: str) -> Path:
    return S.LLM_CACHE_DIR / f"{key}.json"


def _cache_get(key: str) -> Any | None:
    p = _cache_path(key)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))["result"]
    except (json.JSONDecodeError, KeyError):
        # A corrupt entry is not worth failing a pipeline over - drop and refetch.
        p.unlink(missing_ok=True)
        return None


def _cache_put(key: str, task: str, model: str, result: Any) -> None:
    S.LLM_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _cache_path(key).write_text(
        json.dumps({"task": task, "model": model, "result": result}, indent=2),
        encoding="utf-8",
    )


def cache_stats() -> dict[str, int]:
    """Entries on disk and calls actually made. Worth showing at the demo."""
    n = len(list(S.LLM_CACHE_DIR.glob("*.json"))) if S.LLM_CACHE_DIR.exists() else 0
    return {"cached_entries": max(n - 1, 0), "calls_made": call_count()}


# --------------------------------------------------------------------------
# Budget guard
# --------------------------------------------------------------------------


def call_count() -> int:
    if not _COUNTER_PATH.exists():
        return 0
    try:
        return int(json.loads(_COUNTER_PATH.read_text(encoding="utf-8"))["calls"])
    except (json.JSONDecodeError, KeyError, ValueError):
        return 0


def _bump_call_count() -> int:
    n = call_count() + 1
    S.LLM_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _COUNTER_PATH.write_text(json.dumps({"calls": n}), encoding="utf-8")
    return n


def _budget_guard() -> None:
    """Warn, then block, before a runaway loop drains the account."""
    n = call_count()
    if n >= CONFIRM_AT_CALLS:
        msg = f"LLM budget: {n} calls already made (limit {CONFIRM_AT_CALLS})."
        if not sys.stdin.isatty():
            raise RuntimeError(
                f"{msg} Refusing to continue non-interactively. "
                f"Delete {_COUNTER_PATH} to reset if this is intended."
            )
        if input(f"{msg} Continue? [y/N] ").strip().lower() not in ("y", "yes"):
            raise RuntimeError("Aborted at the LLM budget guard.")
    elif n >= WARN_AT_CALLS:
        print(f"  [llm] warning: {n} API calls made so far.", file=sys.stderr)


# --------------------------------------------------------------------------
# Images
# --------------------------------------------------------------------------


def _encode_image(path: str | Path) -> bytes:
    """Downsample to MAX_IMAGE_EDGE and return JPEG bytes."""
    from PIL import Image

    with Image.open(path) as im:
        im = im.convert("RGB")
        longest = max(im.size)
        if longest > MAX_IMAGE_EDGE:
            scale = MAX_IMAGE_EDGE / longest
            im = im.resize((round(im.width * scale), round(im.height * scale)), Image.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def _image_block(jpeg: bytes) -> dict:
    return {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": "image/jpeg",
            "data": base64.standard_b64encode(jpeg).decode("ascii"),
        },
    }


# --------------------------------------------------------------------------
# The single call path
# --------------------------------------------------------------------------


def _client():
    from anthropic import Anthropic

    return Anthropic()


def _strip_fence(text: str) -> str:
    """Tolerate a ```json fence even when we asked for raw JSON."""
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t
        t = t.rsplit("```", 1)[0]
    return t.strip()


def _call(
    *,
    task: str,
    model: str,
    system: str,
    content: list[dict],
    schema: dict,
    cache_payload: bytes,
    max_tokens: int = 2048,
) -> Any:
    """Cached, budget-guarded, schema-constrained request. The only network path."""
    key = _cache_key(task, model, cache_payload)
    hit = _cache_get(key)
    if hit is not None:
        return hit

    if mock_mode():
        raise RuntimeError(
            f"LLM_MOCK=1 but task {task!r} reached the network path. Add a mock branch."
        )

    _budget_guard()

    output_config: dict[str, Any] = {"format": {"type": "json_schema", "schema": schema}}
    # `effort` is an Opus/Sonnet control - Haiku 4.5 rejects it.
    if model != MODEL_FAST:
        output_config["effort"] = "medium"

    response = _client().messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system,
        output_config=output_config,
        messages=[{"role": "user", "content": content}],
    )
    _bump_call_count()

    if response.stop_reason == "refusal":
        raise RuntimeError(f"LLM refused task {task!r}: {response.stop_details}")

    text = "".join(b.text for b in response.content if b.type == "text")
    result = json.loads(_strip_fence(text))
    _cache_put(key, task, model, result)
    return result


def _mock(task: str, payload: bytes) -> Any:
    """Deterministic fixtures - the same input always gives the same answer."""
    seed = int(hashlib.sha256(task.encode() + payload).hexdigest()[:8], 16)
    if task == "classify_wide":
        # ~70% wide, roughly the real broadcast ratio.
        return {"wide": seed % 10 < 7}
    if task == "score_rubric":
        return {"damage": [3, 2], "aggression": [2, 1], "control": [2, 1], "reasoning": "mock"}
    if task == "damage_assess":
        return {"damage_delta": round((seed % 100) / 100.0, 2), "reasoning": "mock"}
    raise RuntimeError(f"no mock for task {task!r}")


# --------------------------------------------------------------------------
# Tasks
# --------------------------------------------------------------------------

_WIDE_SCHEMA = {
    "type": "object",
    "properties": {
        "wide": {
            "type": "boolean",
            "description": "True if this is a wide arena shot showing both robots and the floor.",
        }
    },
    "required": ["wide"],
    "additionalProperties": False,
}

_WIDE_SYSTEM = (
    "You classify single frames from BattleBots broadcast footage.\n"
    "A frame is WIDE when the camera shows the arena floor from above or from the "
    "side, far enough back that both robots and a usable stretch of floor are "
    "visible - the kind of shot you could track positions from.\n"
    "A frame is NOT wide when it is a close-up of one robot, a crowd or pit shot, "
    "a driver or commentator shot, a replay wipe, a graphic, or so motion-blurred "
    "that the floor is unreadable.\n"
    "Answer with the boolean only."
)


def classify_wide(image_path: str | Path) -> bool:
    """D2's primary path: is this shot usable for tracking? Cached per frame."""
    jpeg = _encode_image(image_path)
    if mock_mode():
        return bool(_mock("classify_wide", jpeg)["wide"])
    result = _call(
        task="classify_wide",
        model=MODEL_FAST,
        system=_WIDE_SYSTEM,
        content=[_image_block(jpeg), {"type": "text", "text": "Wide shot?"}],
        schema=_WIDE_SCHEMA,
        cache_payload=jpeg,
        max_tokens=256,
    )
    return bool(result["wide"])


_RUBRIC_SCHEMA = {
    "type": "object",
    "properties": {
        "damage": {
            "type": "array",
            "items": {"type": "integer"},
            "description": "Damage points as [bot_a, bot_b]. Must sum to exactly 5.",
        },
        "aggression": {
            "type": "array",
            "items": {"type": "integer"},
            "description": "Aggression points as [bot_a, bot_b]. Must sum to exactly 3.",
        },
        "control": {
            "type": "array",
            "items": {"type": "integer"},
            "description": "Control points as [bot_a, bot_b]. Must sum to exactly 3.",
        },
        "reasoning": {
            "type": "string",
            "description": "Two or three sentences justifying the split, citing what you saw.",
        },
    },
    "required": ["damage", "aggression", "control", "reasoning"],
    "additionalProperties": False,
}

_RUBRIC_SYSTEM = (
    "You are scoring a BattleBots judges' decision on the modern 11-point rubric:\n"
    "  Damage 5 points, Aggression 3 points, Control 3 points.\n"
    "Each category is split between the two robots and must sum to exactly its "
    "total - no points left unassigned.\n\n"
    "Damage: cumulative and match-ending damage. Weigh loss of weapon function, "
    "loss of mobility, and structural damage above cosmetic marks.\n"
    "Aggression: who initiated engagements, closed distance, and pressed the "
    "attack. Reward the robot forcing the fight, not the one surviving it.\n"
    "Control: who dictated where the fight happened - driving the opponent into "
    "hazards or walls, holding the centre, and imposing their own match strategy.\n\n"
    "You are shown keyframes sampled through the fight in chronological order. "
    "Score only what the frames support. Be decisive: a 3-2 damage split is a real "
    "verdict, not a hedge."
)


def score_rubric(frame_paths: list[str | Path], bots: list[str]) -> dict:
    """B4's cheap lane: rubric scores for a fight we never tracked.

    ``bots[0]`` is index 0 in every returned pair, matching FightMeta.bots order.
    """
    frames = [_encode_image(p) for p in frame_paths]
    payload = b"".join(frames) + "|".join(bots).encode("utf-8")
    if mock_mode():
        return _mock("score_rubric", payload)

    content: list[dict] = [
        {
            "type": "text",
            "text": (
                f"Fight: {bots[0]} (index 0) versus {bots[1]} (index 1).\n"
                f"{len(frames)} keyframes follow in chronological order. "
                f"Score the fight on the 11-point rubric."
            ),
        }
    ]
    for i, jpeg in enumerate(frames):
        content.append({"type": "text", "text": f"Frame {i + 1}:"})
        content.append(_image_block(jpeg))

    return _call(
        task="score_rubric",
        model=MODEL_STRONG,
        system=_RUBRIC_SYSTEM,
        content=content,
        schema=_RUBRIC_SCHEMA,
        cache_payload=payload,
        max_tokens=4096,
    )


_DAMAGE_SCHEMA = {
    "type": "object",
    "properties": {
        "damage_delta": {
            "type": "number",
            "description": "Visible damage sustained between the frames, 0.0 (none) to 1.0 (destroyed).",
        },
        "reasoning": {
            "type": "string",
            "description": "One or two sentences naming what changed.",
        },
    },
    "required": ["damage_delta", "reasoning"],
    "additionalProperties": False,
}

_DAMAGE_SYSTEM = (
    "You compare two frames of the same BattleBots robot, taken earlier and later "
    "in one fight, and judge how much visible damage it sustained in between.\n"
    "Count: missing or bent armour, a weapon that has stopped spinning or fallen "
    "off, a shed wheel, exposed internals, fire, and smoke.\n"
    "Do not count: scratches, scuffs, paint transfer, sparks, or debris that is "
    "clearly the opponent's.\n"
    "0.0 means untouched. 1.0 means functionally destroyed. Be conservative - "
    "camera angle and lighting change between frames and are not damage."
)


def damage_assess(before_path: str | Path, after_path: str | Path, bot: str) -> dict:
    """B4's full-telemetry lane: the damage half of the rubric, on the hero fights."""
    before = _encode_image(before_path)
    after = _encode_image(after_path)
    payload = before + after + bot.encode("utf-8")
    if mock_mode():
        return _mock("damage_assess", payload)

    return _call(
        task="damage_assess",
        model=MODEL_STRONG,
        system=_DAMAGE_SYSTEM,
        content=[
            {"type": "text", "text": f"Robot: {bot}. Earlier in the fight:"},
            _image_block(before),
            {"type": "text", "text": "Later in the fight:"},
            _image_block(after),
            {"type": "text", "text": "How much damage did it take in between?"},
        ],
        schema=_DAMAGE_SCHEMA,
        cache_payload=payload,
        max_tokens=2048,
    )
