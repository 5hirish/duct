// Theme definitions — migrated from backend/reports/themes.json.
// The backend embeds the theme key in source_metadata.theme; the app
// resolves it here to get accent colors for rendering.

export const THEMES = {
  paid_ads: {
    accent: "#2563EB",
    label: "Paid Ads",
  },
  product_intelligence: {
    accent: "#FF5C00",
    label: "Product Intelligence",
  },
  organic_growth: {
    accent: "#2E9E6B",
    label: "Organic Growth",
  },
};

export const DEFAULT_THEME = THEMES.paid_ads;

export function resolveTheme(key) {
  return THEMES[key] ?? DEFAULT_THEME;
}
