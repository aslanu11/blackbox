// E3 - fights our model says were scored wrong, sortable by robbery_score.

import { useMemo, useState } from "react";
import type { IndexEntry, Scorecard } from "../types";

interface Row {
  fight_id: string;
  bots: string[];
  ourWinner: string;
  officialWinner: string | null;
  split: string | null;
  robbery: number;
}

interface Props {
  fights: IndexEntry[];
  scorecards: Record<string, Scorecard>;
}

type SortKey = "robbery" | "fight_id";

export default function RobberyTable({ fights, scorecards }: Props) {
  const [sortKey, setSortKey] = useState<SortKey>("robbery");
  const [desc, setDesc] = useState(true);

  const rows = useMemo<Row[]>(() => {
    const out: Row[] = [];
    for (const f of fights) {
      const sc = scorecards[f.fight_id];
      if (!sc) continue;
      out.push({
        fight_id: f.fight_id,
        bots: f.bots,
        ourWinner: sc.ours.winner === "A" ? f.bots[0] : f.bots[1],
        officialWinner:
          sc.official.winner === null ? null : sc.official.winner === "A" ? f.bots[0] : f.bots[1],
        split: sc.official.split,
        robbery: sc.robbery_score,
      });
    }
    out.sort((a, b) =>
      sortKey === "robbery" ? (desc ? b.robbery - a.robbery : a.robbery - b.robbery)
        : desc ? b.fight_id.localeCompare(a.fight_id) : a.fight_id.localeCompare(b.fight_id),
    );
    return out;
  }, [fights, scorecards, sortKey, desc]);

  const toggle = (k: SortKey) => {
    if (k === sortKey) setDesc(!desc);
    else {
      setSortKey(k);
      setDesc(true);
    }
  };

  return (
    <section className="panel">
      <h2 className="display">Robbery leaderboard</h2>
      {rows.length === 0 ? (
        <p className="empty-state">
          No judges&#39;-decision fights scored yet. Fill the corpus in{" "}
          <code>data/manifest.yaml</code> and run <code>bb scorecard</code>.
        </p>
      ) : (
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th onClick={() => toggle("fight_id")}>FIGHT</th>
                <th>OUR CARD</th>
                <th>OFFICIAL</th>
                <th className="num" onClick={() => toggle("robbery")}>
                  ROBBERY {sortKey === "robbery" ? (desc ? "▾" : "▴") : ""}
                </th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.fight_id}>
                  <td className="data">{r.fight_id}</td>
                  <td>{r.ourWinner}</td>
                  <td>
                    {r.officialWinner ?? "—"}
                    {r.split ? ` (${r.split})` : ""}
                  </td>
                  <td className="num" style={r.robbery > 0 ? { color: "var(--recorder-orange)" } : undefined}>
                    {r.robbery.toFixed(2)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
