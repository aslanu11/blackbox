// E3 - the rate card: screen time x attention per robot.

import { useMemo, useState } from "react";
import type { MediaValue } from "../types";

interface Props {
  media: MediaValue | null;
}

type SortKey = "media_value" | "screen_s" | "attn_index" | "perf_score";

export default function MediaValueTable({ media }: Props) {
  const [sortKey, setSortKey] = useState<SortKey>("media_value");
  const [desc, setDesc] = useState(true);

  const rows = useMemo(() => {
    const out = [...(media?.bots ?? [])];
    out.sort((a, b) => (desc ? b[sortKey] - a[sortKey] : a[sortKey] - b[sortKey]));
    return out;
  }, [media, sortKey, desc]);

  const toggle = (k: SortKey) => {
    if (k === sortKey) setDesc(!desc);
    else {
      setSortKey(k);
      setDesc(true);
    }
  };
  const arrow = (k: SortKey) => (sortKey === k ? (desc ? " ▾" : " ▴") : "");

  return (
    <section className="panel">
      <h2 className="display">Media value</h2>
      {rows.length === 0 ? (
        <p className="empty-state">
          No media value computed yet. Run <code>bb fuse</code> after attention data exists.
        </p>
      ) : (
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th>BOT</th>
                <th className="num">FIGHTS</th>
                <th className="num" onClick={() => toggle("screen_s")}>SCREEN s{arrow("screen_s")}</th>
                <th className="num" onClick={() => toggle("attn_index")}>ATTN{arrow("attn_index")}</th>
                <th className="num" onClick={() => toggle("media_value")}>VALUE{arrow("media_value")}</th>
                <th className="num">RECORD</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((b) => (
                <tr key={b.name}>
                  <td>{b.name}</td>
                  <td className="num">{b.fights}</td>
                  <td className="num">{b.screen_s.toFixed(0)}</td>
                  <td className="num">{b.attn_index.toFixed(2)}</td>
                  <td className="num">{b.media_value.toFixed(0)}</td>
                  <td className="num">{b.record ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
