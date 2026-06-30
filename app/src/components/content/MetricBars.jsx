"use client";

import { useRef } from "react";
import { Plus, Scale, Trash2 } from "lucide-react";
import ComboInput from "./ComboInput";

const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
const round1 = (v) => Math.round(v * 10) / 10;

/**
 * Draggable %-breakdown bars (gender, age, traffic, locations, search queries).
 * Each row is a bar you drag to set the share — or tap the number for an exact
 * value. A live Total + one-tap "Balance to 100%" keeps a distribution honest.
 *
 * Props:
 *   - items        : [{ key, value }]  (value 0–100; "" allowed)
 *   - onChange     : (items) => void
 *   - editableKeys : true → free-form rows (editable label + add/remove); false → fixed labels
 *   - keyPlaceholder : placeholder for a free-form label ("Country", "Search term")
 *   - keyOptions   : optional string[] — themed ComboInput autocomplete for the label
 *                    (still free-typeable). Used for the country list.
 *   - balance      : show the "Balance to 100%" action (for distributions that sum to 100)
 */
export default function MetricBars({ items, onChange, editableKeys = false, keyPlaceholder = "", keyOptions, balance = false }) {
  const dragging = useRef(false);
  const hasOptions = Array.isArray(keyOptions) && keyOptions.length > 0;

  const setVal = (i, value) => onChange(items.map((it, j) => (j === i ? { ...it, value } : it)));
  const setKey = (i, key) => onChange(items.map((it, j) => (j === i ? { ...it, key } : it)));
  const addRow = () => onChange([...(items || []), { key: "", value: "" }]);
  const removeRow = (i) => onChange(items.filter((_, j) => j !== i));

  function trackSet(e, i) {
    const r = e.currentTarget.getBoundingClientRect();
    const val = Math.round(clamp((e.clientX - r.left) / r.width, 0, 1) * 100);
    setVal(i, val);
  }
  const down = (e, i) => { dragging.current = true; e.currentTarget.setPointerCapture?.(e.pointerId); trackSet(e, i); };
  const move = (e, i) => { if (dragging.current) trackSet(e, i); };
  const up = (e) => { dragging.current = false; try { e.currentTarget.releasePointerCapture?.(e.pointerId); } catch { /* ignore */ } };

  const total = (items || []).reduce((a, it) => a + (Number(it.value) || 0), 0);
  const balanced = Math.abs(total - 100) <= 1;

  function balanceTo100() {
    const sum = (items || []).reduce((a, it) => a + (Number(it.value) || 0), 0);
    if (!sum) return;
    onChange(items.map((it) => ({ ...it, value: round1(((Number(it.value) || 0) / sum) * 100) })));
  }

  return (
    <div className="space-y-1.5">
      {(items || []).map((it, i) => (
        <div key={i} className="flex items-center gap-2">
          {editableKeys && hasOptions ? (
            <ComboInput
              value={it.key}
              onChange={(v) => setKey(i, v)}
              options={keyOptions}
              placeholder={keyPlaceholder}
              className="w-24 shrink-0"
            />
          ) : editableKeys ? (
            <input
              value={it.key}
              onChange={(e) => setKey(i, e.target.value)}
              placeholder={keyPlaceholder}
              autoComplete="off"
              className="w-24 shrink-0 rounded-lg border border-input bg-input/40 px-2 py-1 text-xs outline-none transition-[box-shadow,border-color] focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring/25"
            />
          ) : (
            <span className="w-24 shrink-0 truncate text-[11px] text-muted-foreground" title={it.key}>{it.key}</span>
          )}

          <div
            onPointerDown={(e) => down(e, i)}
            onPointerMove={(e) => move(e, i)}
            onPointerUp={up}
            onPointerCancel={up}
            className="relative h-7 flex-1 cursor-ew-resize overflow-hidden rounded-lg bg-muted ring-1 ring-inset ring-border/60"
            style={{ touchAction: "none" }}
            role="slider"
            aria-label={it.key || keyPlaceholder}
            aria-valuenow={Number(it.value) || 0}
            aria-valuemin={0}
            aria-valuemax={100}
          >
            <div
              className="absolute inset-y-0 left-0 bg-primary/70 transition-[width] duration-75"
              style={{ width: `${clamp(Number(it.value) || 0, 0, 100)}%` }}
            />
          </div>

          <div className="flex w-[3.75rem] shrink-0 items-center gap-0.5">
            <input
              type="number"
              inputMode="decimal"
              min={0}
              max={100}
              step={0.1}
              value={it.value}
              onChange={(e) => setVal(i, e.target.value)}
              placeholder="—"
              className="w-full rounded-lg border border-input bg-input/40 px-1.5 py-1 text-xs tabular-nums outline-none transition-[box-shadow,border-color] focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring/25"
            />
            <span className="text-[10px] text-muted-foreground">%</span>
          </div>

          {editableKeys && (
            <button
              type="button"
              onClick={() => removeRow(i)}
              aria-label="Remove row"
              className="flex size-7 shrink-0 items-center justify-center rounded-lg text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
            >
              <Trash2 className="size-3.5" />
            </button>
          )}
        </div>
      ))}

      <div className="flex items-center justify-between pt-0.5">
        {editableKeys ? (
          <button type="button" onClick={addRow} className="inline-flex items-center gap-1 text-[11px] font-medium text-primary hover:underline">
            <Plus className="size-3" /> Add {keyPlaceholder.toLowerCase()}
          </button>
        ) : <span />}
        {(items || []).length > 0 && (
          <div className="flex items-center gap-2 text-[10px] text-muted-foreground">
            <span>Total <span className={`font-medium tabular-nums ${balanced ? "text-emerald-500" : "text-foreground"}`}>{round1(total)}%</span></span>
            {balance && !balanced && total > 0 && (
              <button type="button" onClick={balanceTo100} className="inline-flex items-center gap-0.5 text-primary hover:underline">
                <Scale className="size-3" /> Balance to 100%
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
