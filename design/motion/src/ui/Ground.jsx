import { AbsoluteFill } from "remotion";
import { C, GROUND } from "../lib/tokens.js";

// The stage under every scene. `navy` (0..1) blends to the closing card's
// colour; the gradient stays underneath so the loop back to scene 0 is a
// dissolve to something that is already there.
export const Ground = ({ navy = 0 }) => (
  <AbsoluteFill style={{ background: GROUND }}>
    <AbsoluteFill style={{ background: C.navy, opacity: navy }} />
    <Grain />
  </AbsoluteFill>
);

// A whisper of static over the stage. H.264 at a web bitrate turns a soft
// light gradient into visible bands; a little deterministic noise is the
// standard cure, and it reads as paper rather than as noise at this level.
const Grain = () => (
  <svg width="100%" height="100%" style={{ position: "absolute", inset: 0, opacity: 0.045, mixBlendMode: "multiply" }}>
    <filter id="grain">
      <feTurbulence type="fractalNoise" baseFrequency="0.9" numOctaves="2" seed="7" stitchTiles="stitch" />
      <feColorMatrix type="saturate" values="0" />
    </filter>
    <rect width="100%" height="100%" filter="url(#grain)" />
  </svg>
);
