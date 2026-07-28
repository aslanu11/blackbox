// E2 - THE signature component (spec §12).
// Three stacked lanes on ONE shared time axis under the video:
//   CH1 MOMENTUM   area chart around the 0.5 line
//   CH2 EVENTS     markers sized by magnitude, KO as a distinct glyph
//   CH3 ATTENTION  area chart
// Coverage gaps render as diagonal-hatched voids across ALL lanes - honesty
// as aesthetic. One orange playhead crosses everything, driven by
// video.timeupdate; clicking seeks.
//
// Hand-rolled SVG with a single shared x-scale: perfect alignment by
// construction, no chart library to fight.

import { useCallback, useRef } from "react";
import type { Events, Gap, Series } from "../types";

const W = 1200; // viewBox units; scales responsively
const LANE_H = 64;
const LANE_PAD = 10;
const LABEL_W = 110;
const AXIS_H = 18;
const H = LANE_H * 3 + LANE_PAD * 2 + AXIS_H;

interface Props {
  duration: number;
  momentum: Series;
  attention: Series;
  events: Events | null;
  gaps: Gap[];
  bots: string[];
  colors: Record<string, string>;
  playhead: number;
  onSeek: (t: number) => void;
}

export default function TimelineLanes({
  duration,
  momentum,
  attention,
  events,
  gaps,
  bots,
  colors,
  playhead,
  onSeek,
}: Props) {
  const svgRef = useRef<SVGSVGElement>(null);
  const x = useCallback(
    (t: number) => LABEL_W + ((W - LABEL_W) * t) / Math.max(duration, 1),
    [duration],
  );

  const laneY = (i: number) => i * (LANE_H + LANE_PAD);

  const handleClick = (e: React.MouseEvent<SVGSVGElement>) => {
    const svg = svgRef.current;
    if (!svg) return;
    const rect = svg.getBoundingClientRect();
    const vx = ((e.clientX - rect.left) / rect.width) * W;
    if (vx < LABEL_W) return;
    onSeek(((vx - LABEL_W) / (W - LABEL_W)) * duration);
  };

  const areaPath = (series: Series, y0: number, valueToY: (v: number) => number) => {
    if (!series.length) return "";
    let d = `M ${x(series[0][0])} ${y0}`;
    for (const [t, v] of series) d += ` L ${x(t)} ${valueToY(v)}`;
    d += ` L ${x(series[series.length - 1][0])} ${y0} Z`;
    return d;
  };

  const linePath = (series: Series, valueToY: (v: number) => number) => {
    if (!series.length) return "";
    return series
      .map(([t, v], i) => `${i === 0 ? "M" : "L"} ${x(t)} ${valueToY(v)}`)
      .join(" ");
  };

  // Lane value scales.
  const chA = laneY(0); // momentum: 0..1, 0.5 line at centre
  const momY = (v: number) => chA + LANE_H - v * LANE_H;
  const chB = laneY(1); // events
  const chC = laneY(2); // attention: 0..1
  const attY = (v: number) => chC + LANE_H - v * LANE_H * 0.92;

  const maxMag = Math.max(1, ...(events?.events ?? []).map((e) => e.magnitude ?? 0));

  const px = playhead >= 0 ? x(Math.min(playhead, duration)) : null;

  return (
    <div className="lanes panel">
      <svg
        ref={svgRef}
        viewBox={`0 0 ${W} ${H}`}
        onClick={handleClick}
        role="img"
        aria-label="Telemetry timeline: momentum, events, attention"
      >
        <defs>
          <pattern id="gap-hatch" width="6" height="6" patternTransform="rotate(45)" patternUnits="userSpaceOnUse">
            <rect width="6" height="6" fill="transparent" />
            <line x1="0" y1="0" x2="0" y2="6" stroke="var(--line)" strokeWidth="1.5" />
          </pattern>
        </defs>

        {/* Lane frames + labels */}
        {(
          [
            ["CH1 MOMENTUM", chA],
            ["CH2 EVENTS", chB],
            ["CH3 ATTENTION", chC],
          ] as const
        ).map(([label, y]) => (
          <g key={label}>
            <rect x={LABEL_W} y={y} width={W - LABEL_W} height={LANE_H} fill="var(--panel)" stroke="var(--line)" strokeWidth="1" />
            <text x={0} y={y + LANE_H / 2 + 3} className="lane-label">
              {label}
            </text>
          </g>
        ))}

        {/* Coverage gaps: hatched voids through all three lanes */}
        {gaps.map(([g0, g1], i) => (
          <rect
            key={i}
            x={x(g0)}
            y={chA}
            width={Math.max(x(g1) - x(g0), 2)}
            height={chC + LANE_H - chA}
            fill="url(#gap-hatch)"
            opacity="0.9"
          />
        ))}

        {/* CH1 momentum: fill relative to the 0.5 line, in bots[0]'s colour */}
        {momentum.length > 0 && (
          <>
            <line x1={LABEL_W} y1={momY(0.5)} x2={W} y2={momY(0.5)} stroke="var(--ink-dim)" strokeWidth="0.75" strokeDasharray="3 4" />
            <path d={areaPath(momentum, momY(0.5), momY)} fill={colors[bots[0]] ?? "var(--ink-dim)"} opacity="0.28" />
            <path d={linePath(momentum, momY)} fill="none" stroke={colors[bots[0]] ?? "var(--ink)"} strokeWidth="1.5" />
          </>
        )}

        {/* CH2 events */}
        {(events?.events ?? []).map((e, i) => {
          const cx = x(e.t);
          const cy = chB + LANE_H / 2;
          const color = e.actor ? (colors[e.actor] ?? "var(--ink)") : "var(--ink-dim)";
          if (e.type === "ko") {
            const s = 9;
            return (
              <g key={i} stroke="var(--recorder-orange)" strokeWidth="2.5">
                <line x1={cx - s} y1={cy - s} x2={cx + s} y2={cy + s} />
                <line x1={cx - s} y1={cy + s} x2={cx + s} y2={cy - s} />
              </g>
            );
          }
          const r = 2.5 + 6 * ((e.magnitude ?? 1) / maxMag);
          if (e.type === "hazard") {
            return (
              <rect key={i} x={cx - r} y={cy - r} width={r * 2} height={r * 2} transform={`rotate(45 ${cx} ${cy})`} fill="none" stroke={color} strokeWidth="1.5" />
            );
          }
          return <circle key={i} cx={cx} cy={cy} r={r} fill={color} opacity="0.85" />;
        })}

        {/* CH3 attention */}
        {attention.length > 0 && (
          <>
            <path d={areaPath(attention, chC + LANE_H, attY)} fill="var(--ink-dim)" opacity="0.25" />
            <path d={linePath(attention, attY)} fill="none" stroke="var(--ink)" strokeWidth="1.25" />
          </>
        )}

        {/* Time axis */}
        {Array.from({ length: Math.floor(duration / 30) + 1 }, (_, i) => i * 30).map((t) => (
          <g key={t}>
            <line x1={x(t)} y1={chC + LANE_H} x2={x(t)} y2={chC + LANE_H + 4} stroke="var(--ink-dim)" strokeWidth="1" />
            <text x={x(t)} y={H - 3} textAnchor="middle" className="lane-label">
              {`${Math.floor(t / 60)}:${String(t % 60).padStart(2, "0")}`}
            </text>
          </g>
        ))}

        {/* THE playhead: one orange rule through everything */}
        {px !== null && (
          <line x1={px} y1={chA} x2={px} y2={chC + LANE_H} stroke="var(--recorder-orange)" strokeWidth="1.75" />
        )}
      </svg>
    </div>
  );
}
