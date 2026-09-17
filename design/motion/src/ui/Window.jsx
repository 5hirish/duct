import { C, LIFT, MAC_DOTS } from "../lib/tokens.js";

export const MacDots = ({ size = 10 }) => (
  <div
    style={{
      height: 28,
      background: "#f3f3f1",
      borderBottom: "1px solid #e3e3df",
      display: "flex",
      alignItems: "center",
      gap: 6,
      paddingLeft: 11,
      flexShrink: 0,
    }}
  >
    {MAC_DOTS.map((fill) => (
      <span key={fill} style={{ width: size, height: size, borderRadius: "50%", background: fill, display: "block" }} />
    ))}
  </div>
);

// A floating surface on the stage: white, hairline border, the README lift.
export const Window = ({ style, dots = false, radius = 12, children }) => (
  <div
    style={{
      background: C.white,
      border: `1px solid ${C.border}`,
      borderRadius: radius,
      boxShadow: LIFT,
      overflow: "hidden",
      display: "flex",
      flexDirection: "column",
      ...style,
    }}
  >
    {dots ? <MacDots /> : null}
    {children}
  </div>
);
