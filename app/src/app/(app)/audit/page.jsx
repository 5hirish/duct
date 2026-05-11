"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";

const CONTENT_TYPES = [
  { value: "", label: "Select type…" },
  { value: "blog", label: "Blog / Articles" },
  { value: "landing_pages", label: "Landing Pages" },
  { value: "product_pages", label: "Product Pages" },
  { value: "docs", label: "Docs / Help" },
];

export default function AuditSetupPage() {
  const router = useRouter();
  const [url, setUrl] = useState("");
  const [businessName, setBusinessName] = useState("");
  const [description, setDescription] = useState("");
  const [goals, setGoals] = useState("");
  const [keywords, setKeywords] = useState("");
  const [competitors, setCompetitors] = useState("");
  const [contentType, setContentType] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function handleSubmit(e) {
    e.preventDefault();
    setError("");
    if (!url.trim()) {
      setError("Website URL is required.");
      return;
    }
    setLoading(true);
    try {
      const params = {
        url: url.trim(),
        business_context: {
          business_name: businessName.trim(),
          business_description: description.trim(),
          business_goals: goals.trim(),
          target_keywords: keywords.split(",").map(k => k.trim()).filter(Boolean),
          competitors: competitors.split(",").map(c => c.trim()).filter(Boolean),
          primary_content_type: contentType,
        },
      };

      // Client-side routing key only. The workspace page calls POST /api/agents/seo-audit/sessions
      // on mount, gets the real backend session ID, then opens the SSE stream.
      const sessionId = crypto.randomUUID();
      sessionStorage.setItem(`audit_session_${sessionId}`, JSON.stringify(params));
      router.push(`/audit/${sessionId}`);
    } catch (err) {
      setError(err.message || "Failed to start audit.");
      setLoading(false);
    }
  }

  return (
    <div className="mx-auto max-w-2xl px-4 py-10">
      <div className="mb-8">
        <h1 className="text-2xl font-semibold tracking-tight">SEO Audit</h1>
        <p className="text-muted-foreground mt-1 text-sm">
          Crawl your site, surface issues, and get an AI-generated report with
          actionable recommendations.
        </p>
      </div>

      <form onSubmit={handleSubmit} className="space-y-6">
        {/* Required */}
        <div>
          <label className="block text-sm font-medium mb-1.5" htmlFor="url">
            Website URL <span className="text-destructive">*</span>
          </label>
          <input
            id="url"
            type="url"
            placeholder="https://yoursite.com"
            value={url}
            onChange={e => setUrl(e.target.value)}
            required
            className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
          />
        </div>

        {/* Optional context */}
        <div className="rounded-lg border border-border/60 p-4 space-y-4">
          <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
            Optional — improves report quality
          </p>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium mb-1.5" htmlFor="biz-name">
                Business name
              </label>
              <input
                id="biz-name"
                type="text"
                placeholder="Duct"
                value={businessName}
                onChange={e => setBusinessName(e.target.value)}
                className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1.5" htmlFor="content-type">
                Primary content type
              </label>
              <select
                id="content-type"
                value={contentType}
                onChange={e => setContentType(e.target.value)}
                className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
              >
                {CONTENT_TYPES.map(ct => (
                  <option key={ct.value} value={ct.value}>{ct.label}</option>
                ))}
              </select>
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium mb-1.5" htmlFor="description">
              Business description
            </label>
            <input
              id="description"
              type="text"
              placeholder="One-sentence description of what you do"
              value={description}
              onChange={e => setDescription(e.target.value)}
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
            />
          </div>

          <div>
            <label className="block text-sm font-medium mb-1.5" htmlFor="keywords">
              Target keywords
            </label>
            <input
              id="keywords"
              type="text"
              placeholder="analytics reporting, growth intelligence, SEO audit (comma-separated)"
              value={keywords}
              onChange={e => setKeywords(e.target.value)}
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
            />
          </div>

          <div>
            <label className="block text-sm font-medium mb-1.5" htmlFor="competitors">
              Competitors
            </label>
            <input
              id="competitors"
              type="text"
              placeholder="competitor1.com, competitor2.com (comma-separated)"
              value={competitors}
              onChange={e => setCompetitors(e.target.value)}
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
            />
          </div>

          <div>
            <label className="block text-sm font-medium mb-1.5" htmlFor="goals">
              Primary SEO goal
            </label>
            <textarea
              id="goals"
              rows={2}
              placeholder="e.g. Increase trial signups from organic search"
              value={goals}
              onChange={e => setGoals(e.target.value)}
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring resize-none"
            />
          </div>
        </div>

        {error && (
          <p className="text-sm text-destructive">{error}</p>
        )}

        <Button type="submit" disabled={loading} className="w-full">
          {loading ? "Starting audit…" : "Run SEO Audit →"}
        </Button>
      </form>
    </div>
  );
}
