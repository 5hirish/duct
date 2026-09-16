import { Img, staticFile } from "remotion";
import { C, FONT } from "../lib/tokens.js";
import { COMPANY } from "../story.js";

export const Mark = ({ id, size = 18, style }) => (
  <Img src={staticFile(`${id}.svg`)} style={{ width: size, height: size, display: "block", ...style }} />
);

// The app's wordmark as the sidebar header draws it: serif "duct", the
// orange dot, the small "app" label.
export const Wordmark = ({ size = 18, light = false }) => (
  <span style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
    <span style={{ display: "inline-flex", alignItems: "center", gap: 6, fontFamily: FONT.serif, fontSize: size, letterSpacing: "-0.01em", color: light ? C.white : C.ink }}>
      duct
      <span style={{ width: size * 0.44, height: size * 0.44, borderRadius: "50%", background: C.orange, display: "inline-block" }} />
    </span>
    {light ? null : <span style={{ fontSize: 12, color: "rgba(11,17,31,0.4)" }}>app</span>}
  </span>
);

export const ProjectSwitcher = () => (
  <div
    style={{
      display: "flex",
      alignItems: "center",
      gap: 8,
      margin: "0 0 12px",
      padding: "6px 8px",
      border: `1px solid ${C.border}`,
      borderRadius: 8,
      background: C.white,
      fontSize: 13,
    }}
  >
    <span style={{ width: 22, height: 22, borderRadius: 6, background: C.navy2, color: C.white, display: "inline-flex", alignItems: "center", justifyContent: "center", fontSize: 11, fontWeight: 600, flexShrink: 0 }}>
      {COMPANY[0]}
    </span>
    <span style={{ flexGrow: 1, fontWeight: 500 }}>{COMPANY}</span>
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke={C.hint} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="m7 15 5 5 5-5M7 9l5-5 5 5" />
    </svg>
  </div>
);

export const Pill = ({ children, bg = C.surface, fg = C.muted, style }) => (
  <span style={{ display: "inline-flex", alignItems: "center", padding: "2px 8px", borderRadius: 999, background: bg, color: fg, fontSize: 11, fontWeight: 500, whiteSpace: "nowrap", ...style }}>
    {children}
  </span>
);

export const Outline = ({ children, style }) => (
  <span style={{ display: "inline-flex", alignItems: "center", padding: "2px 8px", borderRadius: 999, border: `1px solid ${C.border}`, color: C.muted, fontSize: 11, whiteSpace: "nowrap", ...style }}>
    {children}
  </span>
);

export const Cite = ({ id, label, style }) => (
  <span style={{ display: "inline-flex", alignItems: "center", gap: 6, padding: "3px 8px", borderRadius: 999, border: `1px solid ${C.border}`, background: C.white, fontSize: 11, color: C.muted, ...style }}>
    <Mark id={id} size={12} />
    {label}
  </span>
);

export const Kpi = ({ value, label, delta, tone = C.muted, style }) => (
  <div style={{ background: C.white, border: `1px solid ${C.border}`, borderRadius: 10, padding: "12px 14px", display: "flex", flexDirection: "column", gap: 2, ...style }}>
    <div style={{ fontSize: 22, fontWeight: 600, letterSpacing: "-0.02em" }}>{value}</div>
    <div style={{ fontSize: 11, color: C.muted }}>{label}</div>
    <div style={{ fontSize: 11, color: tone }}>{delta}</div>
  </div>
);

export const Avatar = ({ initials, bg }) => (
  <div style={{ width: 40, height: 40, borderRadius: 12, background: bg, color: C.white, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 15, fontWeight: 600, flexShrink: 0 }}>
    {initials}
  </div>
);

export const Check = ({ size = 12, stroke = C.white }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={stroke} strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
    <path d="m5 12 5 5 9-10" />
  </svg>
);

export const Cursor = ({ x, y, pressed = false }) => (
  <svg style={{ position: "absolute", left: x, top: y, transform: `scale(${pressed ? 0.9 : 1})`, transformOrigin: "5px 3px" }} width="28" height="28" viewBox="0 0 24 24" fill={C.navy} stroke={C.white} strokeWidth="1.5" strokeLinejoin="round">
    <path d="M5 3l14 8.5-6.2 1.6L9.5 20 5 3z" />
  </svg>
);
