"use client";

// The one card shape on the Connections page.
//
// Every connector and model provider gets the same tile: logo, name, one line
// of what it's for, and its live state. Setup happens in a dialog
// (`ConnectorDialog`), never inline, so the grid stays scannable no matter how
// many fields a given connector needs.
//
// The card is a container, not a button. It was a <button> wrapping the whole
// thing, which put the storage glyph's tooltip trigger — itself a button —
// inside it. React refuses to hydrate that ("<button> cannot be a descendant
// of <button>"), and the HTML parser had already moved the inner one out of
// the card before React ever saw it. The fix is the pattern AGENTS.md
// prescribes for exactly this: the button goes on the title and stretches
// over the card with a pseudo-element. One tab stop, one readable name, and
// anything that needs its own interaction just sits above it.

import { ChevronRight } from "lucide-react";
import StorageBadge from "./StorageBadge";

/**
 * @param tone  "on" | "partial" | "off" — drives the status dot's colour.
 * @param status  Short state line, e.g. "Connected — Acme Ads".
 * @param storage  STORAGE_* constant — where the credential lives. On the tile
 *   rather than only in the dialog because "saved to your account" and "living
 *   in this tab" are indistinguishable from outside, and the difference is the
 *   whole reason a connection appears to vanish.
 */
export default function ConnectorTile({
  logo,
  title,
  description,
  tone = "off",
  status,
  storage,
  onClick,
  disabled = false,
}) {
  const dotTone = tone === "on" ? " conn-dot--on" : tone === "partial" ? " conn-dot--partial" : "";

  return (
    <div className={`conn-tile${disabled ? " is-disabled" : ""}`}>
      <span className="conn-tile-logo" aria-hidden="true">
        {logo}
      </span>
      <div className="conn-tile-body">
        <div className="conn-tile-top">
          {disabled ? (
            <span className="conn-tile-title">{title}</span>
          ) : (
            // The visible text is the title, so the accessible name has to
            // contain it verbatim (WCAG 2.5.3) — "Configure X", not "Open
            // settings".
            <button
              type="button"
              className="conn-tile-title conn-tile-open"
              onClick={onClick}
              aria-label={`Configure ${title}`}
            >
              {title}
            </button>
          )}
          {!disabled && (
            <ChevronRight className="conn-tile-chevron" size={16} aria-hidden="true" />
          )}
        </div>
        <p className="conn-tile-desc">{description}</p>
        <div className={`conn-tile-foot${tone === "on" ? " conn-tile-foot--on" : ""}`}>
          <span className={`conn-dot${dotTone}`} />
          {/* State on the left, where it is read; where the credential lives
              on the right. The word stays even when the dot is green — the dot
              alone made the left half of the row look empty, and colour is
              never the only channel anyway (WCAG 1.4.1). It used to clip to
              "Connec…" because a full-width pill sat beside it; the pill is a
              24px glyph now, so the room exists. */}
          <span className="conn-tile-foot-text">{status}</span>
          <StorageBadge storage={storage} />
        </div>
      </div>
    </div>
  );
}
