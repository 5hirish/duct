"use client";
import React, { useMemo, useState } from 'react';
import { Sparkles, PenLine, Languages, ArrowRight, X, Check } from 'lucide-react';
import { Plural, Trans, useLingui } from "@lingui/react/macro";
import { msg } from "@lingui/core/macro";
import { Spinner } from "@/components/ui/spinner";
import {
  Dialog,
  DialogContent,
  DialogTitle,
} from '@/components/ui/dialog';
import { expressExecutionInterest } from '../../lib/api';
import { trackEvent, AnalyticsEvent } from '../../lib/analytics';

const DUCT_ORANGE = '#ff5c00';
const DUCT_NAVY = '#0d0f1a';
const DUCT_CREAM = '#f4ece2';

// ---------------------------------------------------------------------------
// Service catalogue — what Duct can execute (auditing is free; this is the product)
// ---------------------------------------------------------------------------

// `label` and `blurb` are message descriptors (module scope); the blocks that
// render them resolve with `i18n._`.
const SERVICES = [
  {
    key: 'ai_ready_fixes',
    label: msg`AI-ready fixes`,
    Icon: Sparkles,
    blurb: msg`Schema, meta titles & descriptions, llms.txt and FAQ markup — generated and ready to paste.`,
    // Findings in these categories are auto-generatable with no CMS access
    cats: ['on_page_seo', 'structured_data', 'geo_aio', 'open_graph', 'technical_foundation'],
    kw: ['schema', 'meta', 'title', 'description', 'canonical', 'llms', 'faq', 'open graph', 'og:', 'structured'],
  },
  {
    key: 'content_rewrites',
    label: msg`On-page content rewrites`,
    Icon: PenLine,
    blurb: msg`Thin or weak page and blog copy rewritten for search intent and your keywords.`,
    cats: ['blog_content_strategy'],
    kw: ['thin', 'word count', 'short', 'content', 'blog', 'copy', 'readability', 'intent', 'h1'],
  },
  {
    key: 'translation',
    label: msg`Translation & localization`,
    Icon: Languages,
    blurb: msg`Translated metadata and a complete hreflang map so you can rank in new markets.`,
    cats: [],
    kw: ['hreflang', 'locale', 'translation', 'language', 'international', 'multilingual'],
  },
];

const SEVERITIES = new Set(['fail', 'warn', 'opportunity']);

/**
 * Count how many addressable findings map to each service, from the report data.
 * Returns [{ ...service, count }]. Translation is usually 0 (single-locale sites) —
 * the block shows it with generic "expand" copy rather than a count.
 */
export function computeExecutionServices(data) {
  const categories = Array.isArray(data?.categories) ? data.categories : [];
  const allFindings = categories.flatMap((c) =>
    (Array.isArray(c.findings) ? c.findings : []).map((f) => ({ ...f, _catId: c.id })),
  );

  return SERVICES.map((svc) => {
    const count = allFindings.filter((f) => {
      if (!SEVERITIES.has(f.severity)) return false;
      if (svc.cats.includes(f._catId)) return true;
      const hay = `${f.id || ''} ${f.title || ''}`.toLowerCase();
      return svc.kw.some((k) => hay.includes(k));
    }).length;
    return { ...svc, count };
  });
}

// ---------------------------------------------------------------------------
// Strategic block — placed after "Fix These First"
// ---------------------------------------------------------------------------

