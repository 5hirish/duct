import { Easing, interpolate, spring } from "remotion";

// The film's shared vocabulary, lifted from the Claude Design launch film:
// one easing for every camera move, one spring for panels that open from
// where they were summoned, one for things that should overshoot.
export const CAMERA_EASE = Easing.bezier(0.4, 0, 0.2, 1);

export const SPRING = Object.freeze({
  smooth: { damping: 200 },
  panel: { damping: 18, stiffness: 170 },
  snappy: { damping: 20, stiffness: 200 },
  bouncy: { damping: 9, stiffness: 120 },
});

export const seconds = (fps, s) => Math.round(fps * s);

// 0→1 over [from, from + duration] frames with the camera easing, clamped.
export const ease = (frame, from, duration, easing = CAMERA_EASE) =>
  interpolate(frame, [from, from + duration], [0, 1], {
    easing,
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

// A spring that starts at `delay` frames; before that it holds at 0.
export const springAt = (frame, fps, delay, config = SPRING.panel, durationInFrames) =>
  spring({ frame: frame - delay, fps, config, durationInFrames });

// Build-in: opacity + rise for staggered lists. Returns a style object.
export const buildIn = (frame, fps, delay, { rise = 16, config = SPRING.smooth } = {}) => {
  const p = springAt(frame, fps, delay, config);
  return { opacity: p, transform: `translateY(${(1 - p) * rise}px)` };
};

// Origin-anchored open: the panel grows from 0.85 at the point it was
// summoned from (transformOrigin), the way a detail opens beside its source.
export const openFrom = (frame, fps, delay, origin = "left top", config = SPRING.panel) => {
  const p = springAt(frame, fps, delay, config);
  return {
    opacity: interpolate(p, [0, 0.4], [0, 1], { extrapolateRight: "clamp" }),
    transform: `scale(${0.85 + 0.15 * p})`,
    transformOrigin: origin,
  };
};

// Count-up for numbers: formats with the caller's formatter.
export const countUp = (frame, from, duration, target, format = (n) => Math.round(n).toLocaleString("en-GB")) => {
  const p = ease(frame, from, duration, Easing.out(Easing.cubic));
  return format(target * p);
};

// Human typing: characters land at irregular intervals; a comma or a
// question mark buys a pause. Deterministic per index so renders agree.
export const typed = (text, frame, from, { pauseAfter = ",", pauseFrames = 6 } = {}) => {
  let f = from;
  let shown = 0;
  for (let i = 0; i < text.length; i += 1) {
    const jitter = (i * 7) % 3; // 0..2 frames, fixed per character
    f += 1 + jitter;
    if (frame < f) break;
    shown = i + 1;
    if (pauseAfter.includes(text[i])) f += pauseFrames;
  }
  return { shown: text.slice(0, shown), done: shown === text.length, endsAt: f };
};

// Frame count a typed string needs, so the next beat can wait for it.
export const typedDuration = (text, { pauseAfter = ",", pauseFrames = 6 } = {}) => {
  let f = 0;
  for (let i = 0; i < text.length; i += 1) {
    f += 1 + ((i * 7) % 3);
    if (pauseAfter.includes(text[i])) f += pauseFrames;
  }
  return f;
};

// Cubic bezier path for the cursor, from a to b through one control point.
export const alongCurve = (t, a, c, b) => ({
  x: (1 - t) ** 2 * a.x + 2 * (1 - t) * t * c.x + t ** 2 * b.x,
  y: (1 - t) ** 2 * a.y + 2 * (1 - t) * t * c.y + t ** 2 * b.y,
});
