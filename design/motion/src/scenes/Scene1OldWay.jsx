import { interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import { C, FONT } from "../lib/tokens.js";
import { buildIn, countUp, ease, springAt } from "../lib/motion.js";
import { Mark } from "../ui/bits.jsx";
import { Window } from "../ui/Window.jsx";
import { CAMPAIGN, N, TARGETS } from "../story.js";

// The five windows, where they land, and what each one says on its own.
// Each is true and each is useless alone; that is the scene's argument.
export const TABS = [
  { id: "google-ads", title: `Google Ads · ${CAMPAIGN.account}`, x: 120, y: 190, rot: -6, value: 14, format: (v) => `+${Math.round(v)}%`, tone: C.success, label: "ROAS vs last week · looks great" },
  { id: "googleanalytics", title: "Google Analytics · Signups", x: 560, y: 150, rot: 2, value: N.signups, format: (v) => Math.round(v).toString(), tone: C.destructive, label: `▼ 9% · target ${TARGETS.weeklySignups} · looks bad` },
  { id: "stripe", title: "Stripe · MRR", x: 1000, y: 210, rot: 5, value: 18400, format: (v) => `€${Math.round(v).toLocaleString("en-GB")}`, tone: C.ink, label: `▲ ${N.mrrDelta.replace("+", "")} · says nothing yet` },
  { id: "clarity", title: "Clarity · Rage clicks", x: 330, y: 470, rot: 3, value: N.rageClickClusters, format: (v) => `${Math.round(v)} clusters`, tone: C.warning, label: "all Android · Connect bank screen · why?" },
  { id: "googlesearchconsole", title: "Search Console · Impressions", x: 800, y: 500, rot: -4, value: 23, format: (v) => `+${Math.round(v)}%`, tone: C.success, label: "organic is fine" },
];

export const TAB_W = 520;
const ORIGIN = { x: 800, y: 420 }; // the bubble they fan out of

export const TabWindow = ({ tab, frame, fps, delay, progress }) => {
  const p = progress ?? springAt(frame, fps, delay, { damping: 14, stiffness: 110 });
  const x = interpolate(p, [0, 1], [ORIGIN.x - TAB_W / 2, tab.x]);
  const y = interpolate(p, [0, 1], [ORIGIN.y, tab.y]);
  const scale = interpolate(p, [0, 1], [0.2, 1]);
  const value = countUp(frame, delay + 8, 24, tab.value, tab.format);
  return (
    <Window
      dots
      style={{
        position: "absolute",
        left: x,
        top: y,
        width: TAB_W,
        opacity: Math.min(1, p * 2),
        transform: `rotate(${tab.rot * p}deg) scale(${scale})`,
        transformOrigin: "center",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "12px 16px", borderBottom: `1px solid ${C.border}`, fontSize: 13, color: C.navy3 }}>
        <Mark id={tab.id} />
        <span>{tab.title}</span>
      </div>
      <div style={{ padding: "20px 22px 24px", display: "flex", flexDirection: "column", gap: 8 }}>
        <div style={{ fontSize: 40, fontWeight: 600, letterSpacing: "-0.02em", color: tab.tone }}>{value}</div>
        <div style={{ fontSize: 13, color: C.navy3 }}>{tab.label}</div>
      </div>
    </Window>
  );
};

// 3–7 s. Tabs fan out on staggered springs; the caption lands last.
export const Scene1OldWay = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const caption = buildIn(frame, fps, 72, { rise: 20 });
  return (
    <>
      {TABS.map((tab, i) => (
        <TabWindow key={tab.id} tab={tab} frame={frame} fps={fps} delay={i * 6} />
      ))}
      <div style={{ position: "absolute", left: 0, right: 0, bottom: 84, textAlign: "center", fontFamily: FONT.serif, fontSize: 34, color: C.navy2, ...caption }}>
        five tabs <span style={{ color: C.navy3 }}>·</span> three hours <span style={{ color: C.navy3 }}>·</span>{" "}
        <em style={{ color: C.orange, opacity: ease(frame, 86, 10) }}>still a guess</em>
      </div>
    </>
  );
};
