import { C, FONT, LIFT } from "../lib/tokens.js";
import { Mark, ProjectSwitcher, Wordmark } from "./bits.jsx";
import { SOURCES } from "../story.js";

export const APP = Object.freeze({ x: 120, y: 120, w: 1360, h: 800, sidebar: 256 });

const NAV = ["Insights", "Content", "Audit", "Connections", "Memory"];

// The Duct window as the app draws it: cream sidebar with the wordmark and
// the project switcher, five sections, the connected marks at the bottom.
// `marks` is 0..1 and fades the marks in, for the beat where the five tabs
// land in the sidebar.
export const AppShell = ({ active = "Insights", marks = 1, style, children }) => (
  <div
    style={{
      position: "absolute",
      left: APP.x,
      top: APP.y,
      width: APP.w,
      height: APP.h,
      background: C.white,
      border: `1px solid ${C.border}`,
      borderRadius: 14,
      boxShadow: LIFT,
      display: "flex",
      overflow: "hidden",
      fontFamily: FONT.sans,
      color: C.ink,
      ...style,
    }}
  >
    <div style={{ width: APP.sidebar, background: C.sidebar, borderRight: `1px solid ${C.border}`, display: "flex", flexDirection: "column", padding: "16px 12px", boxSizing: "border-box", gap: 4, flexShrink: 0 }}>
      <div style={{ padding: "6px 12px 10px" }}>
        <Wordmark />
      </div>
      <ProjectSwitcher />
      {NAV.map((item) => (
        <div
          key={item}
          style={{
            padding: "8px 12px",
            borderRadius: 8,
            fontSize: 14,
            color: item === active ? C.ink : C.muted,
            fontWeight: item === active ? 500 : 400,
            background: item === active ? C.surface : "transparent",
          }}
        >
          {item}
        </div>
      ))}
      <div style={{ flexGrow: 1 }} />
      <div style={{ padding: "0 12px 4px", fontSize: 11, fontWeight: 600, letterSpacing: "0.08em", textTransform: "uppercase", color: C.hint, opacity: marks }}>Connected</div>
      <div style={{ display: "flex", gap: 6, padding: "0 12px" }}>
        {SOURCES.map((s) => (
          <Mark key={s.id} id={s.id} size={18} style={{ opacity: marks }} />
        ))}
      </div>
    </div>
    {children}
  </div>
);

export const PaneHead = ({ children, style }) => (
  <div style={{ padding: "18px 24px", borderBottom: `1px solid ${C.border}`, fontSize: 13, color: C.muted, flexShrink: 0, ...style }}>{children}</div>
);
