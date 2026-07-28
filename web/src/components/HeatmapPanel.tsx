// E3 - two control heatmaps side by side, straight from B1's PNGs.

interface Props {
  fightId: string;
  heatmaps: Record<string, string>;
  colors: Record<string, string>;
}

export default function HeatmapPanel({ fightId, heatmaps, colors }: Props) {
  const entries = Object.entries(heatmaps);
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
              <img src={`/data/${fightId}/${png}`} alt={`${bot} floor presence heatmap`} />
              <figcaption style={{ color: colors[bot] }}>{bot}</figcaption>
            </figure>
          ))}
        </div>
      )}
    </section>
  );
}
