"use client";

/**
 * The model dropdown, grouped by provider.
 *
 * Rows read "Gemini 3.8 Flash" rather than `gemini-3.8-flash`: the id is
 * punctuation a marketer has to decode before they can compare it to the row
 * above, and it is still one hover away on the trigger for the times it is
 * the thing you actually need.
 */

import { useMemo } from "react";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectLabel,
  SelectGroup,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { LOGOS } from "@/components/connections/logos";
import { Sparkles } from "lucide-react";
import { PROVIDER_LOGO_KEY, modelLabel } from "@/lib/modelTiers";

/**
 * The value Radix carries for "let Duct choose".
 *
 * Radix reserves the empty string for "nothing selected", so an option that
 * *means* empty needs a sentinel of its own. The caller never sees it: this
 * module maps it to `""` on the way out and back on the way in, so a saved
 * setting is still the empty string the backend already treats as "resolve
 * normally".
 */
export const AUTO_MODEL = "__auto__";

/**
 * A provider's mark at picker size.
 *
 * `LOGOS` entries are authored for the 24px connector tile and carry explicit
 * width/height attributes, so the wrapper has to size them down in CSS rather
 * than by prop.
 */
export function ProviderMark({ providerId, className = "mt-mark" }) {
  const logo = LOGOS[PROVIDER_LOGO_KEY[providerId] || providerId];
  if (!logo) return null;
  return (
    <span className={className} aria-hidden="true">
      {logo}
    </span>
  );
}

/**
 * Groups the picker by provider so "everything I have a key for" is one glance.
 *
 * Every model is listed, annotated rather than hidden. Filtering the list to
 * what the current engine accepts sounds tidier, and it was what this did
 * first — but an engine whose supported providers did not overlap the shipped
 * default triple emptied the list, and every picker rendered blank with
 * nothing to explain why. The row state on the card already says what will
 * actually run; the group label just has to be honest about why an option is
 * greyed.
 */
export default function ModelPicker({
  value,
  models,
  providersById,
  engine,
  onChange,
  id,
  label,
  loading,
  autoOption = "",
}) {
  const grouped = useMemo(() => {
    const byProvider = new Map();
    for (const model of models) {
      if (!byProvider.has(model.provider)) byProvider.set(model.provider, []);
      byProvider.get(model.provider).push(model);
    }
    // The provider you are already on leads, then whatever else is usable —
    // what you can actually run should never sit below what you cannot.
    const current = models.find((model) => model.id === value)?.provider;
    const rank = (providerId) => {
      if (providerId === current) return -1;
      const provider = providersById[providerId];
      const onEngine = (provider?.engines || []).includes(engine);
      return (provider?.reachable ? 0 : 2) + (onEngine ? 0 : 1);
    };
    return [...byProvider.entries()].sort(([a], [b]) => rank(a) - rank(b));
  }, [models, providersById, engine, value]);

  const note = (providerId) => {
    const provider = providersById[providerId];
    const flags = [];
    if (provider && !provider.reachable) flags.push("no key");
    if (provider && !(provider.engines || []).includes(engine)) flags.push(`not on ${engine}`);
    return flags.length ? ` · ${flags.join(", ")}` : "";
  };

  const selected = models.find((model) => model.id === value);

  return (
    <Select
      value={value || (autoOption ? AUTO_MODEL : "")}
      onValueChange={(next) => onChange(next === AUTO_MODEL ? "" : next)}
    >
      {/* The id lives in the tooltip, not the trigger. It is what a support
          thread needs and what nobody reading this page is choosing between. */}
      <SelectTrigger id={id} className="mt-select" aria-label={label} title={selected?.id}>
        {/* Not <SelectValue>: the trigger should carry the provider's mark too,
            so "which vendor am I on" is answerable without opening anything. */}
        {selected ? (
          <span className="mt-selected">
            <ProviderMark providerId={selected.provider} />
            <span className="mt-selected-id">{modelLabel(selected)}</span>
          </span>
        ) : loading ? (
          // Not "Choose a model": until the catalogue lands every tier *does*
          // have a model, and inviting a choice implies none is set.
          <span className="mt-selected mt-selected--loading">Loading models…</span>
        ) : autoOption ? (
          <span className="mt-selected">
            <Sparkles className="mt-mark" size={14} strokeWidth={1.75} aria-hidden="true" />
            <span className="mt-selected-id">{autoOption}</span>
          </span>
        ) : (
          <SelectValue placeholder="Choose a model" />
        )}
      </SelectTrigger>
      {/* `position="popper"`, not Radix's default `item-aligned`. Item-aligned
          positions the list by aligning the *selected item* over the trigger,
          and on grouped content it never resolves one: the wrapper is left
          without `left`/`bottom` and the list opens at the viewport's
          bottom-left corner, off-screen. Clicking the picker did nothing —
          this is the only `SelectGroup` in the app, so it was the only select
          that hit it. `DeskComposer` reaches for popper for the same reason.
          A settings picker wants to hang under its trigger anyway. */}
      <SelectContent position="popper" align="start" sideOffset={4} className="mt-select-list">
        {/* First, and deliberately not last: leaving Duct to choose is the
            state most people should stay in, and an option buried under seven
            model names reads as the thing you settle for. */}
        {autoOption && (
          <SelectItem value={AUTO_MODEL}>
            <span className="mt-option">
              <Sparkles className="mt-mark" size={14} strokeWidth={1.75} aria-hidden="true" />
              <span className="mt-option-id">{autoOption}</span>
            </span>
          </SelectItem>
        )}
        {grouped.map(([providerId, list]) => (
          <SelectGroup key={providerId}>
            <SelectLabel className="mt-group">
              <ProviderMark providerId={providerId} className="mt-mark mt-mark--sm" />
              <span>
                {providersById[providerId]?.label || providerId}
                {note(providerId)}
              </span>
            </SelectLabel>
            {list.map((model) => (
              <SelectItem key={model.id} value={model.id}>
                <span className="mt-option">
                  <ProviderMark providerId={model.provider} />
                  <span className="mt-option-id">{modelLabel(model)}</span>
                </span>
              </SelectItem>
            ))}
          </SelectGroup>
        ))}
      </SelectContent>
    </Select>
  );
}
