import fs from "node:fs/promises";
import path from "node:path";
import { resolveTheme } from "./themes";

const REPORTS_DIR =
  process.env.REPORTS_DIR ??
  path.resolve(process.cwd(), "..", "backend", "reports");

function formatTitle(slug) {
  return slug
    .replace(/[-_]/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

async function readPayload(jsonPath) {
  try {
    const raw = await fs.readFile(jsonPath, "utf8");
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

function getConnectionsFromPayload(payload) {
  const source = payload?.source_metadata?.source;
  if (!source) return [];
  if (source.includes("google_ads")) return ["google_ads"];
  return [source];
}

export async function listReports() {
  const entries = await fs.readdir(REPORTS_DIR, { withFileTypes: true });
  const jsonFiles = entries
    .filter((entry) => entry.isFile() && entry.name.endsWith(".json"))
    .map((entry) => entry.name);

  const reports = await Promise.all(
    jsonFiles.map(async (name) => {
      const slug = name.replace(/\.json$/i, "");
      const jsonPath = path.join(REPORTS_DIR, name);
      const payload = await readPayload(jsonPath);
      if (!payload) return null;

      const themeKey = payload.source_metadata?.theme ?? null;
      const theme = resolveTheme(themeKey);
      const generatedAt = payload.source_metadata?.generated_at ?? null;
      const keyInsight = payload.narrative?.verdict ?? payload.narrative?.summary ?? "";
      const connections = getConnectionsFromPayload(payload);

      return {
        slug,
        title: formatTitle(slug),
        themeKey,
        themeLabel: theme.label,
        generatedAt,
        keyInsight,
        connections,
      };
    })
  );

  const valid = reports.filter(Boolean);
  valid.sort((a, b) => {
    if (!a.generatedAt && !b.generatedAt) return a.slug.localeCompare(b.slug);
    if (!a.generatedAt) return 1;
    if (!b.generatedAt) return -1;
    return b.generatedAt.localeCompare(a.generatedAt);
  });

  return valid;
}

export async function getReportBySlug(slug) {
  const jsonPath = path.join(REPORTS_DIR, `${slug}.json`);
  const payload = await readPayload(jsonPath);
  if (!payload) return null;

  const themeKey = payload.source_metadata?.theme ?? null;
  const theme = resolveTheme(themeKey);
  const generatedAt = payload.source_metadata?.generated_at ?? null;

  return { slug, title: formatTitle(slug), themeKey, themeLabel: theme.label, generatedAt, payload };
}
