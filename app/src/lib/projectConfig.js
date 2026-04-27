import { BASE } from "./api";

function backendApiHeaders(extra = {}) {
  const headers = { ...extra };
  const key = process.env.NEXT_PUBLIC_DUCT_API_KEY;
  if (key) {
    headers["X-API-Key"] = key;
  }
  return headers;
}

const FALLBACK_PROJECT_CONFIG = {
  industry_options: [
    { value: "E-commerce & Retail", label: "E-commerce & Retail" },
    { value: "SaaS & Software", label: "SaaS & Software" },
    { value: "Financial Services", label: "Financial Services" },
    { value: "Healthcare", label: "Healthcare" },
    { value: "Education", label: "Education" },
    { value: "Professional Services", label: "Professional Services" },
    { value: "Marketing & Advertising", label: "Marketing & Advertising" },
    { value: "Real Estate", label: "Real Estate" },
    { value: "Travel & Hospitality", label: "Travel & Hospitality" },
    { value: "Other", label: "Other" },
  ],
  business_model_options: [
    { value: "B2B", label: "B2B" },
    { value: "B2C", label: "B2C" },
    { value: "Marketplace", label: "Marketplace" },
    { value: "PLG", label: "PLG" },
    { value: "Agency", label: "Agency" },
    { value: "Hybrid", label: "Hybrid" },
  ],
  north_star_metric_options: [
    { value: "Weekly active users", label: "Weekly active users" },
    { value: "Monthly active customers", label: "Monthly active customers" },
    { value: "Qualified leads", label: "Qualified leads" },
    { value: "Pipeline created", label: "Pipeline created" },
    { value: "Net new revenue", label: "Net new revenue" },
    { value: "Retention rate", label: "Retention rate" },
    { value: "Bookings", label: "Bookings" },
    { value: "Custom", label: "Custom" },
  ],
  growth_stage_milestone_options: [
    { value: "0_pre_customer", label: "No customers or active users yet" },
    { value: "1_first_users", label: "First active users/customers (1-10)" },
    { value: "2_early_revenue", label: "Early repeat usage or revenue (10-100 customers)" },
    { value: "3_repeatable_growth", label: "Repeatable growth motion (100+ customers or steady MoM growth)" },
    { value: "4_scaling", label: "Scaling across channels or segments with predictable performance" },
  ],
};

export async function fetchProjectConfig(
  { industry = "", businessModel = "" } = {},
  options = {}
) {
  const query = new URLSearchParams();
  if (industry) query.set("industry", industry);
  if (businessModel) query.set("business_model", businessModel);
  const queryString = query.toString();
  const url = `${BASE}/api/projects/config${queryString ? `?${queryString}` : ""}`;
  const res = await fetch(url, {
    headers: backendApiHeaders(),
    ...options,
  });
  if (!res.ok) throw new Error(`Failed to fetch project config: ${res.status}`);
  return res.json();
}

export function getFallbackProjectConfig() {
  return FALLBACK_PROJECT_CONFIG;
}
