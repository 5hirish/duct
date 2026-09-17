import { Img, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import { C, FONT, LIFT } from "../lib/tokens.js";
import { buildIn, ease, springAt } from "../lib/motion.js";
import { Pill } from "../ui/bits.jsx";
import { Ask, Thread } from "../ui/Thread.jsx";
import { BOARD } from "../story.js";

// Aspirational: no ads-audit agent ships yet (see the storyboard commit).
// Insights plus the Ads executors can do each line; the card names the shape.
const FIXES = [
  { sev: "High", tone: C.destructive, bg: "rgba(201,0,12,0.10)", text: "€610 last week on \"free budget template\" searches" },
  { sev: "High", tone: C.destructive, bg: "rgba(201,0,12,0.10)", text: "2 ad groups with no conversions in 30 days" },
  { sev: "Medium", tone: C.warning, bg: "rgba(154,101,0,0.12)", text: "Sitelinks missing on the Freelancers ads" },
];

const COLUMNS = [
  { key: "pending", head: "Pending", pill: (d) => `Planned · ${d}`, bg: C.surface, fg: C.muted },
  { key: "draft", head: "Draft", pill: (d) => `Scheduled · ${d}`, bg: "rgba(0,107,187,0.10)", fg: "#006bbb" },
  { key: "posted", head: "Posted", pill: (d) => `Published · ${d}`, bg: "rgba(16,136,60,0.10)", fg: C.success },
];

const Card = ({ style, children, width = 500 }) => (
  <div style={{ width, background: C.white, border: `1px solid ${C.border}`, borderRadius: 14, boxShadow: LIFT, overflow: "hidden", ...style }}>{children}</div>
);

const Head = ({ title, note }) => (
  <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "16px 20px", borderBottom: `1px solid ${C.border}` }}>
    <span style={{ fontSize: 15, fontWeight: 600 }}>{title}</span>
    <span style={{ fontSize: 13, color: C.muted }}>{note}</span>
  </div>
);

// A card flips up from the desk: rotateX from 70° to 0 on a spring.
const flipIn = (frame, fps, delay, rot) => {
  const p = springAt(frame, fps, delay, { damping: 16, stiffness: 140 });
  return { opacity: Math.min(1, p * 2), transform: `perspective(1400px) rotateX(${(1 - p) * 70}deg) rotate(${rot}deg)`, transformOrigin: "center bottom" };
};

// 26–28 s. The thread blurs. Two more things Duct did this week flip in.
export const Scene7Desk = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const covers = ease(frame, 30, 12);
  return (
    <>
      <Thread blur top={170}>
        <Ask size={20} />
      </Thread>
      <div style={{ position: "absolute", left: 0, right: 0, top: 122, textAlign: "center", fontFamily: FONT.serif, fontSize: 30, color: C.navy2, ...buildIn(frame, fps, 0, { rise: 14 }) }}>
        Also on your desk <em style={{ color: C.orange }}>this week</em>
      </div>
      <div style={{ position: "absolute", left: 190, top: 290, display: "flex", gap: 60, alignItems: "flex-start" }}>
        <Card style={flipIn(frame, fps, 8, -2)}>
          <Head title="Ads audit · Google Ads" note="9 fixes, prioritised" />
          {FIXES.map((f) => (
            <div key={f.text} style={{ display: "flex", alignItems: "center", gap: 10, padding: "10px 20px", borderBottom: `1px solid rgba(230,228,225,0.6)`, fontSize: 13 }}>
              <Pill bg={f.bg} fg={f.tone}>{f.sev}</Pill>
              {f.text}
            </div>
          ))}
          <div style={{ padding: "10px 20px", fontSize: 13, color: C.muted }}>+ 6 more · 14 negatives already added by Duct</div>
        </Card>

        <Card style={flipIn(frame, fps, 11, 2)}>
          <Head title="Content Studio · this week" note="2 posted · 1 drafted · 2 planned" />
          <div style={{ display: "grid", gridTemplateColumns: "repeat(3, minmax(0, 1fr))", gap: 10, padding: "16px 20px" }}>
            {COLUMNS.map((col) => {
              const items = BOARD.filter((b) => b.status === col.key);
              return (
                <div key={col.key} style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                  <span style={{ fontSize: 11, fontWeight: 600, letterSpacing: "0.08em", textTransform: "uppercase", color: C.hint, display: "flex", justifyContent: "space-between" }}>
                    {col.head}
                    <span style={{ color: "#b4afa8" }}>{items.length}</span>
                  </span>
                  {items.map((b) => (
                    <div key={b.topic} style={{ background: C.paper, border: `1px solid ${C.border}`, borderRadius: 8, padding: 10, fontSize: 12, lineHeight: 1.35, display: "flex", flexDirection: "column", gap: 6 }}>
                      {b.cover ? (
                        <span style={{ position: "relative", display: "block", height: 66, borderRadius: 6, overflow: "hidden", background: C.surface }}>
                          <Img src={staticFile(b.cover)} style={{ width: "100%", height: "100%", objectFit: "cover", display: "block", opacity: covers }} />
                          {b.status === "posted" ? (
                            <span style={{ position: "absolute", left: 6, bottom: 6, padding: "2px 6px", borderRadius: 4, background: "#b34000", color: C.white, fontSize: 8, fontWeight: 600, letterSpacing: "0.06em", textTransform: "uppercase", opacity: covers }}>via Duct</span>
                          ) : null}
                        </span>
                      ) : (
                        <span style={{ height: 66, borderRadius: 6, background: C.surface, display: "flex", alignItems: "center", justifyContent: "center", color: C.hint }}>
                          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="3" width="18" height="18" rx="2" /><circle cx="9" cy="9" r="2" /><path d="m21 15-5-5L5 21" /></svg>
                        </span>
                      )}
                      <Pill bg={col.bg} fg={col.fg} style={{ alignSelf: "flex-start", fontSize: 10, padding: "2px 7px" }}>{col.pill(b.day)}</Pill>
                      {b.topic}
                    </div>
                  ))}
                </div>
              );
            })}
          </div>
        </Card>
      </div>
    </>
  );
};
