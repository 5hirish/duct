import { C, FONT } from "../lib/tokens.js";

// The one element that never leaves the frame: the film's argument is that
// the morning takes five minutes instead of three hours, and the clock is
// what makes that visible. `rewind` swaps the dot for the rewind glyph and
// paints the time orange for the beat where the day starts over.
export const Clock = ({ text, rewind = false, opacity = 1 }) => (
  <div
    style={{
      position: "absolute",
      top: 40,
      right: 48,
      display: "flex",
      alignItems: "center",
      gap: 10,
      fontFamily: FONT.mono,
      fontSize: 26,
      fontWeight: 500,
      letterSpacing: "0.02em",
      color: rewind ? C.orange : C.navy3,
      opacity,
    }}
  >
    {rewind ? (
      <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke={C.orange} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M3 12a9 9 0 1 0 3-6.7" />
        <path d="M3 4v5h5" />
      </svg>
    ) : (
      <span style={{ width: 10, height: 10, borderRadius: "50%", background: C.orange, display: "inline-block" }} />
    )}
    <span>{text}</span>
  </div>
);

export const clockText = (minutes) => {
  const h = Math.floor(minutes / 60);
  const m = Math.round(minutes % 60);
  return `Mon ${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
};
