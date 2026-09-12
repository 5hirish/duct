"use client";

/**
 * One tier, as a card. Only rendered once the reader has asked to customise —
 * the collapsed summary is what the page opens with.
 *
 * What used to be here and is not any more, with the reason each time:
 *
 *  * **The rank superscript.** Icon, name and position already said "these are
 *    ordered". A fourth encoding of one fact is not emphasis.
 *  * **The blurb, at full weight.** It is the honest explanation of the tier,
 *    so it moved into the disclosure with the job chips rather than being cut:
 *    an explanation belongs where someone goes looking for one.
 *  * **"Also the fallback for Heavy".** The chain drawn under these cards is
 *    the same claim, once, for all three.
 *  * **The credential chip, unconditionally.** `showSource` is false while all
 *    three tiers agree about who pays, which is the ordinary case; the summary
 *    says it once instead of this saying it three times.
 */

import { Anvil, Feather, Scale } from "lucide-react";
import ModelPicker from "./ModelPicker";
import StateChip from "./StateChip";
import { JOB_LABELS, SOURCE_DETAIL, SOURCE_LABELS, SOURCE_TONE, modelLabel } from "@/lib/modelTiers";

/** The tier's own mark. Anvil, balance scale, feather — heaviest to lightest. */
const TIER_ICONS = { anvil: Anvil, scale: Scale, feather: Feather };

export default function TierCard({
  tier,
  index,
  value,
  models,
  providersById,
  engine,
  jobs,
  preview,
  loading,
  showSource,
  onChange,
}) {
  const provider = providersById[preview?.provider] || null;
  const source = provider?.source || "none";
  const blocked = preview && !preview.runnable;
  const serves = preview?.serves;
  const offEngine = preview?.reason === "engine_unsupported";
  const TierIcon = TIER_ICONS[tier.icon] || Scale;
  const selected = models.find((model) => model.id === value);
  // The resolver answers with an id; the picker above shows a name, and the
  // promise under it should be in the same words.
  const servesName = serves
    ? modelLabel(models.find((model) => model.id === serves.model)) || serves.model
    : "";

  return (
    <div className={`mt-tier${index === 0 ? " mt-tier--lead" : ""}${blocked ? " mt-tier--blocked" : ""}`}>
      <div className="mt-tier-head">
        <span className={`mt-tier-mark mt-tier-mark--${tier.key}`} aria-hidden="true">
          <TierIcon size={17} strokeWidth={1.75} />
        </span>
        <div className="mt-tier-name">
          <h3>{tier.label}</h3>
          <p>{tier.tagline}</p>
        </div>
      </div>

      <div className="mt-tier-control">
        <ModelPicker
          id={`tier-${tier.key}`}
          label={`Model for the ${tier.label} tier`}
          loading={loading}
          value={value}
          models={models}
          providersById={providersById}
          engine={engine}
          onChange={(next) => onChange(tier.key, next)}
        />
        {/* The id, quietly. The picker now shows a human name, and the id is
            what a bug report and a provider dashboard are both keyed on. */}
        {selected && <p className="mt-tier-meta">{selected.id}</p>}
        {preview && (blocked || showSource) && (
          <StateChip
            tone={blocked ? "warn" : SOURCE_TONE[source] || "neutral"}
            title={blocked ? undefined : SOURCE_DETAIL[source]}
          >
            {blocked ? (offEngine ? "Not on this engine" : "No key") : SOURCE_LABELS[source] || "Ready"}
          </StateChip>
        )}
      </div>

      {/* The promise. Rendered from the server's own resolution, never from a
          guess about which keys this browser holds. */}
      {blocked && (
        <p className="mt-tier-fallback">
          {serves ? (
            <>
              {offEngine ? (
                <>This engine runs Anthropic models only, so </>
              ) : null}
              {offEngine ? tier.label.toLowerCase() : tier.label} jobs run on <b>{servesName}</b>
              {serves.engine_default ? " — this engine's default" : " until you add a key"}.
            </>
          ) : (
            <>Nothing below this tier can run either — add a key to use {tier.label}.</>
          )}
        </p>
      )}

      {/* Native <details>: this is an explanation someone opens on purpose,
          which is exactly the element's job, and it costs no primitive. The
          chips stayed flat on the card for a while and read as controls. */}
      {jobs.length > 0 && (
        <details className="mt-tier-jobs">
          <summary>What runs here</summary>
          <p className="mt-tier-blurb">{tier.blurb}</p>
          <div className="mt-tier-joblist">
            {jobs.map((job) => (
              <span key={job} className="mt-job">
                {JOB_LABELS[job] || job}
              </span>
            ))}
          </div>
        </details>
      )}
    </div>
  );
}
