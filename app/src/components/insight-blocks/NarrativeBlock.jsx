"use client";

export default function NarrativeBlock({ title, synthesis, insightNote = "" }) {
  const narrative = synthesis?.narrative;
  if (!narrative) return null;

  return (
    <section className="rpt-header">
      {title ? <p className="rpt-section-label">{title}</p> : null}
      <div className="rpt-verdict green">{narrative.verdict}</div>
      <p className="rpt-summary">{narrative.summary}</p>
      <p className="rpt-summary">Operator takeaway: {narrative.takeaway}</p>
      {insightNote ? <p className="rpt-meta">{insightNote}</p> : null}
    </section>
  );
}
