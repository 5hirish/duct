import { useCurrentFrame, useVideoConfig } from "remotion";
import { C } from "../lib/tokens.js";
import { openFrom, springAt } from "../lib/motion.js";
import { Ask, Message, Thread } from "../ui/Thread.jsx";
import { N, REPLY, USER } from "../story.js";

// 22–26 s. Back in the thread. Maya's reply opens from under the question;
// the brief slides in as an attachment; the reaction pops. Then it holds.
export const Scene6Reply = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const reply = openFrom(frame, fps, 6, "left top");
  const attach = springAt(frame, fps, 30, { damping: 18, stiffness: 160 });
  const react = springAt(frame, fps, 56, { damping: 9, stiffness: 180 });
  const parts = REPLY.split(N.androidRetentionDrop);
  return (
    <Thread top={170}>
      <Ask size={20} />
      <div style={reply}>
        <Message who={USER} at="09:07">
          <div style={{ fontSize: 22, lineHeight: 1.4 }}>
            {parts[0]}
            <strong>{N.androidRetentionDrop}</strong>
            {parts[1]}
          </div>
          <div style={{ display: "inline-flex", alignItems: "center", gap: 12, alignSelf: "flex-start", padding: "12px 16px", border: `1px solid ${C.border}`, borderRadius: 12, background: "#f7f7f6", marginTop: 4, opacity: Math.min(1, attach * 2), transform: `translateX(${(1 - attach) * -24}px)` }}>
            <span style={{ width: 34, height: 34, borderRadius: 8, background: C.white, border: `1px solid ${C.border}`, display: "flex", alignItems: "center", justifyContent: "center" }}>
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke={C.navy} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                <path d="M14 2v6h6M8 13h8M8 17h6" />
              </svg>
            </span>
            <span style={{ display: "flex", flexDirection: "column", gap: 2 }}>
              <span style={{ fontSize: 14, fontWeight: 600 }}>Signups · week of 8 Sep</span>
              <span style={{ fontSize: 12, color: C.navy3 }}>Brief · 5 sources · written by Duct</span>
            </span>
          </div>
          <div style={{ display: "inline-flex", alignItems: "center", gap: 6, alignSelf: "flex-start", padding: "4px 10px", borderRadius: 999, border: `1px solid ${C.orange}`, background: "rgba(255,92,0,0.08)", fontSize: 13, marginTop: 6, opacity: Math.min(1, react * 2), transform: `scale(${1.2 * react})`, transformOrigin: "left center" }}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke={C.orange} strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="9" />
              <circle cx="12" cy="12" r="5" />
              <circle cx="12" cy="12" r="1" />
            </svg>
            <span>1</span>
          </div>
        </Message>
      </div>
    </Thread>
  );
};
