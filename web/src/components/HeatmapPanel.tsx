// E3 - two control heatmaps side by side, straight from B1's PNGs.
// Click a map to enlarge it (lightbox); Esc or click closes.

import { useEffect, useState } from "react";

interface Props {
  fightId: string;
  heatmaps: Record<string, string>;
  colors: Record<string, string>;
}

export default function HeatmapPanel({ fightId, heatmaps, colors }: Props) {
  const entries = Object.entries(heatmaps);
  const [enlarged, setEnlarged] = useState<[string, string] | null>(null);

  useEffect(() => {
    if (!enlarged) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setEnlarged(null);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [enlarged]);

  return (
    <section className="panel">
      <h2 className="display">Control heat</h2>
      {entries.length === 0 ? (
        <p className="empty-state">
          No telemetry recovered for this fight yet. Run{" "}
          <code>bb telemetry --fight-id {fightId}</code>.
        </p>
      ) : (
        <div className="heatmaps">
          {entries.map(([bot, png]) => (
            <figure key={bot}>
              <button
                className="heatmap-zoom"
                onClick={() => setEnlarged([bot, png])}
                aria-label={`Enlarge ${bot} heatmap`}
              >
                <img src={`/data/${fightId}/${png}`} alt={`${bot} floor presence heatmap`} />
              </button>
              <figcaption style={{ color: colors[bot] }}>{bot}</figcaption>
            </figure>
          ))}
        </div>
      )}

      {enlarged && (
        <div
          className="lightbox"
          role="dialog"
          aria-label={`${enlarged[0]} heatmap enlarged`}
          onClick={() => setEnlarged(null)}
        >
          <figure onClick={(e) => e.stopPropagation()}>
            <img src={`/data/${fightId}/${enlarged[1]}`} alt={`${enlarged[0]} floor presence heatmap, enlarged`} />
            <figcaption>
              <span style={{ color: colors[enlarged[0]] }}>{enlarged[0]}</span>
              <span className="dim"> · floor presence, brighter = more time · esc to close</span>
            </figcaption>
          </figure>
        </div>
      )}
    </section>
  );
}
