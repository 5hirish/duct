"use client";

/**
 * Models — the one page that answers "which model runs my work, and whose key
 * pays for it".
 *
 * Both questions used to live elsewhere: the model came from a server env var
 * nobody could see, and the provider keys sat on the Connections page next to
 * Google Ads. The failure that produced was specific — you could paste an
 * OpenAI key, watch it save, and have every run still go to Claude, with
 * nothing anywhere saying why.
 *
 * A third tab, Runtime, picked the agent harness. Once v3 was removed it
 * offered a single engine, always active, already selected — a radio group
 * with one button. The engine is still a question the server is asked (it
 * scopes the catalogue and the tier preview), just no longer one to answer
 * here; DEFAULT_ENGINE is what goes over the wire.
 */

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Anvil, ArrowRight, Feather, ImageIcon, Scale, Video, Wand2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectLabel,
  SelectGroup,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import ChatGPTCard from "@/components/connections/ChatGPTCard";
import ProviderCard from "@/components/connections/ProviderCard";
import ContextCompressionCard from "@/components/ContextCompressionCard.jsx";
import AutoFallbackCard from "@/components/AutoFallbackCard";
import TelemetryCard from "@/components/TelemetryCard.jsx";
import { LOGOS } from "@/components/connections/logos";
import { PROVIDERS } from "@/lib/providerKeys";
import {
  JOB_LABELS,
  MODEL_MAP_CHANGED,
  PROVIDER_LOGO_KEY,
  SOURCE_DETAIL,
  SOURCE_LABELS,
  SOURCE_TONE,
  TIERS,
  fetchModelCatalogue,
  fetchProviderStatus,
  fetchTierPreview,
  loadModelMap,
  saveModelMap,
  tierPicks,
} from "@/lib/modelTiers";
import { fetchModelSettings, saveModelSettings } from "@/lib/modelSettings";
import { DEFAULT_ENGINE } from "@/lib/engines";

// ---------------------------------------------------------------------------
// Small shared pieces
// ---------------------------------------------------------------------------

function StateChip({ tone = "neutral", children, title }) {
  return (
    <span className={`mt-chip mt-chip--${tone}`} title={title}>
      {children}
    </span>
  );
}

/** The tier's own mark. Anvil, balance scale, feather — heaviest to lightest. */
const TIER_ICONS = { anvil: Anvil, scale: Scale, feather: Feather };

/**
 * A provider's mark at picker size.
 *
 * `LOGOS` entries are authored for the 24px connector tile and carry explicit
 * width/height attributes, so the wrapper has to size them down in CSS rather
 * than by prop.
 */
function ProviderMark({ providerId, className = "mt-mark" }) {
  const logo = LOGOS[PROVIDER_LOGO_KEY[providerId] || providerId];
  if (!logo) return null;
  return (
    <span className={className} aria-hidden="true">
      {logo}
    </span>
  );
}

/**
 * Groups the picker by provider so "everything I have a key for" is one glance.
 *
 * Every model is listed, annotated rather than hidden. Filtering the list to
 * what the current engine accepts sounds tidier, and it was what this did
 * first — but an engine whose supported providers did not overlap the shipped
 * default triple emptied the list, and every picker rendered blank with
 * nothing to explain why. The row state below already says what will actually
 * run; the group label just has to be honest about why an option is greyed.
 */