export function ExecutionOfferBlock({ services, onOpen }) {
  const { i18n } = useLingui();
  const totalFixes = services
    .filter((s) => s.key !== 'translation')
    .reduce((n, s) => n + s.count, 0);

  React.useEffect(() => {
  }, [totalFixes]);

  return (
    <section className="rise-6">
      <div
        className="rounded-2xl overflow-hidden shadow-xl"
        style={{ background: DUCT_NAVY }}
      >
        <div className="px-5 py-6 @xl:px-8 @xl:py-7">
          <div className="flex items-center gap-2 mb-3">
            <span
              className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-2xs font-semibold tracking-wide"
              style={{ background: 'rgba(255,92,0,0.16)', color: DUCT_ORANGE }}
            >
              <Sparkles size={12} /> <Trans>DONE FOR YOU</Trans>
            </span>
          </div>

          <h2
            style={{
              fontFamily: 'Georgia, "Times New Roman", serif',
              color: DUCT_CREAM,
              fontSize: 'clamp(1.15rem, 3.5vw, 1.6rem)',
              fontWeight: 700,
              lineHeight: 1.25,
              letterSpacing: '-0.01em',
              margin: 0,
            }}
          >
            {totalFixes > 0
              ? <Trans>Don’t have time to fix these? Duct can execute <span style={{ color: DUCT_ORANGE }}>{totalFixes}</span> of them for you.</Trans>
              : <Trans>Want Duct to execute these fixes for you?</Trans>}
          </h2>

          <p className="mt-2.5 text-sm @xl:text-base" style={{ color: 'rgba(244,236,226,0.72)', lineHeight: 1.6 }}>
            <Trans>
              The audit is on us. Our agents turn these findings into ready-to-ship fixes —
              so you ship the work, not just the to-do list.
            </Trans>
          </p>

          {/* Service chips */}
          <div className="mt-5 grid gap-3 @xl:grid-cols-3">
            {services.map(({ key, label, blurb, count, Icon }) => (
              <div
                key={key}
                className="rounded-xl p-3.5 h-full"
                style={{ background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.08)' }}
              >
                <div className="flex items-center gap-2">
                  <Icon size={15} style={{ color: DUCT_ORANGE }} />
                  <span className="text-sm font-semibold" style={{ color: DUCT_CREAM }}>{i18n._(label)}</span>
                </div>
                {count > 0 ? (
                  <div className="mt-1.5 text-2xs font-medium" style={{ color: DUCT_ORANGE }}>
                    <Plural value={count} one="# fix we can generate" other="# fixes we can generate" />
                  </div>
                ) : (
                  <div className="mt-1.5 text-2xs font-medium" style={{ color: 'rgba(244,236,226,0.72)' }}>
                    {key === 'translation' ? <Trans>Expand into new markets</Trans> : <Trans>On request</Trans>}
                  </div>
                )}
                <p className="mt-1.5 text-xs leading-snug" style={{ color: 'rgba(244,236,226,0.76)' }}>
                  {i18n._(blurb)}
                </p>
              </div>
            ))}
          </div>

          <div className="mt-5 flex flex-wrap items-center gap-3">
            <button
              type="button"
              onClick={() => onOpen('block')}
              className="inline-flex items-center gap-2 rounded-lg px-4 py-2.5 text-sm font-semibold transition-opacity hover:opacity-90"
              style={{ background: DUCT_ORANGE, color: '#fff' }}
            >
              <Trans>See what we’d do</Trans> <ArrowRight size={15} />
            </button>
            <span className="text-xs" style={{ color: 'rgba(244,236,226,0.72)' }}>
              <Trans>No commitment — we’ll scope it and follow up.</Trans>
            </span>
          </div>
        </div>
        <div style={{ height: 3, background: 'linear-gradient(90deg, #ff5c00, #ff8c42 60%, transparent)' }} />
      </div>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Soft closing line — sits just above the footer
// ---------------------------------------------------------------------------

export function ExecutionClosingLine({ onOpen }) {
  return (
    <div className="text-center pt-2">
      <button
        type="button"
        onClick={() => onOpen('footer')}
        className="text-sm font-medium underline-offset-4 hover:underline"
        style={{ color: DUCT_ORANGE }}
      >
        <Trans>Want these done for you? Request execution →</Trans>
      </button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Request modal — pick services, submit interest
// ---------------------------------------------------------------------------

export function ExecutionRequestModal({ open, onClose, services, leadToken, email }) {
  const { t, i18n } = useLingui();
  // Pre-check services that have addressable fixes; fall back to AI-ready fixes.
  const defaults = useMemo(() => {
    const checked = services.filter((s) => s.count > 0).map((s) => s.key);
    return checked.length ? checked : ['ai_ready_fixes'];
  }, [services]);

  const [selected, setSelected] = useState(defaults);
  const [note, setNote] = useState('');
  const [status, setStatus] = useState('idle'); // idle | submitting | done | error

  // Reset selection whenever the modal re-opens with fresh defaults
  React.useEffect(() => {
    if (open) {
      setSelected(defaults);
      setNote('');
      setStatus('idle');
    }
  }, [open, defaults]);

  if (!open) return null;

  const toggle = (key) =>
    setSelected((cur) => (cur.includes(key) ? cur.filter((k) => k !== key) : [...cur, key]));

  const submit = async () => {
    if (!selected.length || status === 'submitting') return;
    setStatus('submitting');
    trackEvent(AnalyticsEvent.ExecutionInterestSubmitted, { services: selected.join(',') });
    try {
      await expressExecutionInterest(leadToken, { services: selected, note: note.trim() || null });
      setStatus('done');
    } catch {
      setStatus('error');
    }
  };

  const contact = email || t`your email`;

  // This dialog belongs to the audit report, which declares itself a light
  // document (AuditReportV1). It is portalled out of that subtree, so it has to
  // declare the same thing for itself rather than inherit it — and it does so
  // by redefining the tokens, not by painting `bg-white`, so the shadcn parts
  // inside (DialogTitle, and anything added later) come out right too. Without
  // this it was a white card with white-ish token text in dark mode.
  return (
    <Dialog open={open} onOpenChange={(next) => { if (!next) onClose(); }}>
      <DialogContent
        showCloseButton={false}
        className="max-w-md overflow-hidden rounded-2xl border-0 p-0 shadow-2xl"
        style={{
          colorScheme: "light",
          "--background": "#ffffff",
          "--foreground": "#1a1a1a",
          "--popover": "#ffffff",
          "--popover-foreground": "#1a1a1a",
          "--muted-foreground": "#5b6072",
          "--border": "#e5e7eb",
          background: "var(--background)",
          color: "var(--foreground)",
        }}
      >
        {/* Header */}
        <div className="flex items-start justify-between px-5 pt-5 pb-3">
          <div>
            <DialogTitle className="text-base font-bold" style={{ color: DUCT_NAVY }}>
              {status === 'done' ? <Trans>You're on the list</Trans> : <Trans>Have Duct execute your fixes</Trans>}
            </DialogTitle>
            {status !== 'done' && (
              <p className="mt-1 text-xs text-muted-foreground"><Trans>Pick what you’d like done. We’ll scope it and follow up.</Trans></p>
            )}
          </div>
          <button type="button" onClick={onClose} className="p-1 text-muted-foreground hover:text-foreground" aria-label={t`Close`}>
            <X size={18} />
          </button>
        </div>

        {status === 'done' ? (
          <div className="px-5 pb-6">
            <div className="rounded-xl bg-success/5 border border-success/30 px-4 py-4 text-sm text-success">
              <Trans>Thanks! We’ll be in touch at <span className="font-semibold">{contact}</span> to scope this out.</Trans>
            </div>
            <button
              type="button"
              onClick={onClose}
              className="mt-4 w-full rounded-lg py-2.5 text-sm font-semibold text-white"
              style={{ background: DUCT_NAVY }}
            >
              <Trans>Done</Trans>
            </button>
          </div>
        ) : (
          <div className="px-5 pb-5">
            <div className="space-y-2">
              {services.map(({ key, label, blurb, count, Icon }) => {
                const isOn = selected.includes(key);
                return (
                  <button
                    type="button"
                    key={key}
                    onClick={() => toggle(key)}
                    className="w-full text-left rounded-xl border px-3.5 py-3 transition-colors"
                    style={{
                      borderColor: isOn ? DUCT_ORANGE : 'var(--border)',
                      background: isOn ? 'rgba(255,92,0,0.05)' : 'var(--background)',
                    }}
                  >
                    <div className="flex items-center gap-2.5">
                      <span
                        className="inline-flex size-5 shrink-0 items-center justify-center rounded-md"
                        style={{ background: isOn ? DUCT_ORANGE : '#eceef2', color: isOn ? '#fff' : '#5b6072' }}
                      >
                        {isOn ? <Check size={13} /> : <Icon size={13} />}
                      </span>
                      <span className="text-sm font-semibold" style={{ color: DUCT_NAVY }}>{i18n._(label)}</span>
                      {count > 0 && (
                        <span className="ml-auto text-2xs font-medium" style={{ color: DUCT_ORANGE }}>
                          <Plural value={count} one="# fix" other="# fixes" />
                        </span>
                      )}
                    </div>
                    <p className="mt-1 pl-[30px] text-xs leading-snug text-muted-foreground">{i18n._(blurb)}</p>
                  </button>
                );
              })}
            </div>

            <textarea
              value={note}
              aria-label={t`Anything specific (optional)`}
              onChange={(e) => setNote(e.target.value)}
              rows={2}
              placeholder={t`Anything specific? (optional)`}
              className="mt-3 w-full rounded-lg border border-border px-3 py-2 text-sm outline-none focus-visible:border-brand"
            />

            {status === 'error' && (
              <p className="mt-2 text-xs text-destructive"><Trans>That didn’t send — your choices are still here. Try again.</Trans></p>
            )}

            <button
              type="button"
              onClick={submit}
              disabled={!selected.length || status === 'submitting'}
              className="mt-3 w-full inline-flex items-center justify-center gap-2 rounded-lg py-2.5 text-sm font-semibold text-white disabled:opacity-50"
              style={{ background: DUCT_ORANGE }}
            >
              {status === 'submitting' ? <><Spinner className="size-4" /> <Trans>Sending…</Trans></> : <Trans>Request execution</Trans>}
            </button>
            <p className="mt-2 text-center text-2xs text-muted-foreground"><Trans>No payment now — we’ll scope and quote first.</Trans></p>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
