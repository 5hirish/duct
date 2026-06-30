"use client";

import { useId, useRef, useState } from "react";

const MAX = 8;

/**
 * Themed autocomplete input — a tiny combobox built from plain React + Tailwind
 * (no cmdk / no dependency, no network). Suggests from `options` as you type,
 * fully keyboard-navigable, and — unlike a native <datalist> — themed to match
 * the app. Free-typeable: the value isn't restricted to the option list.
 *
 * Props:
 *   - value, onChange : controlled string
 *   - options         : string[] suggestions
 *   - placeholder
 *   - className       : applied to the wrapper (controls width); the input fills it
 */
export default function ComboInput({ value, onChange, options = [], placeholder = "", className = "" }) {
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  const blurTimer = useRef(null);
  const listId = useId();

  const q = (value || "").trim().toLowerCase();
  const matches = (q ? options.filter((o) => o.toLowerCase().includes(q)) : options).slice(0, MAX);
  // Hide once the input already equals the only match (nothing left to pick).
  const showList = open && matches.length > 0 && !(matches.length === 1 && matches[0].toLowerCase() === q);

  function choose(opt) {
    onChange(opt);
    setOpen(false);
    setActive(-1);
  }

  function onKeyDown(e) {
    if (e.key === "ArrowDown" && !showList) { setOpen(true); return; }
    if (!showList) return;
    if (e.key === "ArrowDown") { e.preventDefault(); setActive((a) => Math.min(a + 1, matches.length - 1)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setActive((a) => Math.max(a - 1, 0)); }
    else if (e.key === "Enter" && active >= 0) { e.preventDefault(); choose(matches[active]); }
    else if (e.key === "Escape") { setOpen(false); setActive(-1); }
  }

  return (
    <div className={`relative ${className}`}>
      <input
        value={value}
        onChange={(e) => { onChange(e.target.value); setOpen(true); setActive(-1); }}
        onFocus={() => setOpen(true)}
        onBlur={() => { blurTimer.current = setTimeout(() => setOpen(false), 120); }}
        onKeyDown={onKeyDown}
        placeholder={placeholder}
        role="combobox"
        aria-expanded={showList}
        aria-controls={listId}
        aria-autocomplete="list"
        autoComplete="off"
        className="w-full rounded-lg border border-input bg-input/40 px-2 py-1 text-xs outline-none transition-[box-shadow,border-color] focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring/25"
      />
      {showList && (
        <ul
          id={listId}
          role="listbox"
          // preventDefault on mousedown keeps the input focused so the click lands.
          onMouseDown={(e) => { e.preventDefault(); clearTimeout(blurTimer.current); }}
          className="absolute left-0 top-full z-50 mt-1 max-h-56 w-48 overflow-auto rounded-lg border border-border bg-popover p-1 text-popover-foreground shadow-md"
        >
          {matches.map((opt, i) => (
            <li
              key={opt}
              role="option"
              aria-selected={i === active}
              onMouseEnter={() => setActive(i)}
              onClick={() => choose(opt)}
              className={`cursor-pointer truncate rounded-md px-2 py-1.5 text-xs transition-colors ${
                i === active ? "bg-accent text-accent-foreground" : "hover:bg-accent/60"
              }`}
            >
              {opt}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
