import { interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import { C, FONT } from "../lib/tokens.js";
import { alongCurve, buildIn, ease, openFrom, springAt } from "../lib/motion.js";
import { AppShell, APP, PaneHead } from "../ui/AppShell.jsx";
import { Check, Cite, Cursor, Kpi, Outline, Pill } from "../ui/bits.jsx";
import { CAMPAIGN, CHANGE, N, SOURCES, TARGETS, WEEK_SHORT } from "../story.js";

// Beats, in local frames.
const T_CARD = 8;
const T_CURSOR = 44;
const T_PRESS = 88;
const T_APPLIED = T_PRESS + 6;
const T_BRIEF = 12;
const T_PULSE = 122;

// The chat pane's card sits at a known place, so the cursor can be aimed at
// the Apply button rather than at a guess. Coordinates are scene pixels.
const PANE_X = APP.x + APP.sidebar + 24;
const PANE_Y = APP.y + 53 + 24;
const CARD_W = 460;
// message block 66 + gap 16, then the card: header 66, two rows 140, half the
// 56 px footer; the button's centre sits 46 px in from the card's right edge.
const APPLY_AT = { x: PANE_X + CARD_W - 52, y: PANE_Y + 66 + 16 + 66 + 140 + 24 };
const CURSOR_FROM = { x: 1120, y: 880 };
const CURSOR_VIA = { x: 980, y: 560 };

const Row = ({ frame, fps, delay, title, note, tone = C.warning, badge, done, dim }) => {
  const b = buildIn(frame, fps, delay, { rise: 6 });
  return (
    <div style={{ display: "flex", alignItems: "flex-start", gap: 12, padding: "12px 16px", borderBottom: `1px solid rgba(230,228,225,0.6)`, ...b }}>
      {done ? (
        <span style={{ width: 16, height: 16, borderRadius: "50%", background: C.success, display: "inline-flex", alignItems: "center", justifyContent: "center", flexShrink: 0, marginTop: 2 }}>
          <Check size={10} />
        </span>
      ) : (
        <span style={{ width: 6, height: 6, borderRadius: "50%", background: "rgba(77,83,95,0.5)", marginTop: 8, flexShrink: 0 }} />
      )}
      <div style={{ flexGrow: 1 }}>
        <div style={{ fontSize: 14, lineHeight: 1.3, color: dim ? C.muted : C.ink }}>{title}</div>
        <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12, color: tone, marginTop: 3 }}>{note}</div>
      </div>
      {badge}
    </div>
  );
};

const Todo = ({ frame, fps, delay, title, meta, ticked }) => {
  const b = buildIn(frame, fps, delay, { rise: 10 });
  const t = ticked ? springAt(frame, fps, T_APPLIED, { damping: 12, stiffness: 180 }) : 0;
  return (
    <div style={{ display: "flex", alignItems: "flex-start", gap: 10, padding: "9px 12px", background: C.white, border: `1px solid ${C.border}`, borderRadius: 10, ...b }}>
      <span style={{ width: 18, height: 18, borderRadius: 5, border: `1.5px solid ${t > 0.2 ? C.primary : "#d5d3cf"}`, background: t > 0.2 ? C.primary : C.white, boxSizing: "border-box", display: "inline-flex", alignItems: "center", justifyContent: "center", flexShrink: 0, marginTop: 1, transform: `scale(${1 + 0.25 * Math.sin(Math.min(t, 1) * Math.PI)})` }}>
        <span style={{ opacity: t > 0.3 ? 1 : 0 }}>
          <Check size={12} />
        </span>
      </span>
      <div style={{ flexGrow: 1, minWidth: 0 }}>
        <div style={{ position: "relative", fontSize: 13, fontWeight: 500, lineHeight: 1.3, color: t > 0.5 ? C.muted : C.ink, display: "inline-block" }}>
          {title}
          <span style={{ position: "absolute", left: 0, top: "52%", height: 1.5, width: `${Math.max(0, Math.min(1, (t - 0.3) / 0.6)) * 100}%`, background: C.muted }} />
        </div>
        <div style={{ fontSize: 11, color: C.muted, marginTop: 2 }}>{meta}</div>
      </div>
    </div>
  );
};

