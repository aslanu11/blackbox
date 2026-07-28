// E3 - plays the burned-in overlay.mp4 (D5's output). No live canvas overlay
// is ever drawn here (spec §2.6) - the video IS the overlay.

import { forwardRef } from "react";

interface Props {
  src: string | null;
  fightId: string;
  onTime: (t: number) => void;
}

const VideoHero = forwardRef<HTMLVideoElement, Props>(function VideoHero(
  { src, fightId, onTime },
  ref,
) {
  if (!src) {
    return (
      <div className="video-hero panel">
        <p className="empty-state">
          No overlay video recovered for this fight yet. Run{" "}
          <code>bb overlay --fight-id {fightId}</code> then <code>bb export</code>.
        </p>
      </div>
    );
  }
  return (
    <div className="video-hero">
      <video
        ref={ref}
        src={src}
        controls
        playsInline
        onTimeUpdate={(e) => onTime(e.currentTarget.currentTime)}
      />
    </div>
  );
});

export default VideoHero;
