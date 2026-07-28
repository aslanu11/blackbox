// How to read the instruments. Linked from the masthead; plain content,
// instrument voice, honest about limits. No routing library - App toggles it.

interface Props {
  onBack: () => void;
}

const REPO = "https://github.com/aslanu11/blackbox";

export default function Guide({ onBack }: Props) {
  return (
    <main className="stack guide">
      <section className="panel guide-body">
        <button className="back-link" onClick={onBack}>
          ← back to the recorder
        </button>

        <h1 className="display">How to read the instruments</h1>
        <p className="dim">
          BattleBots publishes no telemetry: no positions, no speeds, no impact data. Everything
          on this page is manufactured by computer vision over broadcast footage, then fused with
          YouTube&apos;s public &quot;most replayed&quot; attention data. This guide says what each
          instrument means, how it&apos;s computed, and where it can be wrong.
        </p>

        <h2 className="display">The honesty rule</h2>
        <p>
          The CV lane can only see what the broadcast shows. When the production cuts to a
          close-up, a replay, or a camera we haven&apos;t calibrated, we have no positions —
          so every instrument renders those stretches as <strong>hatched voids</strong>, and each
          fight reports a <strong>coverage percentage</strong>. Nothing is interpolated across a
          camera cut. A number we didn&apos;t measure doesn&apos;t get drawn.
        </p>

        <h2 className="display">CH1 · Momentum</h2>
        <p>
          Live win probability for the first-listed robot, 0 to 1 around the 0.5 line. A logistic
          model over three bounded signals: <em>control</em> (who holds the centre and pushes the
          fight to the opponent&apos;s wall), the rolling 30-second <em>hit-magnitude
          differential</em>, and the <em>mobility differential</em>. Each signal&apos;s influence
          is capped, and outside a knockout the curve is clamped to 5–95%: the model is never
          allowed to claim certainty mid-fight. From five seconds before a KO it ramps to 99% for
          the winner.
        </p>

        <h2 className="display">CH2 · Events</h2>
        <p>
          Detected impacts. A <strong>hit</strong> is a joint velocity spike on both robots while
          they are within 2.5 m — marker size is the combined velocity change, and the
          &quot;actor&quot; is whichever robot was closing faster (on messy footage, treat actor
          attribution as an estimate). A <strong>hazard</strong> is an impulse inside a hazard
          zone with no opponent nearby. A <strong>KO</strong> comes from sustained mobility
          collapse or the official result.
        </p>

        <h2 className="display">CH3 · Attention</h2>
        <p>
          YouTube&apos;s &quot;most replayed&quot; heatmap for the episode, cut to fight-local
          time and normalised 0–1. This is real audience behaviour — which seconds people drag
          the scrubber back to. YouTube only publishes it once a video has enough views, so a
          fight can honestly have an empty attention lane. <em>Event lift</em> is the mean
          attention in a ±5 s window around a detected event divided by the fight&apos;s quiet
          baseline (20th percentile): lift above ~1.5 means the audience genuinely rewatches that
          moment.
        </p>

        <h2 className="display">Control heat</h2>
        <p>
          Where each robot spent the fight (brighter = more time), from tracked floor positions.
          Click a map to enlarge. Centre presence generally reads as control; a bright corner
          smear usually means a robot was pinned or dead there. Only tracked (wide-shot,
          calibrated-camera) time contributes.
        </p>

        <h2 className="display">Scorecard vs official</h2>
        <p>
          The modern BattleBots judging rubric, 11 points: <strong>Damage 5</strong>,
          <strong> Aggression 3</strong>, <strong>Control 3</strong>. For fully-tracked fights:
          damage from opponent mobility decay (plus a frame-comparison damage read), aggression
          from who initiates approaches, control from the integral of the control signal. For
          untracked fights, a vision-language model scores per-minute keyframes against the same
          rubric. Our card is an independent second opinion, not ground truth — when it disagrees
          with the judges, that disagreement is the product.
        </p>

        <h2 className="display">Robbery leaderboard</h2>
        <p>
          For judges&apos;-decision fights only: <em>robbery score</em> = our margin of
          disagreement with the official verdict, 0 when we agree. Sorted, it is a list of the
          fights our model thinks were scored wrong — including historical fan-alleged robberies
          scraped from the fight-history corpus.
        </p>

        <h2 className="display">Media value &amp; Wins vs Watches</h2>
        <p>
          Per robot: <code>screen_s</code> is tracked on-screen seconds;{" "}
          <code>attn_index</code> is the fight&apos;s mean attention against the episode baseline;
          <code> media value = screen_s × attn_index</code>. The scatter plots competitive
          performance against media value — the interesting robots are off the diagonal.
          A robot that loses but tops media value is under-priced sponsorship inventory; that
          divergence is the rate-card argument.
        </p>

        <h2 className="display">Where the data comes from</h2>
        <p>
          Fight results, the 24-bot roster, and the historical judges&apos;-decision corpus are
          scraped from the BattleBots wiki and battlebots.com through Bright Data&apos;s Web
          Unlocker (the wiki 403-blocks plain scrapers); every request is receipted in{" "}
          <code>data/fetch_log.jsonl</code>. Attention comes from YouTube&apos;s public
          most-replayed markers. Footage is processed locally and never redistributed — this site
          ships derived JSON and charts only.
        </p>

        <p className="dim guide-footer">
          Full methodology, code, and decision log:{" "}
          <a href={REPO} target="_blank" rel="noreferrer">
            {REPO.replace("https://", "")}
          </a>{" "}
          · MIT · built at BattleBots Hack Night, London · #battlebotsdev
        </p>
      </section>
    </main>
  );
}