function ModelPicker({ value, models, providersById, engine, onChange, id, label, loading }) {
  const grouped = useMemo(() => {
    const byProvider = new Map();
    for (const model of models) {
      if (!byProvider.has(model.provider)) byProvider.set(model.provider, []);
      byProvider.get(model.provider).push(model);
    }
    // The provider you are already on leads, then whatever else is usable —
    // what you can actually run should never sit below what you cannot.
    const current = models.find((model) => model.id === value)?.provider;
    const rank = (id) => {
      if (id === current) return -1;
      const provider = providersById[id];
      const onEngine = (provider?.engines || []).includes(engine);
      return (provider?.reachable ? 0 : 2) + (onEngine ? 0 : 1);
    };
    return [...byProvider.entries()].sort(([a], [b]) => rank(a) - rank(b));
  }, [models, providersById, engine, value]);

  const note = (providerId) => {
    const provider = providersById[providerId];
    const flags = [];
    if (provider && !provider.reachable) flags.push("no key");
    if (provider && !(provider.engines || []).includes(engine)) flags.push(`not on ${engine}`);
    return flags.length ? ` · ${flags.join(", ")}` : "";
  };

  const selected = models.find((model) => model.id === value);

  return (
    <Select value={value || ""} onValueChange={onChange}>
      <SelectTrigger id={id} className="mt-select" aria-label={label}>
        {/* Not <SelectValue>: the trigger should carry the provider's mark too,
            so "which vendor am I on" is answerable without opening anything. */}
        {selected ? (
          <span className="mt-selected">
            <ProviderMark providerId={selected.provider} />
            <span className="mt-selected-id">{selected.id}</span>
          </span>
        ) : loading ? (
          // Not "Choose a model": until the catalogue lands every tier *does*
          // have a model, and inviting a choice implies none is set.
          <span className="mt-selected mt-selected--loading">Loading models…</span>
        ) : (
          <SelectValue placeholder="Choose a model" />
        )}
      </SelectTrigger>
      <SelectContent>
        {grouped.map(([providerId, list]) => (
          <SelectGroup key={providerId}>
            <SelectLabel className="mt-group">
              <ProviderMark providerId={providerId} className="mt-mark mt-mark--sm" />
              <span>
                {providersById[providerId]?.label || providerId}
                {note(providerId)}
              </span>
            </SelectLabel>
            {list.map((model) => (
              <SelectItem key={model.id} value={model.id}>
                <span className="mt-option">
                  <ProviderMark providerId={model.provider} />
                  <span className="mt-option-id">{model.id}</span>
                </span>
              </SelectItem>
            ))}
          </SelectGroup>
        ))}
      </SelectContent>
    </Select>
  );
}

// ---------------------------------------------------------------------------
// Tier card
// ---------------------------------------------------------------------------

