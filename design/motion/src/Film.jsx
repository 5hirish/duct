import { AbsoluteFill, Sequence, interpolate, useCurrentFrame } from "remotion";
import { C, FONT } from "./lib/tokens.js";
import { ease } from "./lib/motion.js";
import { Clock, clockText } from "./ui/Clock.jsx";
import { Ground } from "./ui/Ground.jsx";
import { Sound } from "./Sound.jsx";
import { Scene0Ask } from "./scenes/Scene0Ask.jsx";
import { Scene1OldWay } from "./scenes/Scene1OldWay.jsx";
import { Scene2Collapse } from "./scenes/Scene2Collapse.jsx";
import { Scene3Reads } from "./scenes/Scene3Reads.jsx";
import { Scene4Acts } from "./scenes/Scene4Acts.jsx";
import { Scene5Remembers } from "./scenes/Scene5Remembers.jsx";
import { Scene6Reply } from "./scenes/Scene6Reply.jsx";
import { Scene7Desk } from "./scenes/Scene7Desk.jsx";
import { Scene8Close } from "./scenes/Scene8Close.jsx";

export const FPS = 30;
export const WIDTH = 1600;
export const HEIGHT = 1000;

// The nine beats of the storyboard (design/storyboard/canvas.json),
// in seconds. `origin` is where the camera move anchors: a scene that opens
// from a detail grows out of that detail, not out of the frame's centre.
const BEATS = [
  { id: "ask", at: 0, len: 3, C: Scene0Ask, origin: "50% 60%" },
  { id: "old-way", at: 3, len: 3.5, C: Scene1OldWay, origin: "50% 40%", hold: true },
  { id: "collapse", at: 6.5, len: 2, C: Scene2Collapse, origin: "16% 90%", cut: true },
  { id: "reads", at: 8.5, len: 5, C: Scene3Reads, origin: "40% 30%" },
  { id: "acts", at: 13.5, len: 5, C: Scene4Acts, origin: "40% 45%" },
  { id: "remembers", at: 18.5, len: 3, C: Scene5Remembers, origin: "12% 82%" },
  { id: "reply", at: 21.5, len: 3.5, C: Scene6Reply, origin: "50% 30%" },
  { id: "desk", at: 25, len: 2, C: Scene7Desk, origin: "50% 60%" },
  { id: "close", at: 27, len: 3, C: Scene8Close, origin: "50% 50%", cut: true },
];

export const DURATION = Math.round((BEATS.at(-1).at + BEATS.at(-1).len) * FPS);

const ENTER = 18; // frames a camera move takes to settle
const EXIT = 12; // frames the previous scene takes to leave under it

// One camera move, applied to a whole scene: it arrives slightly small and
// grows into place from its origin; it leaves by growing past 1 and fading.
// A scene marked `cut` just appears (the collapse continues the tabs from
// the scene before, so it must not re-enter; the close is the one hard cut),
// and one marked `hold` stays put while the next scene takes over its objects.
const Camera = ({ length, origin, cut, hold, children }) => {
  const frame = useCurrentFrame();
  const enter = cut ? 1 : ease(frame, 0, ENTER);
  const exit = hold ? 0 : ease(frame, length - EXIT, EXIT);
  const scale = 0.94 + 0.06 * enter + 0.03 * exit;
  return (
    <AbsoluteFill style={{ opacity: Math.min(enter * 1.4, 1) * (1 - exit), transform: `scale(${scale})`, transformOrigin: origin }}>
      {children}
    </AbsoluteFill>
  );
};

// The clock as a function of the film's absolute frame: 09:02 while the
// question sits there, spinning to 11:40 across the old way, one tick back
// to 09:02 when the tabs collapse, then real minutes as Duct works.
const clockAt = (frame) => {
  const s = frame / FPS;
  if (s < 3) return { text: clockText(9 * 60 + 2) };
  if (s < 6.5) return { text: clockText(interpolate(s, [3.2, 6], [9 * 60 + 2, 11 * 60 + 40], { extrapolateLeft: "clamp", extrapolateRight: "clamp" })) };
  if (s < 7) return { text: clockText(11 * 60 + 40) };
  if (s < 8.5) return { text: clockText(9 * 60 + 2), rewind: true };
  if (s < 13.5) return { text: clockText(9 * 60 + 3) };
  if (s < 18.5) return { text: clockText(9 * 60 + 5) };
  if (s < 27) return { text: clockText(9 * 60 + 7) };
  return { text: clockText(9 * 60 + 7), opacity: 0 };
};

// `sound` is on for every render; the hero plays the file muted anyway, and
// the social cuts want it. Off is for a silent preview in Studio.
export const Film = ({ sound = true }) => {
  const frame = useCurrentFrame();
  const closeAt = Math.round(BEATS.at(-1).at * FPS);
  const navy = ease(frame, closeAt, 15) * (1 - ease(frame, DURATION - 10, 10));
  const clock = clockAt(frame);
  return (
    <AbsoluteFill style={{ fontFamily: FONT.sans, color: C.ink, background: C.navy }}>
      <Ground navy={navy} />
      {BEATS.map((b) => {
        const from = Math.round(b.at * FPS);
        const length = Math.round(b.len * FPS) + (b.hold ? 0 : EXIT);
        return (
          <Sequence key={b.id} name={b.id} from={from} durationInFrames={length} premountFor={FPS}>
            <Camera length={length} origin={b.origin} cut={b.cut} hold={b.hold}>
              <b.C />
            </Camera>
          </Sequence>
        );
      })}
      <Clock text={clock.text} rewind={clock.rewind} opacity={clock.opacity ?? 1} />
      {sound ? <Sound fps={FPS} durationInFrames={DURATION} /> : null}
    </AbsoluteFill>
  );
};
