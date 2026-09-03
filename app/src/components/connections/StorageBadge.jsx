"use client";

// "Where does this credential actually live?" — one badge, used by every card
// on the Connections page so the answer reads the same everywhere.
//
// It exists because the honest answer used to be buried in a sentence inside a
// dialog, and the two states people most need to tell apart look identical
// from outside: a connector saved to the account and one that only exists in
// this browser tab both render as "Connected" right up until the tab closes.

import { STORAGE_DETAIL, STORAGE_LABELS, STORAGE_NONE, STORAGE_TONE } from "../../lib/credentialStorage";

/**
 * @param storage  one of the STORAGE_* constants.
 * @param detail   render the explanatory clause under the badge.
 */
export default function StorageBadge({ storage, detail = false }) {
  if (!storage || storage === STORAGE_NONE) return null;
  const label = STORAGE_LABELS[storage];
  if (!label) return null;

  return (
    <>
      <span
        // Its own class as well as status-pill: the shared pill capitalizes
        // every word, which turns "This session" into "This Session".
        className={`status-pill conn-storage-pill ${STORAGE_TONE[storage] || "grey"}`}
        // The label alone is terse by design — the tile has no room for a
        // clause — so the full sentence rides along for anyone hovering or
        // using a screen reader.
        title={STORAGE_DETAIL[storage]}
      >
        {label}
      </span>
      {detail && <p className="conn-hint">{STORAGE_DETAIL[storage]}</p>}
    </>
  );
}
