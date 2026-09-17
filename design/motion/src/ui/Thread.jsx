import { C, FONT } from "../lib/tokens.js";
import { Avatar } from "./bits.jsx";
import { Window } from "./Window.jsx";
import { ASKER, COMPANY, QUESTION, USER } from "../story.js";

// The team chat where the morning starts and ends. Not a named product on
// purpose: every team has one, and the film is about what happens between
// the question and the answer.
export const Thread = ({ style, top = 250, children, blur = false }) => (
  <Window
    radius={20}
    style={{
      position: "absolute",
      left: 400,
      top,
      width: 800,
      fontFamily: FONT.sans,
      ...(blur ? { filter: "blur(2px)", opacity: 0.35, boxShadow: "none" } : {}),
      ...style,
    }}
  >
    <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "18px 24px", borderBottom: `1px solid ${C.border}`, fontSize: 15, color: C.navy3 }}>
      <span style={{ fontWeight: 600, color: C.navy }}>#growth</span>
      <span>· {COMPANY}</span>
    </div>
    <div style={{ display: "flex", flexDirection: "column", gap: 22, padding: "28px 24px 30px" }}>{children}</div>
  </Window>
);

export const Message = ({ who, at, children, style }) => (
  <div style={{ display: "flex", gap: 14, alignItems: "flex-start", ...style }}>
    <Avatar initials={who.initials} bg={who === USER ? C.orange : C.navy2} />
    <div style={{ display: "flex", flexDirection: "column", gap: 6, flexGrow: 1, minWidth: 0 }}>
      <div style={{ display: "flex", gap: 10, alignItems: "baseline" }}>
        <span style={{ fontSize: 16, fontWeight: 600 }}>{who.name}</span>
        <span style={{ fontSize: 13, color: C.navy3 }}>{at}</span>
      </div>
      {children}
    </div>
  </div>
);

export const Ask = ({ size = 26, style }) => (
  <Message who={ASKER} at="09:02" style={style}>
    <div style={{ fontSize: size, lineHeight: 1.35 }}>
      <span style={{ color: C.orange, fontWeight: 600 }}>@{USER.name.split(" ")[0].toLowerCase()}</span> {QUESTION}
    </div>
  </Message>
);

export const TypingDots = ({ frame }) => (
  <div style={{ display: "flex", gap: 14, alignItems: "center", paddingLeft: 54 }}>
    <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
      {[0, 1, 2].map((i) => (
        <span key={i} style={{ width: 8, height: 8, borderRadius: "50%", background: C.navy3, opacity: 0.3 + 0.7 * Math.abs(Math.sin((frame / 10 + i / 3) * Math.PI)) }} />
      ))}
    </div>
    <span style={{ fontSize: 13, color: C.navy3 }}>{USER.name.split(" ")[0]} is typing…</span>
  </div>
);
