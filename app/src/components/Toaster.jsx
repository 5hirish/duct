"use client";

import { useEffect, useState } from "react";
import { subscribeToasts, dismissToast } from "../lib/toast";

// Accent + border per variant, themed off the shadcn CSS variables with safe
// fallbacks so it reads correctly in both light and dark.
const VARIANT = {
  default: "var(--primary, #4f46e5)",
  error: "var(--destructive, #e5484d)",
  success: "var(--primary, #2e7d57)",
};

/**
 * Renders toasts raised via lib/toast at the top-center of the app. Mounted once
 * in the authenticated app shell ((app)/layout.js). Auto-dismisses after each
 * toast's duration; click × (or call dismissToast) to close early.
 */
export default function Toaster() {
  const [items, setItems] = useState([]);

  useEffect(() => {
    return subscribeToasts((ev) => {
      if (ev.type === "add") {
        setItems((cur) => [...cur, ev.toast]);
        if (ev.toast.duration > 0) {
          setTimeout(
            () => setItems((cur) => cur.filter((t) => t.id !== ev.toast.id)),
            ev.toast.duration,
          );
        }
      } else if (ev.type === "remove") {
        setItems((cur) => cur.filter((t) => t.id !== ev.id));
      }
    });
  }, []);

  if (!items.length) return null;

  return (
    <div
      role="region"
      aria-label="Notifications"
      style={{
        position: "fixed",
        top: 16,
        left: "50%",
        transform: "translateX(-50%)",
        zIndex: 9999,
        display: "flex",
        flexDirection: "column",
        gap: 10,
        width: "min(440px, calc(100vw - 32px))",
        pointerEvents: "none",
      }}
    >
      {items.map((t) => {
        const accent = VARIANT[t.variant] || VARIANT.default;
        return (
          <div
            key={t.id}
            role="alert"
            style={{
              pointerEvents: "auto",
              display: "flex",
              gap: 10,
              alignItems: "flex-start",
              background: "var(--popover, var(--card, #15151b))",
              color: "var(--popover-foreground, var(--foreground, #f4f4f5))",
              border: "1px solid var(--border, rgba(127,127,127,0.25))",
              borderLeft: `3px solid ${accent}`,
              borderRadius: 10,
              padding: "12px 14px",
              boxShadow: "0 10px 30px rgba(0,0,0,0.35)",
              fontSize: 14,
              lineHeight: 1.4,
            }}
          >
            <div style={{ flex: 1, minWidth: 0 }}>
              {t.title && <div style={{ fontWeight: 600, marginBottom: 2 }}>{t.title}</div>}
              <div style={{ opacity: t.title ? 0.85 : 1, wordBreak: "break-word" }}>{t.message}</div>
            </div>
            <button
              type="button"
              aria-label="Dismiss notification"
              onClick={() => dismissToast(t.id)}
              style={{
                background: "transparent",
                border: "none",
                color: "inherit",
                cursor: "pointer",
                opacity: 0.6,
                fontSize: 16,
                lineHeight: 1,
                padding: 2,
              }}
            >
              ×
            </button>
          </div>
        );
      })}
    </div>
  );
}
