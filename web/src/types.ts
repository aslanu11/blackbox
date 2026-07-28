// Mirrors blackbox/schemas.py (§5) - the single source of truth.
// If a field isn't in schemas.py, it doesn't exist here either.

export type Series = [number, number][];

export interface FightResult {
  winner: string | null;
  method: "ko" | "jd" | null;
  time_s: number | null;
}

export interface IndexEntry {
  fight_id: string;
  bots: string[];
  colors: Record<string, string>;
  role: "hero" | "corpus" | "proleague" | null;
  result: FightResult | null;
  has: Record<string, boolean>;
}

export interface FightIndex {
  fights: IndexEntry[];
}

export interface TrackFrame {
  t: number;
  wide: boolean;
  pos: Record<string, [number, number]> | null;
}

export interface Tracks {
  fight_id: string;
  fps: number;
  coverage: number;
  frames: TrackFrame[];
}

export interface FightEvent {
  t: number;
  type: "hit" | "ko" | "hazard";
  magnitude: number | null;
  actor: string | null;
  target: string | null;
}

export interface Events {
  fight_id: string;
  events: FightEvent[];
}

export interface TelemetrySeries {
  momentum: Series;
  control: Series;
  speed: Record<string, Series>;
  mobility: Record<string, Series>;
}

export interface Telemetry {
  fight_id: string;
  series: TelemetrySeries;
  heatmap_png: Record<string, string>;
}

export interface AttentionStats {
  baseline: number;
  peak: number;
  peak_t: number;
}

export interface EventLift {
  event_t: number;
  type: "hit" | "ko" | "hazard";
  lift: number;
}

export interface Attention {
  video_id: string | null;
  fight_id: string;
  points: Series;
  stats: AttentionStats;
  event_lift: EventLift[];
}

export interface RubricScores {
  damage: [number, number];
  aggression: [number, number];
  control: [number, number];
  winner: "A" | "B";
  margin: number;
}

export interface OfficialVerdict {
  winner: "A" | "B" | null;
  split: string | null;
}

export interface Scorecard {
  fight_id: string;
  ours: RubricScores;
  official: OfficialVerdict;
  robbery_score: number;
}

export interface BotMediaValue {
  name: string;
  fights: number;
  screen_s: number;
  attn_index: number;
  media_value: number;
  record: string | null;
  perf_score: number;
}

export interface MediaValue {
  bots: BotMediaValue[];
}

/** Coverage gaps derived from tracks: [startT, endT] stretches with no wide data. */
export type Gap = [number, number];

export function gapsFromTracks(tracks: Tracks): Gap[] {
  const gaps: Gap[] = [];
  let start: number | null = null;
  for (const f of tracks.frames) {
    if (!f.wide && start === null) start = f.t;
    if (f.wide && start !== null) {
      gaps.push([start, f.t]);
      start = null;
    }
  }
  if (start !== null && tracks.frames.length) {
    gaps.push([start, tracks.frames[tracks.frames.length - 1].t]);
  }
  return gaps;
}