function TierCard({ tier, index, value, models, providersById, engine, jobs, preview, loading, onChange }) {
  const provider = providersById[preview?.provider] || null;
  const source = provider?.source || "none";
  const blocked = preview && !preview.runnable;
  const serves = preview?.serves;
  const offEngine = preview?.reason === "engine_unsupported";
  const TierIcon = TIER_ICONS[tier.icon] || Scale;

  return (
    <div className={`mt-tier${index === 0 ? " mt-tier--lead" : ""}${blocked ? " mt-tier--blocked" : ""}`}>
      <div className="mt-tier-head">
        <span className={`mt-tier-mark mt-tier-mark--${tier.key}`} aria-hidden="true">
          <TierIcon size={17} strokeWidth={1.75} />
        </span>
        <div className="mt-tier-name">
          <h3>
            {tier.label}
            <span className="mt-tier-rank">{index + 1}</span>
          </h3>
          <p>{tier.tagline}</p>
        </div>
      </div>

      <p className="mt-tier-blurb">{tier.blurb}</p>

      <div className="mt-tier-control">
        <ModelPicker
          id={`tier-${tier.key}`}
          label={`Model for the ${tier.label} tier`}
          loading={loading}
          value={value}
          models={models}
          providersById={providersById}
          engine={engine}
          onChange={(next) => onChange(tier.key, next)}
        />
        {preview && (
          <StateChip
            tone={blocked ? "warn" : SOURCE_TONE[source] || "neutral"}
            title={blocked ? undefined : SOURCE_DETAIL[source]}
          >
            {blocked ? (offEngine ? "Not on this engine" : "No key") : SOURCE_LABELS[source] || "Ready"}
          </StateChip>
        )}
      </div>

      {/* The promise. Rendered from the server's own resolution, never from a
          guess about which keys this browser holds. */}
      {blocked && (
        <p className="mt-tier-fallback">
          {serves ? (
            <>
              {offEngine ? (
                <>This engine runs Anthropic models only, so </>
              ) : null}
              {offEngine ? tier.label.toLowerCase() : tier.label} jobs run on <b>{serves.model}</b>
              {serves.engine_default ? " — this engine's default" : " until you add a key"}.
            </>
          ) : (
            <>Nothing below this tier can run either — add a key to use {tier.label}.</>
          )}
        </p>
      )}

      {tier.fallbackFor && (
        <p className="mt-tier-role">
          Also the fallback for <b>{tier.fallbackFor}</b>
        </p>
      )}

      {/* The divider belongs to the job chips. With the catalogue still in
          flight there are none, and an empty bordered box reads as a broken
          card rather than as a loading one. */}
      {jobs.length > 0 && (
        <div className="mt-tier-jobs">
          {jobs.map((job) => (
            <span key={job} className="mt-job">
              {JOB_LABELS[job] || job}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

/**
 * The Images row: which key draws, resolved by the server.
 *
 * Used to print `gemini-3.1-flash-image` as a literal beside the Gemini mark,
 * which read as a rule — and sent people on an OpenAI or xAI key to Google
 * for something their own key already does. The server now answers with its
 * pick (same preference order the run uses: Gemini, then OpenAI, then xAI),
 * and this renders whatever came back. `catalogue.image_models` lists the
 * providers that can draw at all, for the empty state and the hint.
 */
function ImagesRow({ images, catalogue, providersById }) {
  const imageProviders = useMemo(() => {
    const order = catalogue?.image_provider_order ?? [];
    const seen = new Set((catalogue?.image_models ?? []).map((model) => model.provider));
    return order.filter((id) => seen.has(id));
  }, [catalogue]);
  // Before the catalogue answers there is nothing to list; the three names
  // are the ones the server would send, not a second copy of the rule.
  const providerNames = (imageProviders.length
    ? imageProviders.map((id) => providersById[id]?.label || id)
    : ["Google Gemini", "OpenAI", "xAI"]
  )
    .join(", ")
    .replace(/, ([^,]*)$/, " or $1");
  const picked = images?.provider ? images : null;
  const pickedLabel = picked ? providersById[picked.provider]?.label || picked.provider : "";
  const others = imageProviders.filter((id) => id !== picked?.provider && providersById[id]?.reachable);

  let note;
  if (!images) {
    note = "Checking which of your keys can draw…";
  } else if (!picked) {
    note = `None of your tier models generate images. Add a ${providerNames} key and Duct will draw with it.`;
  } else if (others.length) {
    note = `Drawing with your ${pickedLabel} key. Your ${others
      .map((id) => providersById[id]?.label || id)
      .join(" and ")} key${others.length > 1 ? "s" : ""} can draw too; ${pickedLabel} comes first when more than one is set.`;
  } else {
    note = `None of your tier models generate images, so Duct draws with your ${pickedLabel} key.`;
  }

  return (
    <div className="mt-mod-row">
      <div className="mt-mod-name">
        <span className="mt-mod-mark" aria-hidden="true">
          <ImageIcon size={15} strokeWidth={1.75} />
        </span>
        <div>
          <strong>Images</strong>
          <span>Slides and post images · Content Studio</span>
        </div>
      </div>
      <div className="mt-mod-ctl">
        {picked ? (
          <>
            <ProviderMark providerId={picked.provider} />
            <code className="mt-mono">{picked.model}</code>
            <StateChip
              tone={SOURCE_TONE[picked.source] || "ok"}
              title={`${SOURCE_DETAIL[picked.source] || ""} — chosen for you, no tier model can generate images`}
            >
              {SOURCE_LABELS[picked.source] || "Auto"}
            </StateChip>
          </>
        ) : (
          <StateChip tone={images ? "warn" : "neutral"}>{images ? "Needs a key" : "Checking"}</StateChip>
        )}
      </div>
      <p className="mt-mod-note">{note}</p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function ModelSettingsPage() {
  const [map, setMap] = useState({});
  const [catalogue, setCatalogue] = useState(null);
  const [providers, setProviders] = useState([]);
  // The server's pick for the image tools, or null until it answers.
  const [images, setImages] = useState(null);
  // The backend's kill switch for the ChatGPT tile; off until it answers.
  const [chatgptAuthEnabled, setChatgptAuthEnabled] = useState(false);
  const [preview, setPreview] = useState(null);
  const [saved, setSaved] = useState("");
  const savedTimer = useRef(null);

  // First paint: everything the page renders is server-owned except the map.
  useEffect(() => {
    setMap(loadModelMap());
    // The server's copy is the one every run reads — including the scheduled
    // brief, which has no browser. localStorage paints first so the page is
    // never blank; this corrects it a moment later, and a stale tab loses.
    fetchModelSettings().then((settings) => {
      if (Object.keys(settings.tiers || {}).length) {
        setMap((current) => {
          const next = { ...current, tiers: settings.tiers };
          saveModelMap(next);
          return next;
        });
      }
    });
    fetchModelCatalogue().then(setCatalogue);
    fetchProviderStatus().then((status) => {
      setProviders(status.providers);
      setImages(status.images);
      setChatgptAuthEnabled(Boolean(status.chatgptAuthEnabled));
    });
  }, []);

  const picks = useMemo(() => tierPicks(map), [map]);
  // Depend on the *content* of the picks, not the object identity. Reading
  // storage on mount replaces `map` with an equal-but-new object, which would
  // otherwise fire a second, identical resolve on every page load.
  const picksKey = JSON.stringify(picks);

  // Re-resolve whenever the draft changes. The page never computes what will
  // run — it asks.
  useEffect(() => {
    let alive = true;
    fetchTierPreview(JSON.parse(picksKey), DEFAULT_ENGINE).then((next) => {
      if (alive) setPreview(next);
    });
    return () => {
      alive = false;
    };
  }, [picksKey]);

  useEffect(() => () => clearTimeout(savedTimer.current), []);

  const providersById = useMemo(() => {
    const byId = {};
    for (const provider of providers) byId[provider.id] = provider;
    return byId;
  }, [providers]);

  const previewByTier = useMemo(() => {
    const byTier = {};
    for (const row of preview?.tiers ?? []) byTier[row.id] = row;
    return byTier;
  }, [preview]);

  const jobsByTier = useMemo(() => {
    const byTier = {};
    for (const row of catalogue?.tiers ?? []) byTier[row.id] = row.jobs || [];
    return byTier;
  }, [catalogue]);

  // The whole catalogue. The picker annotates what this engine cannot serve
  // rather than hiding it — see ModelPicker for why filtering was wrong.
  const models = catalogue?.models ?? [];

  const flash = useCallback((message) => {
    setSaved(message);
    clearTimeout(savedTimer.current);
    savedTimer.current = setTimeout(() => setSaved(""), 2200);
  }, []);

  const commit = useCallback(
    (next, message) => {
      setMap(next);
      saveModelMap(next);
      // Written to both: localStorage so this tab and the composer see it at
      // once, the server so every run does — including the ones with nobody
      // watching. Fire-and-forget; the local copy is what this page renders.
      saveModelSettings({ tiers: tierPicks(next) });
      flash(message);
    },
    [flash]
  );

  function setTier(tierKey, model) {
    const defaults = Object.fromEntries(
      (catalogue?.tiers ?? []).map((row) => [row.id, row.default_model])
    );
    const nextTiers = { ...defaults, ...(map.tiers || {}), [tierKey]: model };
    commit({ ...map, tiers: nextTiers }, "Saved");
  }

  function fillFromProvider(providerId) {
    const triple = catalogue?.provider_triples?.[providerId];
    if (!triple) return;
    commit({ ...map, tiers: { ...triple } }, `Filled from ${providersById[providerId]?.label || providerId}`);
  }

  function resetToDefaults() {
    const { tiers, ...rest } = map;
    commit(rest, "Reset to defaults");
  }


  // Re-read if another tab (or the composer) writes the map.
  useEffect(() => {
    const sync = () => setMap(loadModelMap());
    window.addEventListener(MODEL_MAP_CHANGED, sync);
    window.addEventListener("storage", sync);
    return () => {
      window.removeEventListener(MODEL_MAP_CHANGED, sync);
      window.removeEventListener("storage", sync);
    };
  }, []);

  const configuredCount = Object.keys(picks).length;
  const fillable = (PROVIDERS || []).filter(
    (provider) => catalogue?.provider_triples?.[provider.statusId]
  );

  return (
    <section>
      <div className="page-toolbar-back">
        <Button variant="ghost" size="icon" className="connection-back-btn shrink-0 rounded-full" asChild>
          <Link href="/insights/organic-growth" aria-label="Back to Insights" title="Back to Insights">
            <svg width="18" height="18" viewBox="0 0 24 24" aria-hidden="true">
              <path
                d="M15 18 9 12l6-6"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          </Link>
        </Button>
        <h1 className="page-toolbar-title text-2xl font-semibold tracking-tight">Models</h1>
        <span aria-live="polite" className={`mt-saved${saved ? " mt-saved--on" : ""}`}>
          {saved}
        </span>
      </div>

      <Tabs defaultValue="tiers">
        <TabsList>
          <TabsTrigger value="tiers">Tiers</TabsTrigger>
          <TabsTrigger value="providers">Providers</TabsTrigger>
        </TabsList>

        {/* ---------------------------------------------------------------- */}
        <TabsContent value="tiers">
          <p className="app-subtle mt-lede">
            Pick three models. Duct decides which one each job deserves — and falls down the
            list when a model has no key. {configuredCount === 0 && "You're on the defaults."}
          </p>

          <div className="mt-tiers">
            {TIERS.map((tier, index) => (
              <TierCard
                key={tier.key}
                tier={tier}
                index={index}
                value={
                  picks[tier.key] ||
                  (catalogue?.tiers ?? []).find((row) => row.id === tier.key)?.default_model ||
                  ""
                }
                models={models}
                providersById={providersById}
                engine={DEFAULT_ENGINE}
                loading={!catalogue}
                jobs={jobsByTier[tier.key] || []}
                preview={previewByTier[tier.key]}
                onChange={setTier}
              />
            ))}
          </div>

          {/* The ladder, drawn. Three cards side by side show three settings;
              they do not show that one falls through to the next, which is the
              part that surprises people when a key is missing. */}
          <div className="mt-chain" aria-hidden="true">
            {TIERS.map((tier, index) => {
              const row = previewByTier[tier.key];
              const Icon = TIER_ICONS[tier.icon] || Scale;
              const dead = row && !row.runnable;
              return (
                <span key={tier.key} className="mt-chain-step">
                  {index > 0 && <ArrowRight className="mt-chain-arrow" size={13} />}
                  <span className={`mt-chain-node${dead ? " mt-chain-node--dead" : ""}`}>
                    <Icon size={13} strokeWidth={1.75} />
                    {tier.label}
                  </span>
                </span>
              );
            })}
            <span className="mt-chain-step">
              <ArrowRight className="mt-chain-arrow" size={13} />
              <span className="mt-chain-node mt-chain-node--floor">this engine&rsquo;s default</span>
            </span>
          </div>
          <p className="mt-chain-note">
            Each tier falls through to the next when its model has no key, and to the
            engine&rsquo;s own default when none of them can run.
          </p>

          {/* Sits directly under the ladder because it is a question about the
              ladder: the fallback order is the three models above, in the order
              they are already in. Asking for a second order here is what would
              have made this page a maze. */}
          <AutoFallbackCard ladder={TIERS.map((tier) => tier.label)} />

          <div className="mt-actions">
            <span className="mt-actions-label">
              <Wand2 size={14} aria-hidden="true" /> Only have one key?
            </span>
            {fillable.map((provider) => (
              <Button
                key={provider.id}
                type="button"
                variant="outline"
                size="sm"
                onClick={() => fillFromProvider(provider.statusId)}
              >
                Fill from {provider.label}
              </Button>
            ))}
            {configuredCount > 0 && (
              <Button type="button" variant="ghost" size="sm" onClick={resetToDefaults}>
                Reset to defaults
              </Button>
            )}
          </div>

          {/* How the data those models read is written on the way in. Sits with
              the tiers rather than with the provider keys because it is a
              question about a run, not about a credential. */}
          <h2 className="mt-section-title">Context</h2>
          <p className="app-subtle mt-lede">
            What your connectors return can be larger than a model can hold in one go.
          </p>

          <ContextCompressionCard />

          {/* Modality — only what the tier models cannot produce themselves. */}
          <h2 className="mt-section-title">Images &amp; video</h2>
          <p className="app-subtle mt-lede">
            Shown only for what your tier models cannot make on their own.
          </p>

          <div className="mt-modality">
            <ImagesRow images={images} catalogue={catalogue} providersById={providersById} />

            <div className="mt-mod-row">
              <div className="mt-mod-name">
                <span className="mt-mod-mark" aria-hidden="true">
                  <Video size={15} strokeWidth={1.75} />
                </span>
                <div>
                  <strong>Video</strong>
                  <span>Short-form video · Content Studio</span>
                </div>
              </div>
              <div className="mt-mod-ctl">
                <StateChip tone="neutral">Not connected</StateChip>
              </div>
              <p className="mt-mod-note">
                Video generation is a connected service, not a model you pick here.
              </p>
            </div>
          </div>
        </TabsContent>

        {/* ---------------------------------------------------------------- */}
        <TabsContent value="providers">
          <p className="app-subtle mt-lede">
            Duct runs on your own provider keys &mdash; paste one below and it&rsquo;s sent with
            each request. On desktop they live in your OS keychain; in a browser they stay in this
            session unless you ask Duct to remember one, which saves it encrypted so scheduled runs
            can use it too. Use a budget-capped or restricted key where your provider offers one.
          </p>

          <div className="conn-grid">
            {/* Desktop only, and only while the backend allows the path —
                renders nothing otherwise. First because it is the one
                provider that costs nothing extra. */}
            <ChatGPTCard enabled={chatgptAuthEnabled} />
            {PROVIDERS.map((provider) => (
              <ProviderCard
                key={provider.id}
                provider={provider}
                logo={LOGOS[provider.id]}
                status={providersById[provider.statusId]}
              />
            ))}
            {/* Desktop only, and only in a build that can actually report —
                renders nothing otherwise. It belongs on this page because this
                is where the other "what leaves my machine" decisions are made. */}
            <TelemetryCard />
          </div>
        </TabsContent>

      </Tabs>
    </section>
  );
}
