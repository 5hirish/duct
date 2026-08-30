"use client";

// The one card shape on the Connections page.
//
// Every connector and model provider gets the same tile: logo, name, one line
// of what it's for, and its live state. The whole tile is the click target —
// setup happens in a dialog (`ConnectorDialog`), never inline, so the grid
// stays scannable no matter how many fields a given connector needs.

import { ChevronRight } from "lucide-react";

/**
 * @param tone  "on" | "partial" | "off" — drives the status dot's colour.
 * @param status  Short state line, e.g. "Connected — Acme Ads".
 */
export default function ConnectorTile({
  logo,
  title,
  description,
  tone = "off",
  status,
  onClick,
  disabled = false,
}) {
  const dotTone = tone === "on" ? " conn-dot--on" : tone === "partial" ? " conn-dot--partial" : "";

  return (
    <button
      type="button"
      className="conn-tile"
      onClick={onClick}
      disabled={disabled}
      aria-label={disabled ? title : `Configure ${title}`}
    >
      <span className="conn-tile-logo" aria-hidden="true">
        {logo}
      </span>
      <span className="conn-tile-body">
        <span className="conn-tile-top">
          <span className="conn-tile-title">{title}</span>
          {!disabled && (
            <ChevronRight className="conn-tile-chevron" size={16} aria-hidden="true" />
          )}
        </span>
        <span className="conn-tile-desc">{description}</span>
        <span className={`conn-tile-foot${tone === "on" ? " conn-tile-foot--on" : ""}`}>
          <span className={`conn-dot${dotTone}`} />
          <span className="conn-tile-foot-text">{status}</span>
        </span>
      </span>
    </button>
  );
}
