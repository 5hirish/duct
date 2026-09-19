"use client";

import { Trans, useLingui } from "@lingui/react/macro";

// Takes `t`: it runs outside the component, and the pill is copy.
function titleForFindingType(t, type) {
  if (type === "risk") return t`Risk`;
  if (type === "win") return t`Win`;
  return t`Watch`;
}

export default function SignalListBlock({ title, synthesis, insightNote = "" }) {
  const { t } = useLingui();
  const items = [...(synthesis?.risks || []), ...(synthesis?.highlights || [])];
  if (!items.length) return null;

  return (
    <section>
      <p className="rpt-section-label">{title || t`Signals`}</p>
      <div className="signal-grid">
        {items.map((finding) => {
          const action = finding.recommended_action;
          return (
            <article key={finding.id} className="signal-block">
              <span className="signal-pill yellow">{titleForFindingType(t, finding.type)}</span>
              <p className="signal-title">{finding.title}</p>
              <p className="signal-body">{finding.impact}</p>
              {action ? (
                <p className="signal-body">
                  <Trans><strong>Action:</strong> {action}</Trans>
                </p>
              ) : null}
            </article>
          );
        })}
      </div>
      {insightNote ? <p className="rpt-meta">{insightNote}</p> : null}
    </section>
  );
}
