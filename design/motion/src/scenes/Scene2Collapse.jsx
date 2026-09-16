import { AbsoluteFill, interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import { C } from "../lib/tokens.js";
import { buildIn, ease } from "../lib/motion.js";
import { AppShell, APP } from "../ui/AppShell.jsx";
import { Mark } from "../ui/bits.jsx";
import { TABS, TabWindow, TAB_W } from "./Scene1OldWay.jsx";

// Where each mark ends up in the sidebar, in scene coordinates: the row at
// the bottom of the sidebar, 18 px marks, 6 px apart, 12 px in from the edge.
const MARK_AT = (i) => ({ x: APP.x + 12 + 12 + i * 24, y: APP.y + APP.h - 16 - 18 });
const COLLAPSE = 26; // frames the tabs take to fly into the sidebar

// 7–9 s. The five windows scale to points and land as the five marks. The
// app fades up beneath them, the clock rewinds, one frame flashes orange.
export const Scene2Collapse = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const fly = ease(frame, 4, COLLAPSE);
  const landed = frame >= 4 + COLLAPSE;
  const flash = frame === 4 + COLLAPSE ? 0.12 : 0;
  const prompt = buildIn(frame, fps, 40, { rise: 12 });
  return (
    <>
      <AppShell marks={landed ? 1 : 0} style={{ opacity: ease(frame, 6, 14) }}>
        <div style={{ flexGrow: 1, display: "flex", alignItems: "center", justifyContent: "center" }}>
          <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 14, color: C.muted, ...prompt }}>
            <span style={{ width: 14, height: 14, borderRadius: "50%", background: C.orange, display: "inline-block" }} />
            <span style={{ fontSize: 16 }}>Same question. Ask it here.</span>
          </div>
        </div>
      </AppShell>
      {landed
        ? null
        : TABS.map((tab, i) => {
            const to = MARK_AT(i);
            const cx = tab.x + TAB_W / 2;
            const cy = tab.y + 70;
            const x = interpolate(fly, [0, 1], [cx, to.x + 9]);
            const y = interpolate(fly, [0, 1], [cy, to.y + 9]);
            const s = interpolate(fly, [0, 1], [1, 0.06]);
            return (
              <div key={tab.id} style={{ position: "absolute", left: 0, top: 0, transform: `translate(${x}px, ${y}px) scale(${s})`, transformOrigin: "0 0" }}>
                <div style={{ transform: `translate(${-TAB_W / 2}px, -70px)`, opacity: 1 - fly * 0.4 }}>
                  <TabWindow tab={tab} frame={frame + 120} fps={fps} delay={0} progress={1} />
                </div>
                <Mark id={tab.id} size={18} style={{ position: "absolute", left: -9, top: -9, opacity: fly, transform: `scale(${1 / Math.max(s, 0.06)})`, transformOrigin: "center" }} />
              </div>
            );
          })}
      <AbsoluteFill style={{ background: C.orange, opacity: flash, pointerEvents: "none" }} />
    </>
  );
};
