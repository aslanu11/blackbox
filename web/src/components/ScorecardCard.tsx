// E3 - our rubric verdict vs the official one, three-axis bars.

import type { Scorecard } from "../types";

interface Props {
  fightId: string;
  scorecard: Scorecard | null;
  bots: string[];
  colors: Record<string, string>;
}

const AXES: { key: "damage" | "aggression" | "control"; label: string; total: number }[] = [
  { key: "damage", label: "DAMAGE", total: 5 },
  { key: "aggression", label: "AGGRESSION", total: 3 },
  { key: "control", label: "CONTROL", total: 3 },
];

export default function ScorecardCard({ fightId, scorecard, bots, colors }: Props) {
  if (!scorecard) {
    return (
      <section className="panel">
        <h2 className="display">Scorecard vs official</h2>
        <p className="empty-state">
          No scorecard for this fight yet. Run <code>bb scorecard --fight-id {fightId}</code>.
        </p>
      </section>
    );
  }
  const ourWinner = scorecard.ours.winner === "A" ? bots[0] : bots[1];
  const officialWinner =
    scorecard.official.winner === null ? null : scorecard.official.winner === "A" ? bots[0] : bots[1];
  const disagree = officialWinner !== null && officialWinner !== ourWinner;

  return (
    <section className="panel">
      <h2 className="display">Scorecard vs official</h2>
      {AXES.map(({ key, label, total }) => {
        const [a, b] = scorecard.ours[key];
        return (
          <div className="score-row" key={key}>
            <span className="channel-label dim">{label}</span>
            <div className="bar">
              <div style={{ width: `${(a / total) * 100}%`, background: colors[bots[0]] }} />
              <div style={{ width: `${(b / total) * 100}%`, background: colors[bots[1]] }} />
            </div>
            <span className="data">
              {a}–{b}
            </span>
          </div>
        );
      })}
      <p style={{ fontSize: 12.5, marginTop: 8 }}>
        Our card: <strong style={{ color: colors[ourWinner] }}>{ourWinner}</strong>
        {" · "}Official:{" "}
        {officialWinner ? (
          <strong style={{ color: colors[officialWinner] }}>
            {officialWinner}
            {scorecard.official.split ? ` (${scorecard.official.split})` : ""}
          </strong>
        ) : (
          <span className="dim">n/a</span>
        )}
        {disagree && (
          <span className="data" style={{ color: "var(--recorder-orange)", marginLeft: 8 }}>
            ROBBERY {scorecard.robbery_score.toFixed(2)}
          </span>
        )}
      </p>
    </section>
  );
}
