// Audit request constants shared across the app + public lead audit flows.
// Mirrors ReportMode in backend/agents/audit/schema.py.

export const ReportMode = Object.freeze({
  FREEHAND: "freehand", // agent streams a <duct_artifact> of HTML
  TEMPLATE: "template", // agent calls SubmitAuditReport → structured report
});

// Default structured-report template id (backend audit template registry).
export const DEFAULT_AUDIT_TEMPLATE_ID = "seo_v1";
