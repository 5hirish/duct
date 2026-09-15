"use client";

/**
 * The settings that were stacked under the tier cards, folded away.
 *
 * Both are on by default and neither is a decision anyone arrives at this page
 * to make; together with the image row they were roughly half its scroll and a
 * third of its words. The image row has since moved back out and into the
 * summary card — it turned out to be a model choice like the other three, not
 * a preference like these two, and that is the line this fold draws.
 *
 * `<details>` rather than a Radix collapsible: it is a disclosure, the element
 * exists, and it keeps working with JavaScript still loading.
 */

import AutoFallbackCard from "@/components/AutoFallbackCard";
import ContextCompressionCard from "@/components/ContextCompressionCard.jsx";

export default function AdvancedSettings({ ladder }) {
  return (
    <details className="mt-advanced">
      <summary>
        <span className="mt-advanced-title">Advanced</span>
        <span className="mt-advanced-hint">
          Quota fallback and context compression
        </span>
      </summary>

      <div className="mt-advanced-body">
        <AutoFallbackCard ladder={ladder} />
        <ContextCompressionCard />
      </div>
    </details>
  );
}
