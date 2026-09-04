"use client";

// "Where does this credential actually live?" — one glyph, used by every card
// on the Connections page so the answer reads the same everywhere.
//
// It was a pill reading "Saved to your account", which is a sentence competing
// with the status pill beside it for the same glance. But the answer only has
// four values and three of them are reassuring; the one that matters — this
// disappears when you close the app — deserves to stand out, and cannot while
// it is one green pill among several. So: an icon, in the row's own colour,
// with the sentence on hover and on focus for anyone who needs it.
//
// Still a real <button> rather than a decorated <span>: it carries information
// nothing else on the card carries, so it has to be reachable by keyboard.

import {
  STORAGE_DETAIL,
  STORAGE_KEYCHAIN,
  STORAGE_LABELS,
  STORAGE_LOCAL,
  STORAGE_NONE,
  STORAGE_SESSION,
  STORAGE_TONE,
} from "../../lib/credentialStorage";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

/** 16px line icons, one per answer. `currentColor` so tone drives the colour. */
function StorageIcon({ storage }) {
  const common = {
    viewBox: "0 0 16 16",
    width: 15,
    height: 15,
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.4,
    strokeLinecap: "round",
    strokeLinejoin: "round",
    "aria-hidden": true,
  };
  if (storage === STORAGE_LOCAL) {
    // A laptop: this machine, and only this machine.
    return (
      <svg {...common}>
        <rect x="2.5" y="3" width="11" height="7.5" rx="1" />
        <path d="M1 12.75h14" />
      </svg>
    );
  }
  if (storage === STORAGE_KEYCHAIN) {
    // A padlock: held by the OS, not by us.
    return (
      <svg {...common}>
        <rect x="3.5" y="7" width="9" height="6.5" rx="1.5" />
        <path d="M5.75 7V5.25a2.25 2.25 0 0 1 4.5 0V7" />
      </svg>
    );
  }
  if (storage === STORAGE_SESSION) {
    // A clock: the only one of the four with an expiry.
    return (
      <svg {...common}>
        <circle cx="8" cy="8" r="5.75" />
        <path d="M8 4.75V8l2.25 1.5" />
      </svg>
    );
  }
  // A cloud: reachable without this machine awake.
  return (
    <svg {...common}>
      <path d="M4.75 12.25a3 3 0 0 1-.4-5.97 3.75 3.75 0 0 1 7.2-.53 2.75 2.75 0 0 1 .2 5.44 3 3 0 0 1-.5.06z" />
    </svg>
  );
}

/**
 * @param storage  one of the STORAGE_* constants.
 * @param detail   also render the explanatory sentence as visible text. For the
 *                 dialog, where there is room; the tile relies on the tooltip.
 */
export default function StorageBadge({ storage, detail = false }) {
  if (!storage || storage === STORAGE_NONE) return null;
  const label = STORAGE_LABELS[storage];
  if (!label) return null;
  const sentence = STORAGE_DETAIL[storage];

  return (
    <>
      {/* No local Provider: the root layout already wraps the whole app in one
          (`app/layout.js`). A second one here was not merely redundant — it
          overrode `delayDuration` for this tooltip alone, so the storage glyph
          opened on a different beat from every other tooltip in the app. */}
      <Tooltip>
        <TooltipTrigger asChild>
          <button
            type="button"
            className={`conn-storage-icon tone-${STORAGE_TONE[storage] || "grey"}`}
            // The label is the accessible name, so a screen reader gets "Saved
            // to your account" rather than "button". The sentence follows in
            // the tooltip, which Radix wires up as the description.
            aria-label={label}
          >
            <StorageIcon storage={storage} />
          </button>
        </TooltipTrigger>
        {/* `TooltipContent` is an inline-flex ROW with `items-center` — built
            for one short line plus an optional key chip. Two paragraphs in it
            became two columns, so "Saved to your account" wrapped into a
            narrow stack beside its own explanation. Stacking is the fix, not
            a wider box. */}
        <TooltipContent side="top" className="flex-col items-start gap-0.5">
          <span className="font-medium">{label}</span>
          <span className="opacity-80">{sentence}</span>
        </TooltipContent>
      </Tooltip>
      {detail && <p className="conn-hint">{sentence}</p>}
    </>
  );
}
