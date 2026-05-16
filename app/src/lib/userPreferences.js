export const PREFS_KEY = "duct_user_preferences";

export const PREFS_DEFAULTS = {
  role: "",
  communication_style: "practitioner",
  report_depth: "balanced",
  primary_outcome: "",
};

export const ROLE_OPTIONS = [
  { value: "", label: "Select your role…" },
  { value: "Founder / CEO", label: "Founder / CEO" },
  { value: "Executive (CMO, VP, Director)", label: "Executive (CMO, VP, Director)" },
  { value: "Product Manager", label: "Product Manager" },
  { value: "Growth Manager", label: "Growth Manager" },
  { value: "SEO / Content Lead", label: "SEO / Content Lead" },
  { value: "Developer / Engineer", label: "Developer / Engineer" },
  { value: "Consultant / Agency", label: "Consultant / Agency" },
  { value: "Other", label: "Other" },
];

export function loadPreferences() {
  if (typeof window === "undefined") return { ...PREFS_DEFAULTS };
  try {
    return { ...PREFS_DEFAULTS, ...JSON.parse(localStorage.getItem(PREFS_KEY) || "{}") };
  } catch {
    return { ...PREFS_DEFAULTS };
  }
}

export function savePreferences(prefs) {
  const value = JSON.stringify(prefs);
  localStorage.setItem(PREFS_KEY, value);
  window.dispatchEvent(
    new StorageEvent("storage", { key: PREFS_KEY, newValue: value, storageArea: localStorage })
  );
}

export function hasNonDefaultPreferences(prefs) {
  return (
    prefs.role !== PREFS_DEFAULTS.role ||
    prefs.communication_style !== PREFS_DEFAULTS.communication_style ||
    prefs.report_depth !== PREFS_DEFAULTS.report_depth ||
    prefs.primary_outcome !== PREFS_DEFAULTS.primary_outcome
  );
}
