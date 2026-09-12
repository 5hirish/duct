"use client";

/**
 * Images: which key draws, resolved by the server.
 *
 * Used to print `gemini-3.1-flash-image` as a literal beside the Gemini mark,
 * which read as a rule — and sent people on an OpenAI or xAI key to Google
 * for something their own key already does. The server now answers with its
 * pick (same preference order the run uses: Gemini, then OpenAI, then xAI),
 * and this renders whatever came back. `catalogue.image_models` lists the
 * providers that can draw at all, for the empty state and the hint.
 *
 * It is a `conn-panel` — the same shell as the two switches it sits under.
 * It had its own: a smaller icon tile, a tighter radius, and a note that ran
 * the full width of the card instead of starting at the text column, so three
 * rows in one fold were built out of two different anatomies and the third
 * one's left rail did not line up with anything. DESIGN.md's canon table
 * names that shape ("Card: rounded-xl border bg-card") and lists the
 * hand-rolled alternatives as close-on-touch; this was one of them.
 *
 * Video used to sit beside it as a matching row with a "Not connected" pill.
 * A row whose entire content is that it does nothing, wearing a pill that
 * encodes no state anyone can change from here, is furniture — it is the last
 * line of this card now.
 */

import { useMemo } from "react";
import { ImageIcon } from "lucide-react";
import StateChip from "./StateChip";
import { ProviderMark } from "./ModelPicker";
import { SOURCE_DETAIL, SOURCE_LABELS, SOURCE_TONE, modelLabel } from "@/lib/modelTiers";

/**
 * `sharedSource` is what the page already said about whose key pays. When the
 * image pick agrees with it, this row does not repeat it — the same rule the
 * tier cards follow, and the reason the old page said "This computer's key"
 * four times on one screen.
 */
export default function ModalityRows({ images, catalogue, providersById, sharedSource = "" }) {
  const imageProviders = useMemo(() => {
    const order = catalogue?.image_provider_order ?? [];
    const seen = new Set((catalogue?.image_models ?? []).map((model) => model.provider));
    return order.filter((id) => seen.has(id));
  }, [catalogue]);
  // Before the catalogue answers there is nothing to list; the three names
  // are the ones the server would send, not a second copy of the rule.
  const providerNames = (imageProviders.length
    ? imageProviders.map((id) => providersById[id]?.label || id)
    : ["Google Gemini", "OpenAI", "xAI"]
  )
    .join(", ")
    .replace(/, ([^,]*)$/, " or $1");
  const picked = images?.provider ? images : null;
  const pickedLabel = picked ? providersById[picked.provider]?.label || picked.provider : "";
  const others = imageProviders.filter((id) => id !== picked?.provider && providersById[id]?.reachable);

  // The name, not the id — this sits in the same fold as three pickers that
  // all show names now.
  const pickedModel = picked
    ? modelLabel((catalogue?.image_models ?? []).find((model) => model.id === picked.model)) ||
      picked.model
    : "";

  let note;
  if (!images) {
    note = "Checking which of your keys can draw…";
  } else if (!picked) {
    note = `None of your tier models generate images. Add a ${providerNames} key and Duct will draw with it.`;
  } else if (others.length) {
    note = `Drawing with your ${pickedLabel} key. Your ${others
      .map((id) => providersById[id]?.label || id)
      .join(" and ")} key${others.length > 1 ? "s" : ""} can draw too; ${pickedLabel} comes first when more than one is set.`;
  } else {
    note = `None of your tier models generate images, so Duct draws with your ${pickedLabel} key.`;
  }

  return (
    <article className="conn-panel">
      <span className="conn-tile-logo" aria-hidden="true">
        <ImageIcon size={20} strokeWidth={1.7} />
      </span>
      <div className="conn-tile-body">
        <div className="conn-tile-top">
          <span className="conn-tile-title">Images</span>
          {picked ? (
            <span className="mt-mod-pick">
              <ProviderMark providerId={picked.provider} />
              <span>{pickedModel}</span>
              {/* Only when it is news. `sharedSource` is the answer the page
                  gave at the top; repeating it here taught nobody anything. */}
              {picked.source !== sharedSource && (
                <StateChip
                  tone={SOURCE_TONE[picked.source] || "ok"}
                  title={`${SOURCE_DETAIL[picked.source] || ""} — chosen for you, no tier model can generate images`}
                >
                  {SOURCE_LABELS[picked.source] || "Auto"}
                </StateChip>
              )}
            </span>
          ) : (
            <StateChip tone={images ? "warn" : "neutral"}>{images ? "Needs a key" : "Checking"}</StateChip>
          )}
        </div>
        <p className="conn-tile-desc">{note}</p>
        <p className="conn-tile-desc">
          Video is a connected service rather than a model you pick here.
        </p>
      </div>
    </article>
  );
}
