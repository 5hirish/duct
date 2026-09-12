"use client";

/**
 * The three settings that were stacked under the tier cards, folded away.
 *
 * All three are on-by-default or server-resolved: quota fallback, context
 * compression, and which key draws images. None of them is a decision anyone
 * arrives at this page to make, and together they were roughly half its
 * scroll and a third of its words — an "Advanced" fold is what that pile
 * actually is.
 *
 * `<details>` rather than a Radix collapsible: it is a disclosure, the element
 * exists, and it keeps working with JavaScript still loading.
 */

import AutoFallbackCard from "@/components/AutoFallbackCard";
import ContextCompressionCard from "@/components/ContextCompressionCard.jsx";
import ModalityRows from "./ModalityRows";

export default function AdvancedSettings({ ladder, images, catalogue, providersById, sharedSource = "" }) {
  return (
    <details className="mt-advanced">
      <summary>
        <span className="mt-advanced-title">Advanced</span>
        <span className="mt-advanced-hint">
          Quota fallback, context compression, and which key draws images
        </span>
      </summary>

      <div className="mt-advanced-body">
        <AutoFallbackCard ladder={ladder} />
        <ContextCompressionCard />
        <ModalityRows
          images={images}
          catalogue={catalogue}
          providersById={providersById}
          sharedSource={sharedSource}
        />
      </div>
    </details>
  );
}
