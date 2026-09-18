"use client";

/**
 * What the Models page opens with: the setup you already have, in three lines.
 *
 * The page this replaces opened with the *decision* — three dropdowns of raw
 * model ids, a fallback diagram, and 300-odd words explaining them — and put
 * the thing almost everyone actually wants ("I have one key, use it") at the
 * bottom, phrased as a rescue: "Only have one key?". Most people bring one
 * key. So one key is the front door now, and the three-way choice is behind
 * Customise for the people who want it.
 *
 * Nothing was deleted from the model: the tiers are still real, still three,
 * still resolved by the server. This is the same state, read rather than
 * operated.
 */

import { Button } from "@/components/ui/button";
import ModelPicker, { ProviderMark } from "./ModelPicker";
import { SOURCE_SENTENCE, TIERS, agreedSource, modelLabel } from "@/lib/modelTiers";

export default function TierSummary({
  picks,
  models,
  providersById,
  previewByTier,
  loading,
  expanded,
  onToggle,
  fillable = [],
  onFill,
  configuredCount = 0,
  onReset,
  images,
  imageModels = [],
  imagePick = "",
  onImageChange,
}) {
  const rows = TIERS.map((tier) => {
    const id = picks[tier.key];
    return {
      tier,
      model: models.find((entry) => entry.id === id) || (id ? { id } : null),
      preview: previewByTier[tier.key],
    };
  });

  const providerIds = rows.map((row) => row.model?.provider).filter(Boolean);
  // One provider across all three is the ordinary case and the one worth
  // naming in the heading — it is the answer to "whose models am I on".
  const onePr = providerIds.length === TIERS.length && new Set(providerIds).size === 1;
  const provider = onePr ? providersById[providerIds[0]] : null;
  // Short on purpose: this is the one line that has to survive a phone width,
  // and "Models from more than one provider" truncated to "Models from more
  // than one…", which says less than nothing. The rows below carry a mark
  // each in this case, so the heading does not have to name them.
  const heading = loading
    ? "Loading your models…"
    : provider?.label || (onePr ? providerIds[0] : "Mixed providers");

  const blocked = rows.find((row) => row.preview && !row.preview.runnable);
  // The credential answer, said once for the page. The tier cards repeat it
  // per-card only when the three disagree, and both sides read `sourcesAgree`
  // so the page cannot both say it once and say it three times.
  const shared = agreedSource(previewByTier, providersById);
  const resolved = rows.some((row) => row.preview);

  // The server answers with an id; this page says names everywhere else, and
  // switching to an id mid-sentence reads as a different kind of thing. Both
  // catalogues, because the image models are not in `models` and the first
  // version of this looked them up there and printed the id every time.
  const nameOf = (id) => {
    const model =
      models.find((entry) => entry.id === id) || imageModels.find((entry) => entry.id === id);
    return model ? modelLabel(model) : id;
  };

  let note = "";
  if (blocked) {
    const serves = blocked.preview.serves;
    note = serves
      ? `${blocked.tier.label} has no key, so that work runs on ${nameOf(serves.model)} instead.`
      : `${blocked.tier.label} has no key and nothing below it can run either.`;
  } else if (shared) {
    note = SOURCE_SENTENCE[shared] || "";
  } else if (resolved) {
    note = "Your three tiers run on different keys — open Customise to see which.";
  }

  // What "let Duct choose" resolves to right now, said in the option itself —
  // a picker whose default option is the word "Auto" makes the reader open a
  // second surface to find out what Auto meant.
  const drawn = images?.model
    ? nameOf(images.model) || images.model
    : "";
  // "Auto" alone would send the reader somewhere else to find out what it
  // meant; the resolved name is the answer, so it is in the label. Kept short
  // because this shares its string with the trigger, which is one line wide.
  const autoImageLabel = drawn ? `Auto · ${drawn}` : "Auto — whichever key can draw";

  // Only when something is wrong. A working image pick is already on screen.
  let imageNote = "";
  if (images && !images.provider) {
    // Naming the plan matters here: their OpenAI tile is green, so "no key of
    // yours can draw" reads as a bug rather than as an answer. The plan
    // reaches the Codex backend and the image API is a different door — see
    // agents/engines.resolve_image_run.
    imageNote =
      providersById?.openai?.source === "subscription"
        ? "Your ChatGPT plan can run the chat models but cannot generate images — add an image key on the Providers tab."
        : "No key of yours can generate images yet — add one on the Providers tab.";
  } else if (imagePick && images?.model && imagePick !== images.model) {
    // The server resolved past the pick: its provider has no spendable key.
    imageNote = `No key for ${nameOf(imagePick) || imagePick}, so images are drawn with ${drawn}.`;
  }

  return (
    <>
      <article className={`mt-setup${blocked ? " mt-setup--blocked" : ""}`}>
        <div className="mt-setup-head">
          {onePr && <ProviderMark providerId={providerIds[0]} className="mt-mark mt-setup-mark" />}
          <h2>{heading}</h2>
          <Button type="button" variant="outline" size="sm" onClick={onToggle}>
            {expanded ? "Done" : "Customise"}
          </Button>
        </div>

        <dl className="mt-setup-list">
          {rows.map(({ tier, model, preview }) => (
            <div key={tier.key} className="mt-setup-row">
              <dt>{tier.label}</dt>
              <dd>
                {/* Marks only when they distinguish something. On a single-
                    provider setup the heading already carries the vendor, and
                    three copies of one logo is decoration. */}
                {!onePr && model?.provider && <ProviderMark providerId={model.provider} />}
                <span className={preview && !preview.runnable ? "mt-setup-dead" : undefined}>
                  {model ? modelLabel(model) : "—"}
                </span>
              </dd>
            </div>
          ))}

          {/* Images is the fourth thing Duct runs on your key, so it belongs in
              the list of what Duct runs on your key — it was in an Advanced
              fold, two clicks from the three rows it is a peer of.

              It is set apart by a rule because it is not a tier: nothing falls
              through to it and nothing falls through from it. An empty pick is
              "whichever of my keys can draw", which is why the picker offers
              `AUTO_IMAGE` as a real option rather than leaving the control
              blank — blank reads as broken, and this is the state most people
              are in and should stay in. */}
          <div className="mt-setup-row mt-setup-row--aside">
            <dt>Images</dt>
            <dd>
              <ModelPicker
                id="image-model"
                label="Model for generating images"
                loading={loading}
                value={imagePick}
                models={imageModels}
                providersById={providersById}
                autoOption={autoImageLabel}
                onChange={onImageChange}
              />
            </dd>
          </div>
        </dl>

        {note && <p className="mt-setup-note">{note}</p>}
        {imageNote && <p className="mt-setup-note">{imageNote}</p>}
      </article>

      <div className="mt-actions">
        <span className="mt-actions-label">Use one provider for all three</span>
        {fillable.map((entry) => {
          const current = onePr && entry.statusId === providerIds[0];
          return (
            <Button
              key={entry.id}
              type="button"
              variant={current ? "secondary" : "outline"}
              size="sm"
              // Not disabled: re-picking your current provider is how you get
              // back to its recommended triple after changing one tier by hand.
              onClick={() => onFill(entry.statusId)}
            >
              <ProviderMark providerId={entry.statusId} className="mt-mark mt-mark--sm" />
              {entry.label}
            </Button>
          );
        })}
        {configuredCount > 0 && (
          <Button type="button" variant="ghost" size="sm" onClick={onReset}>
            Reset to defaults
          </Button>
        )}
      </div>
    </>
  );
}
