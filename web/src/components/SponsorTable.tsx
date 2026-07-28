// S1 - Pranav's sponsorship attractiveness index, surfaced.
// Reads /data/sponsor_index.json: 0-100 score per bot from spotlight
// (critical-attention seconds), authorship (event-driving share) and
// performance, weighted 45/30/25.

interface SponsorBot {
  name: string;
  sponsor_score: number;
  components: { spotlight: number; authorship: number; performance: number };
  critical_seconds: number;
  peak_attention: number;
  fights: number;
  record: string | null;
  confidence: number;
}

export interface SponsorIndex {
  weights: { spotlight: number; authorship: number; performance: number };
  bots: SponsorBot[];
}

interface Props {
  index: SponsorIndex | null;
}

export default function SponsorTable({ index }: Props) {
  const rows = [...(index?.bots ?? [])].sort((a, b) => b.sponsor_score - a.sponsor_score);
  return (
    <section className="panel">
      <h2 className="display">Sponsor index</h2>
      {rows.length === 0 ? (
        <p className="empty-state">
          No sponsor index yet. Run <code>bb</code> sponsor scoring after attention data exists.
        </p>
      ) : (
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th>BOT</th>
                <th className="num">SCORE ▾</th>
                <th className="num">SPOTLIGHT</th>
                <th className="num">AUTHORSHIP</th>
                <th className="num">PERF</th>
                <th className="num">CRIT s</th>
                <th className="num">CONF</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((b) => (
                <tr key={b.name} style={{ opacity: 0.55 + 0.45 * b.confidence }}>
                  <td>{b.name}</td>
                  <td className="num">{b.sponsor_score.toFixed(1)}</td>
                  <td className="num">{b.components.spotlight.toFixed(2)}</td>
                  <td className="num">{b.components.authorship.toFixed(2)}</td>
                  <td className="num">{b.components.performance.toFixed(2)}</td>
                  <td className="num">{b.critical_seconds.toFixed(0)}</td>
                  <td className="num">{b.confidence.toFixed(2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="dim" style={{ fontSize: 11, marginTop: 6 }}>
        score = 45% spotlight (seconds above the critical attention threshold) + 30% authorship
        (share of hits driven) + 25% performance · faded rows = low-confidence (missing attention
        data)
      </p>
    </section>
  );
}
