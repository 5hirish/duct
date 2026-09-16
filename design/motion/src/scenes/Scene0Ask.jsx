import { useCurrentFrame, useVideoConfig } from "remotion";
import { SPRING, springAt } from "../lib/motion.js";
import { Ask, Thread, TypingDots } from "../ui/Thread.jsx";

// 0–3 s. The question, and nothing else. The bubble arrives from below with
// a little bounce; the typing dots run until the cut.
export const Scene0Ask = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const p = springAt(frame, fps, 0, { damping: 12, stiffness: 120 });
  return (
    <Thread style={{ opacity: Math.min(1, p * 1.6), transform: `translateY(${(1 - p) * 48}px)` }}>
      <Ask />
      <TypingDots frame={frame} />
    </Thread>
  );
};