// 14–19 s. The change card opens from the finding; the cursor travels to
// Apply on a curve; the press lands; the pause is applied and the brief's
// first action ticks itself. The blocked change stays blocked.
export const Scene4Acts = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const msg = buildIn(frame, fps, 0, { rise: 10 });
  const card = openFrom(frame, fps, T_CARD, "left top");
  const travel = ease(frame, T_CURSOR, T_PRESS - T_CURSOR - 4);
  const at = alongCurve(travel, CURSOR_FROM, CURSOR_VIA, APPLY_AT);
  const pressed = frame >= T_PRESS && frame < T_PRESS + 5;
  const applied = frame >= T_APPLIED;
  const appliedPop = springAt(frame, fps, T_APPLIED, { damping: 10, stiffness: 200 });
  const pulse = interpolate(frame, [T_PULSE, T_PULSE + 6, T_PULSE + 16], [0, 1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const title = buildIn(frame, fps, T_BRIEF, { rise: 10 });

  return (
    <>
      <AppShell active="Insights">
        <div style={{ width: 600, borderRight: `1px solid ${C.border}`, display: "flex", flexDirection: "column", boxSizing: "border-box" }}>
          <PaneHead>Insights · {WEEK_SHORT}</PaneHead>
          <div style={{ display: "flex", flexDirection: "column", gap: 16, padding: 24, flexGrow: 1 }}>
            <div style={{ alignSelf: "flex-start", maxWidth: "92%", background: C.surface, borderRadius: "4px 10px 10px 10px", padding: "10px 14px", fontSize: 14, lineHeight: 1.5, ...msg }}>
              Performance Max is buying signups at €{N.pmaxCpa.toFixed(2)} who leave within a week. I'd pause it and keep brand search on.
            </div>

            <div style={{ position: "relative", width: CARD_W, border: `1px solid ${applied ? "rgba(16,136,60,0.35)" : C.border}`, borderRadius: 12, background: C.white, overflow: "hidden", ...card }}>
              <div style={{ display: "flex", alignItems: "flex-start", gap: 12, padding: 16, height: 66, boxSizing: "border-box" }}>
                <div style={{ width: 32, height: 32, borderRadius: "50%", background: applied ? "rgba(16,136,60,0.12)" : "rgba(61,83,229,0.10)", color: applied ? C.success : C.primary, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0, transform: `scale(${1 + 0.2 * Math.sin(Math.min(appliedPop, 1) * Math.PI)})` }}>
                  {applied ? (
                    <Check size={16} stroke={C.success} />
                  ) : (
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M13 2 3 14h9l-1 8 10-12h-9l1-8z" />
                    </svg>
                  )}
                </div>
                <div style={{ flexGrow: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 14, fontWeight: 600, lineHeight: 1.3 }}>{CHANGE.title}</div>
                  <div style={{ fontSize: 12, color: C.muted, marginTop: 2 }}>Google Ads · {CAMPAIGN.account}</div>
                </div>
                {applied ? <Pill bg="rgba(16,136,60,0.12)" fg={C.success}>Applied</Pill> : <Pill>Pending</Pill>}
              </div>
              <div style={{ borderTop: `1px solid rgba(230,228,225,0.6)`, height: 140, boxSizing: "border-box" }}>
                <Row frame={frame} fps={fps} delay={T_CARD + 6} title={CHANGE.pause.diff.replace(CAMPAIGN.pmax, "PMax · Freelancers")} done={applied}
                  note={applied ? <span style={{ color: C.success }}>Paused at 09:05</span> : (
                    <>
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m21.7 18-8-14a2 2 0 0 0-3.4 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.7-3z" /><path d="M12 9v4M12 17h.01" /></svg>
                      {CHANGE.pause.warnings[0]}
                    </>
                  )}
                  badge={<Outline>Destructive</Outline>} />
                <Row frame={frame} fps={fps} delay={T_CARD + 10} title="Raise Brand EU budget €40 → €60 a day" dim tone={C.muted} note="Over the 25% guardrail · needs you" badge={<Outline>Blocked</Outline>} />
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 8, borderTop: `1px solid rgba(230,228,225,0.6)`, padding: "12px 16px", height: 56, boxSizing: "border-box" }}>
                <div style={{ flexGrow: 1, fontSize: 12, color: C.muted }}>{applied ? "1 applied · 1 still needs you" : "1 destructive, 1 blocked · both wait for you"}</div>
                <span style={{ padding: "6px 12px", borderRadius: 8, fontSize: 13, fontWeight: 500, opacity: applied ? 0.4 : 1 }}>Reject</span>
                <span style={{ padding: "6px 14px", borderRadius: 8, fontSize: 13, fontWeight: 500, background: applied ? C.success : C.primary, color: C.white, transform: `scale(${pressed ? 0.94 : 1})`, boxShadow: travel > 0.96 && !applied ? "0 0 0 4px rgba(61,83,229,0.18)" : "none" }}>
                  {applied ? "Applied" : "Apply"}
                </span>
              </div>
            </div>
          </div>
        </div>

        <div style={{ flexGrow: 1, display: "flex", flexDirection: "column", background: C.paper, minWidth: 0 }}>
          <PaneHead>Signups · {WEEK_SHORT}</PaneHead>
          <div style={{ display: "flex", flexDirection: "column", gap: 16, padding: 28 }}>
            <div style={{ fontFamily: FONT.serif, fontSize: 26, lineHeight: 1.2, letterSpacing: "-0.01em", ...title }}>Signups are down. ROAS is up. Same campaign.</div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
              <Kpi style={buildIn(frame, fps, T_BRIEF + 4)} value={String(N.signups)} label="Signups" delta={`▼ 9% · target ${TARGETS.weeklySignups}`} tone={C.destructive} />
              <Kpi style={buildIn(frame, fps, T_BRIEF + 8)} value={N.roasDelta} label="ROAS" delta="almost all from PMax" />
              <Kpi style={buildIn(frame, fps, T_BRIEF + 12)} value={`€${N.pmaxCpa.toFixed(2)}`} label="CPA · PMax" delta="▲ €7.40 over target" tone={C.destructive} />
              <Kpi style={buildIn(frame, fps, T_BRIEF + 16)} value={`€${N.brandCpa.toFixed(2)}`} label="CPA · Brand search" delta="▼ €3.30 under target" tone={C.success} />
            </div>
            <div style={{ fontSize: 13, lineHeight: 1.55, ...buildIn(frame, fps, T_BRIEF + 20) }}>
              <strong>The short version.</strong> The ROAS gain is hiding a retention problem, not describing a win.
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: "0.08em", textTransform: "uppercase", color: C.hint, ...buildIn(frame, fps, T_BRIEF + 24) }}>Do this week</div>
              <Todo frame={frame} fps={fps} delay={T_BRIEF + 26} ticked title="Pause Performance Max · Freelancers" meta="Duct · applied when you press Apply · €2,140 a week back" />
              <Todo frame={frame} fps={fps} delay={T_BRIEF + 30} title="Raise brand search budget €40 → €60 a day" meta="Needs you · over the 25% guardrail" />
              <Todo frame={frame} fps={fps} delay={T_BRIEF + 34} title="Fix the Connect bank screen on Android" meta={`Engineering · ${N.rageClickClusters} rage-click clusters, all in the PMax cohort`} />
            </div>
            <div style={{ display: "flex", gap: 6, flexWrap: "wrap", ...buildIn(frame, fps, T_BRIEF + 38) }}>
              {SOURCES.map((s, i) => (
                <Cite key={s.id} id={s.id} label={s.label} style={{ boxShadow: `0 0 0 ${3 * pulse}px rgba(255,92,0,${0.25 * pulse})`, transform: `translateY(${-2 * pulse * (i % 2 ? 0.6 : 1)}px)` }} />
              ))}
            </div>
          </div>
        </div>
      </AppShell>
      {frame >= T_CURSOR ? <Cursor x={at.x} y={at.y} pressed={pressed} /> : null}
    </>
  );
};
