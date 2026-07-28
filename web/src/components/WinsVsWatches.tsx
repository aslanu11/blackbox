// E3 - scatter: does winning correlate with being watched? Outliers labeled.

import type { MediaValue } from "../types";

const W = 520;
const H = 300;
const PAD = { l: 44, r: 12, t: 10, b: 30 };

interface Props {
  media: MediaValue | null;
  colors: Record<string, string>;
}

export default function WinsVsWatches({ media, colors }: Props) {
  const bots = media?.bots ?? [];
  if (bots.length === 0) {
    return (
      <section className="panel">
        <h2 className="display">Wins vs watches</h2>
        <p className="empty-state">
          Needs media value data. Run <code>bb fuse</code> first.
        </p>
      </section>
    );
  }

  const maxV = Math.max(...bots.map((b) => b.media_value), 1);
  const x = (p: number) => PAD.l + p * (W - PAD.l - PAD.r);
  const y = (v: number) => H - PAD.b - (v / maxV) * (H - PAD.t - PAD.b);

  // Label the outliers: top/bottom quartile on value with mismatched perf.
  const median = [...bots].sort((a, b) => a.media_value - b.media_value)[
    Math.floor(bots.length / 2)
  ].media_value;
  const isOutlier = (b: (typeof bots)[number]) =>
    (b.media_value > median * 1.5 && b.perf_score < 0.5) ||
    (b.media_value < median * 0.67 && b.perf_score > 0.5) ||
    bots.length <= 4;

  return (
    <section className="panel">
      <h2 className="display">Wins vs watches</h2>
      <svg viewBox={`0 0 ${W} ${H}`} style={{ width: "100%", height: "auto" }} role="img" aria-label="Scatter of performance vs media value">
        <line x1={PAD.l} y1={H - PAD.b} x2={W - PAD.r} y2={H - PAD.b} stroke="var(--line)" />
        <line x1={PAD.l} y1={PAD.t} x2={PAD.l} y2={H - PAD.b} stroke="var(--line)" />
        <text x={(W + PAD.l) / 2} y={H - 6} textAnchor="middle" className="lane-label">
          PERF SCORE (wins)
        </text>
        <text x={10} y={(H - PAD.b + PAD.t) / 2} className="lane-label" transform={`rotate(-90 10 ${(H - PAD.b + PAD.t) / 2})`} textAnchor="middle">
          MEDIA VALUE
        </text>
        {[0, 0.5, 1].map((p) => (
          <text key={p} x={x(p)} y={H - PAD.b + 14} textAnchor="middle" className="lane-label">
            {p}
          </text>
        ))}
        {bots.map((b) => (
          <g key={b.name}>
            <circle cx={x(b.perf_score)} cy={y(b.media_value)} r={5} fill={colors[b.name] ?? "var(--ink-dim)"} opacity={0.9} />
            {isOutlier(b) && (
              <text x={x(b.perf_score) + 8} y={y(b.media_value) + 4} fontSize={11} fill="var(--ink)" fontFamily="var(--font-data)">
                {b.name}
              </text>
            )}
          </g>
        ))}
      </svg>
    </section>
  );
}
