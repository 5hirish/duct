"use client";

function titleForFindingType(type) {
  if (type === "risk") return "Risk";
  if (type === "win") return "Win";
  return "Watch";
}

export default function SignalListBlock({ title, synthesis, insightNote = "" }) {
  const items = [...(synthesis?.risks || []), ...(synthesis?.highlights || [])];
  if (!items.length) return null;

  return (
    <section>
      <p className="rpt-section-label">{title || "Signals"}</p>
      <div className="signal-grid">
        {items.map((finding) => (
          <article key={finding.id} className="signal-block">
            <span className="signal-pill yellow">{titleForFindingType(finding.type)}</span>
            <p className="signal-title">{finding.title}</p>
            <p className="signal-body">{finding.impact}</p>
            {finding.recommended_action ? (
              <p className="signal-body">
                <strong>Action:</strong> {finding.recommended_action}
              </p>
            ) : null}
          </article>
        ))}
      </div>
      {insightNote ? <p className="rpt-meta">{insightNote}</p> : null}
    </section>
  );
}
