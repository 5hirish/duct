"use client";

import { useEffect, useMemo, useState } from "react";
import { Check, Sparkles, X } from "lucide-react";
import { listStyles } from "@/lib/contentApi";

// ---------------------------------------------------------------------------
// Live preview — render the real CSS inside an isolated iframe so global
// classes (.cap-stroke, etc.) don't leak or collide across cards.
// ---------------------------------------------------------------------------

const CATEGORY_LABELS = {
  hook: "Hooks",
  caption: "Captions",
  body: "Text cards",
};
const CATEGORY_ORDER = ["hook", "caption", "body"];

function sampleInner(style) {
  const p = style.preview || {};
  const text = p.text || style.name;
  const sub = p.sub;
  const backdrop = {
    photo: "linear-gradient(135deg,#7a6b80 0%,#3a2a34 60%,#241820 100%)",
    dark: "#160f13",
    light: "#e8e2da",
  }[p.bg] || "#222";

  if (style.category === "body") {
    return `<div class="slide slide-body"><div class="body-content">
      <span class="body-statement">${text}</span>
      ${sub ? `<span class="body-sub">${sub}</span>` : ""}
    </div></div>`;
  }

  let cap;
  if (style.key === "hook") {
    cap = `<span class="hook-headline">${text}</span>${sub ? `<span class="hook-sub">${sub}</span>` : ""}`;
  } else if (style.key === "cap-pill") {
    cap = `<div class="cap-pill-wrap"><span class="cap-pill">${text}</span></div>${sub ? `<div class="cap-pill-sub"><span>${sub}</span></div>` : ""}`;
  } else {
    cap = `<span class="${style.key}">${text}</span>${sub ? `<span class="${style.key}-sub">${sub}</span>` : ""}`;
  }
  return `<div class="slide slide-hook">
    <div style="position:absolute;inset:0;z-index:0;background:${backdrop}"></div>
    <div class="grad"></div>
    <div class="cap-bottom">${cap}</div>
  </div>`;
}

function buildDoc(style, baseCss, zoom) {
  return `<!doctype html><html><head><meta charset="utf-8"><style>
${baseCss}
${style.css}
/* preview overrides — kill the builder-page body chrome */
body{margin:0;padding:0;gap:0;background:#111;display:block}
:root{--zoom:${zoom}}
</style></head><body>${sampleInner(style)}</body></html>`;
}

function StylePreview({ style, baseCss }) {
  const W = 232;
  const zoom = W / 1080;
  const H = Math.round(1920 * zoom);
  const srcDoc = useMemo(() => buildDoc(style, baseCss, zoom), [style, baseCss, zoom]);
  return (
    <div className="overflow-hidden rounded-lg border border-border/60 bg-black" style={{ height: H }}>
      <iframe
        title={`${style.name} preview`}
        srcDoc={srcDoc}
        sandbox=""
        scrolling="no"
        className="block border-0"
        style={{ width: W, height: H }}
      />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Gallery
// ---------------------------------------------------------------------------

export default function StyleGallery() {
  const [styles, setStyles] = useState([]);
  const [baseCss, setBaseCss] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const data = await listStyles();
        if (cancelled) return;
        setStyles(Array.isArray(data?.styles) ? data.styles : []);
        setBaseCss(data?.base_css || "");
      } catch (e) {
        if (!cancelled) setError(e.message || "Failed to load styles.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, []);

  const grouped = useMemo(() => {
    const g = {};
    for (const s of styles) (g[s.category] ||= []).push(s);
    return g;
  }, [styles]);

  if (loading) {
    return (
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {[0, 1, 2].map((i) => (
          <div key={i} className="h-[460px] animate-pulse rounded-xl border border-border/50 bg-muted/30" />
        ))}
      </div>
    );
  }
  if (error) return <p className="text-sm text-destructive">{error}</p>;

  return (
    <section className="space-y-6">
      <div className="rounded-lg border border-border/60 bg-muted/30 px-4 py-3">
        <p className="flex items-center gap-2 text-sm font-medium">
          <Sparkles className="h-4 w-4 text-primary" /> Base styles
        </p>
        <p className="mt-0.5 text-xs text-muted-foreground">
          The shared, brand-agnostic slide styles the builder inlines so captions stay consistent.
          Formats link to these. More styles &amp; categories coming.
        </p>
      </div>

      {CATEGORY_ORDER.filter((c) => grouped[c]?.length).map((cat) => (
        <div key={cat}>
          <h3 className="mb-3 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            {CATEGORY_LABELS[cat] || cat}
          </h3>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {grouped[cat].map((s) => (
              <article key={s.key} className="flex flex-col overflow-hidden rounded-xl border border-border/70 bg-card">
                <div className="bg-black/40 p-3">
                  <StylePreview style={s} baseCss={baseCss} />
                </div>
                <div className="flex flex-1 flex-col gap-2 p-3.5">
                  <div className="flex items-center justify-between gap-2">
                    <h4 className="text-sm font-semibold">{s.name}</h4>
                    <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground">.{s.key}</code>
                  </div>
                  <p className="text-xs leading-relaxed text-muted-foreground">{s.description}</p>
                  {s.when_to_use && (
                    <p className="flex items-start gap-1.5 text-[11px] text-foreground/70">
                      <Check className="mt-0.5 h-3 w-3 shrink-0 text-green-500" />
                      <span>{s.when_to_use}</span>
                    </p>
                  )}
                  {s.dont_use_on && (
                    <p className="flex items-start gap-1.5 text-[11px] text-muted-foreground">
                      <X className="mt-0.5 h-3 w-3 shrink-0 text-rose-500" />
                      <span>{s.dont_use_on}</span>
                    </p>
                  )}
                </div>
              </article>
            ))}
          </div>
        </div>
      ))}
    </section>
  );
}
