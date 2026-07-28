"""Data contracts — THE SINGLE SOURCE OF TRUTH (spec §5).

Producers write these files into ``data/processed/<fight_id>/``; consumers read
only these files. No module reaches into another module's internals.

Changing any shape in this file is a data-contract change and requires human
sign-off (spec §9.6). If you are a coding agent: do not widen, narrow, or
rename a field here to make your own module pass. Fix your module.

Conventions
-----------
* Floor coordinates are metres. The BattleBox floor is 48 ft x 48 ft, modelled
  as ``FLOOR_M`` x ``FLOOR_M`` with the origin at one corner.
* ``t`` is seconds from the fight-clip start, float (not episode time).
* Series are ``[t, value]`` pairs resampled to 1 Hz.
* Gaps are explicit. A non-wide frame is present with ``pos=None``. Never
  interpolate across a shot boundary.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# --------------------------------------------------------------------------
# Constants
# --------------------------------------------------------------------------

#: BattleBox floor edge length in metres (48 ft).
FLOOR_M: float = 14.63

#: Repo root, resolved from this file's location.
ROOT: Path = Path(__file__).resolve().parent.parent

DATA_DIR: Path = ROOT / "data"
RAW_DIR: Path = DATA_DIR / "raw"
FRAMES_DIR: Path = DATA_DIR / "frames"
PROCESSED_DIR: Path = DATA_DIR / "processed"
LLM_CACHE_DIR: Path = DATA_DIR / "llm_cache"
MANIFEST_PATH: Path = DATA_DIR / "manifest.yaml"

Role = Literal["hero", "corpus", "proleague"]
Method = Literal["ko", "jd"]
EventType = Literal["hit", "ko", "hazard"]

#: Weapon taxonomy for data/bots.csv (spec §C4).
WEAPON_CLASSES = (
    "vertical_spinner",
    "horizontal_spinner",
    "drum",
    "flipper",
    "hammer",
    "crusher",
    "control",
    "other",
)


class _Model(BaseModel):
    """Base: reject unknown fields so contract drift fails loudly."""

    model_config = ConfigDict(extra="forbid")


# --------------------------------------------------------------------------
# FightMeta
# --------------------------------------------------------------------------


class FightResult(_Model):
    winner: str | None = None
    #: ``None`` means unaired / result unknown.
    method: Method | None = None
    time_s: float | None = None


class VideoRef(_Model):
    yt_id: str | None = None
    #: Offsets into the *episode* video that bound this fight.
    fight_start_s: float | None = None
    fight_end_s: float | None = None

    @property
    def duration_s(self) -> float | None:
        if self.fight_start_s is None or self.fight_end_s is None:
            return None
        return self.fight_end_s - self.fight_start_s


class FightMeta(_Model):
    fight_id: str
    episode: int | None = None
    #: Order matters. ``bots[0]`` is the reference bot for momentum/control sign.
    bots: list[str]
    #: Hex colours, one per bot name. Drives overlay + frontend bot identity.
    colors: dict[str, str] = Field(default_factory=dict)
    result: FightResult = Field(default_factory=FightResult)
    video: VideoRef = Field(default_factory=VideoRef)
    role: Role = "proleague"


# --------------------------------------------------------------------------
# tracks.json
# --------------------------------------------------------------------------


class TrackFrame(_Model):
    t: float
    wide: bool
    #: ``None`` on non-wide frames. Bot name -> [x_m, y_m].
    pos: dict[str, list[float]] | None = None


class Tracks(_Model):
    fight_id: str
    fps: int = 10
    #: Fraction of frames that are wide *and* successfully tracked.
    coverage: float = 0.0
    frames: list[TrackFrame] = Field(default_factory=list)


# --------------------------------------------------------------------------
# events.json
# --------------------------------------------------------------------------


class Event(_Model):
    t: float
    type: EventType
    magnitude: float | None = None
    actor: str | None = None
    target: str | None = None


class Events(_Model):
    fight_id: str
    events: list[Event] = Field(default_factory=list)


# --------------------------------------------------------------------------
# telemetry.json
# --------------------------------------------------------------------------

Series = list[list[float]]  # [[t, value], ...]


class TelemetrySeries(_Model):
    #: P(bots[0] wins), 0-1.
    momentum: Series = Field(default_factory=list)
    #: [-1, 1]; positive favours bots[0].
    control: Series = Field(default_factory=list)
    #: Bot name -> series, metres/second.
    speed: dict[str, Series] = Field(default_factory=dict)
    #: Bot name -> series, 0-1 index vs that bot's own first-60s baseline.
    mobility: dict[str, Series] = Field(default_factory=dict)


class Telemetry(_Model):
    fight_id: str
    series: TelemetrySeries = Field(default_factory=TelemetrySeries)
    #: Bot name -> PNG filename, relative to the fight's processed dir.
    heatmap_png: dict[str, str] = Field(default_factory=dict)


# --------------------------------------------------------------------------
# attention.json
# --------------------------------------------------------------------------


class AttentionStats(_Model):
    baseline: float = 0.0
    peak: float = 0.0
    peak_t: float = 0.0


class EventLift(_Model):
    event_t: float
    type: EventType
    #: Mean attention in a +/-5 s window divided by the fight baseline.
    lift: float


class Attention(_Model):
    video_id: str | None = None
    fight_id: str
    #: Fight-local ``[t, value]``; value normalised 0-1.
    points: Series = Field(default_factory=list)
    stats: AttentionStats = Field(default_factory=AttentionStats)
    event_lift: list[EventLift] = Field(default_factory=list)


# --------------------------------------------------------------------------
# scorecard.json
# --------------------------------------------------------------------------


class RubricScores(_Model):
    """Modern BattleBots rubric, 11 points: Damage 5, Aggression 3, Control 3.

    Each field is ``[points_for_bots[0], points_for_bots[1]]``.
    """

    damage: list[int]
    aggression: list[int]
    control: list[int]
    #: "A" == bots[0], "B" == bots[1].
    winner: Literal["A", "B"]
    #: Normalised margin of victory under our rubric, 0-1.
    margin: float


class OfficialVerdict(_Model):
    winner: Literal["A", "B"] | None = None
    #: e.g. "2-1", "3-0", or None for a KO.
    split: str | None = None


class Scorecard(_Model):
    fight_id: str
    ours: RubricScores
    official: OfficialVerdict = Field(default_factory=OfficialVerdict)
    #: 0.0 when we agree with the officials; otherwise the disagreement margin.
    robbery_score: float = 0.0


# --------------------------------------------------------------------------
# media_value.json (league-wide, not per fight)
# --------------------------------------------------------------------------


class BotMediaValue(_Model):
    name: str
    fights: int = 0
    #: Total wide-coverage seconds this bot was on screen.
    screen_s: float = 0.0
    #: Mean fight attention / episode baseline.
    attn_index: float = 0.0
    #: screen_s * attn_index (formula documented in DECISIONS.md).
    media_value: float = 0.0
    record: str | None = None
    #: Competitive performance, 0-1.
    perf_score: float = 0.0


class MediaValue(_Model):
    bots: list[BotMediaValue] = Field(default_factory=list)


# --------------------------------------------------------------------------
# Path resolution + load/save helpers
# --------------------------------------------------------------------------

_ARTIFACTS: dict[str, tuple[str, type[BaseModel]]] = {
    "meta": ("meta.json", FightMeta),
    "tracks": ("tracks.json", Tracks),
    "events": ("events.json", Events),
    "telemetry": ("telemetry.json", Telemetry),
    "attention": ("attention.json", Attention),
    "scorecard": ("scorecard.json", Scorecard),
}


def fight_dir(fight_id: str, create: bool = False) -> Path:
    """Return ``data/processed/<fight_id>/``."""
    p = PROCESSED_DIR / fight_id
    if create:
        p.mkdir(parents=True, exist_ok=True)
    return p


def artifact_path(fight_id: str, kind: str) -> Path:
    """Resolve the canonical path for a named artifact of one fight."""
    if kind not in _ARTIFACTS:
        raise KeyError(f"unknown artifact {kind!r}; expected one of {sorted(_ARTIFACTS)}")
    return fight_dir(fight_id) / _ARTIFACTS[kind][0]


def _write_json(path: Path, model: BaseModel) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(model.model_dump(mode="json"), indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def _read_json(path: Path, cls: type[BaseModel]) -> Any:
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found. Produce it first — see the phase that owns it in README.md."
        )
    return cls.model_validate_json(path.read_text(encoding="utf-8"))


def save(fight_id: str, kind: str, model: BaseModel) -> Path:
    """Write one artifact to its canonical location."""
    return _write_json(artifact_path(fight_id, kind), model)


def load(fight_id: str, kind: str) -> Any:
    """Read and validate one artifact from its canonical location."""
    return _read_json(artifact_path(fight_id, kind), _ARTIFACTS[kind][1])


def exists(fight_id: str, kind: str) -> bool:
    return artifact_path(fight_id, kind).exists()


# Named convenience wrappers — these are the API other modules should use.
def save_meta(m: FightMeta) -> Path:
    return save(m.fight_id, "meta", m)


def load_meta(fight_id: str) -> FightMeta:
    return load(fight_id, "meta")


def save_tracks(m: Tracks) -> Path:
    return save(m.fight_id, "tracks", m)


def load_tracks(fight_id: str) -> Tracks:
    return load(fight_id, "tracks")


def save_events(m: Events) -> Path:
    return save(m.fight_id, "events", m)


def load_events(fight_id: str) -> Events:
    return load(fight_id, "events")


def save_telemetry(m: Telemetry) -> Path:
    return save(m.fight_id, "telemetry", m)


def load_telemetry(fight_id: str) -> Telemetry:
    return load(fight_id, "telemetry")


def save_attention(m: Attention) -> Path:
    return save(m.fight_id, "attention", m)


def load_attention(fight_id: str) -> Attention:
    return load(fight_id, "attention")


def save_scorecard(m: Scorecard) -> Path:
    return save(m.fight_id, "scorecard", m)


def load_scorecard(fight_id: str) -> Scorecard:
    return load(fight_id, "scorecard")


def save_media_value(m: MediaValue) -> Path:
    return _write_json(PROCESSED_DIR / "media_value.json", m)


def load_media_value() -> MediaValue:
    return _read_json(PROCESSED_DIR / "media_value.json", MediaValue)


def list_fights() -> list[str]:
    """Fight ids that have a processed directory on disk."""
    if not PROCESSED_DIR.exists():
        return []
    return sorted(p.name for p in PROCESSED_DIR.iterdir() if p.is_dir())
