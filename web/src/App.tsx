// E1 shell: loads /data/index.json, offers the fight selector, and hands the
// selected fight's artifacts to the panels. Missing artifacts render empty
// states - the page never crashes on absent data.

import { useEffect, useRef, useState } from "react";
import TimelineLanes from "./components/TimelineLanes";
import VideoHero from "./components/VideoHero";
import Guide from "./components/Guide";
import HeatmapPanel from "./components/HeatmapPanel";
import ScorecardCard from "./components/ScorecardCard";
import RobberyTable from "./components/RobberyTable";
import MediaValueTable from "./components/MediaValueTable";
import SponsorTable, { type SponsorIndex } from "./components/SponsorTable";
import WinsVsWatches from "./components/WinsVsWatches";
import {
  gapsFromTracks,
  type Attention,
  type Events,
  type FightIndex,
  type IndexEntry,
  type MediaValue,
  type Scorecard,
  type Telemetry,
  type Tracks,
} from "./types";

async function fetchJson<T>(url: string): Promise<T | null> {
  try {
    const r = await fetch(url);
    if (!r.ok) return null;
    return (await r.json()) as T;
  } catch {
    return null;
  }
}

interface FightData {
  tracks: Tracks | null;
  events: Events | null;
  telemetry: Telemetry | null;
  attention: Attention | null;
  scorecard: Scorecard | null;
}

export default function App() {
  const [index, setIndex] = useState<FightIndex | null>(null);
  const [fightId, setFightId] = useState<string | null>(null);
  const [data, setData] = useState<FightData | null>(null);
  const [media, setMedia] = useState<MediaValue | null>(null);
  const [sponsor, setSponsor] = useState<SponsorIndex | null>(null);
  const [scorecards, setScorecards] = useState<Record<string, Scorecard>>({});
  const [playhead, setPlayhead] = useState(-1);
  // "recorder" | "guide" - toggled by the masthead link; the hash keeps the
  // guide directly linkable (…/#guide) without a router.
  const [view, setView] = useState<"recorder" | "guide">(
    window.location.hash === "#guide" ? "guide" : "recorder",
  );
  const videoRef = useRef<HTMLVideoElement>(null);

  const showGuide = (on: boolean) => {
    setView(on ? "guide" : "recorder");
    window.location.hash = on ? "#guide" : "";
  };

  useEffect(() => {
    (async () => {
      const idx = await fetchJson<FightIndex>("/data/index.json");
      setIndex(idx);
      if (idx?.fights.length) setFightId(idx.fights[0].fight_id);
      setMedia(await fetchJson<MediaValue>("/data/media_value.json"));
      setSponsor(await fetchJson<SponsorIndex>("/data/sponsor_index.json"));
      if (idx) {
        const cards: Record<string, Scorecard> = {};
        await Promise.all(
          idx.fights
            .filter((f) => f.has.scorecard)
            .map(async (f) => {
              const sc = await fetchJson<Scorecard>(`/data/${f.fight_id}/scorecard.json`);
              if (sc) cards[f.fight_id] = sc;
            }),
        );
        setScorecards(cards);
      }
    })();
  }, []);

  useEffect(() => {
    if (!fightId) return;
    setData(null);
    setPlayhead(-1);
    (async () => {
      const base = `/data/${fightId}`;
      const [tracks, events, telemetry, attention, scorecard] = await Promise.all([
        fetchJson<Tracks>(`${base}/tracks.json`),
        fetchJson<Events>(`${base}/events.json`),
        fetchJson<Telemetry>(`${base}/telemetry.json`),
        fetchJson<Attention>(`${base}/attention.json`),
        fetchJson<Scorecard>(`${base}/scorecard.json`),
      ]);
      setData({ tracks, events, telemetry, attention, scorecard });
    })();
  }, [fightId]);

  const fight: IndexEntry | undefined = index?.fights.find((f) => f.fight_id === fightId);

  if (!index) {
    return (
      <div className="shell">
        <p className="empty-state">
          No telemetry recovered yet. Run <code>bb fixture</code>, the pipeline, then{" "}
          <code>bb export</code> - then reload.
        </p>
      </div>
    );
  }

  const duration = data?.tracks?.frames.length
    ? data.tracks.frames[data.tracks.frames.length - 1].t
    : (data?.attention?.points.at(-1)?.[0] ?? 150);
  const gaps = data?.tracks ? gapsFromTracks(data.tracks) : [];
  const coverage = data?.tracks ? Math.round(data.tracks.coverage * 100) : null;

  const seek = (t: number) => {
    const v = videoRef.current;
    if (v) v.currentTime = t;
    setPlayhead(t);
  };

  return (
    <div className="shell">
      <header className="masthead">
        <span className="display wordmark">
          BLACKBOX <span className="rec-dot">▮</span>
          <span className="rec-dot" style={{ fontSize: 11, verticalAlign: "middle" }}>
            REC
          </span>
        </span>
        <span className="display tagline dim">FLIGHT RECORDER FOR ROBOT COMBAT</span>
        <button className="guide-link display" onClick={() => showGuide(view !== "guide")}>
          {view === "guide" ? "RECORDER" : "HOW TO READ"}
        </button>
        <select value={fightId ?? ""} onChange={(e) => setFightId(e.target.value)} aria-label="Select fight">
          {index.fights.map((f) => (
            <option key={f.fight_id} value={f.fight_id}>
              {f.fight_id} · {f.bots.join(" vs ")}
            </option>
          ))}
        </select>
      </header>

      {view === "guide" && <Guide onBack={() => showGuide(false)} />}

      {view === "recorder" && fight && (
        <main className="stack">
          <VideoHero
            ref={videoRef}
            src={fight.has.overlay ? `/data/${fight.fight_id}/overlay.mp4` : null}
            fightId={fight.fight_id}
            onTime={setPlayhead}
          />

          <TimelineLanes
            duration={duration}
            momentum={data?.telemetry?.series.momentum ?? []}
            attention={data?.attention?.points ?? []}
            events={data?.events ?? null}
            gaps={gaps}
            bots={fight.bots}
            colors={fight.colors}
            playhead={playhead}
            onSeek={seek}
          />

          <div className="panel-grid">
            <HeatmapPanel
              fightId={fight.fight_id}
              heatmaps={data?.telemetry?.heatmap_png ?? {}}
              colors={fight.colors}
            />
            <ScorecardCard
              fightId={fight.fight_id}
              scorecard={data?.scorecard ?? null}
              bots={fight.bots}
              colors={fight.colors}
            />
            <RobberyTable fights={index.fights} scorecards={scorecards} />
          </div>

          <div className="panel-grid-2">
            <MediaValueTable media={media} />
            <WinsVsWatches media={media} colors={fight.colors} />
          </div>

          <SponsorTable index={sponsor} />

          <p className="footer-note">
            {coverage !== null ? `COVERAGE ${coverage}%` : "COVERAGE n/a"} · CH1 MOMENTUM · CH2
            EVENTS · CH3 ATTENTION · hatched = no wide-shot telemetry, nothing interpolated
          </p>
        </main>
      )}
    </div>
  );
}
