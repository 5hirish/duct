"use client";

export default function ActionListBlock({ title, synthesis, insightNote = "" }) {
  const actions = synthesis?.recommended_actions || [];
  if (!actions.length) return null;

  return (
    <section>
      <p className="rpt-section-label">{title || "Recommended actions"}</p>
      <div className="rpt-disclosure-panel">
        <ul style={{ margin: 0, paddingLeft: "1.2rem" }}>
          {actions.map((action) => (
            <li key={action.id} style={{ marginBottom: 8 }}>
              <strong>{action.title}</strong>
              {action.detail ? ` — ${action.detail}` : ""}
            </li>
          ))}
        </ul>
      </div>
      {insightNote ? <p className="rpt-meta">{insightNote}</p> : null}
    </section>
  );
}
