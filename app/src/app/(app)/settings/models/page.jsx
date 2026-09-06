"use client";

/**
 * Models & engine — the one page that answers "which model runs my work, and
 * whose key pays for it".
 *
 * Three questions used to live on three surfaces: the model came from a server
 * env var nobody could see, the engine came from a dialog in the account menu,
 * and the provider keys sat on the Connections page next to Google Ads. The
 * failure that produced was specific — you could paste an OpenAI key, watch it
 * save, and have every run still go to Claude, with nothing anywhere saying
 * why. Putting the three in one tabbed page is the fix.
 *
 * The tabs are ordered by how often they are touched: Tiers is the setting,
 * Providers is the thing you visit when a tier says it needs a key, Runtime is
 * the thing most people never open.
 */

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Anvil, ArrowRight, ChevronRight, Feather, ImageIcon, KeyRound, Scale, Video, Wand2 } from "lucide-react";
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
import ProviderCard from "@/components/connections/ProviderCard";
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
import { ENGINES, DEFAULT_ENGINE, ENGINE_STORAGE_KEY, ENGINE_STATUS } from "@/lib/engines";
import { fetchEngineStatus } from "@/lib/api";

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

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function ModelSettingsPage() {
  const [map, setMap] = useState({});
  const [catalogue, setCatalogue] = useState(null);
  const [providers, setProviders] = useState([]);
  const [preview, setPreview] = useState(null);
  const [engine, setEngine] = useState(DEFAULT_ENGINE);
  const [engineStatuses, setEngineStatuses] = useState({});
  const [saved, setSaved] = useState("");
  const savedTimer = useRef(null);

  // First paint: everything the page renders is server-owned except the map.
  useEffect(() => {
    setMap(loadModelMap());
    try {
      setEngine(localStorage.getItem(ENGINE_STORAGE_KEY) || DEFAULT_ENGINE);
    } catch {
      /* storage disabled — the default engine is a fine answer */
    }
    fetchModelCatalogue().then(setCatalogue);
    fetchProviderStatus().then(setProviders);
    fetchEngineStatus().then(setEngineStatuses);
  }, []);

  const picks = useMemo(() => tierPicks(map), [map]);
  // Depend on the *content* of the picks, not the object identity. Reading
  // storage on mount replaces `map` with an equal-but-new object, which would
  // otherwise fire a second, identical resolve on every page load.
  const picksKey = JSON.stringify(picks);

  // Re-resolve whenever the draft or the engine changes. The page never
  // computes what will run — it asks.
  useEffect(() => {
    let alive = true;
    fetchTierPreview(JSON.parse(picksKey), engine).then((next) => {
      if (alive) setPreview(next);
    });
    return () => {
      alive = false;
    };
  }, [picksKey, engine]);

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

  function chooseEngine(key) {
    setEngine(key);
    try {
      localStorage.setItem(ENGINE_STORAGE_KEY, key);
      // The sidebar badge and the generate page listen for this; the Engine
      // dialog dispatched the same synthetic event, so nothing downstream
      // notices that the dialog is gone.
      window.dispatchEvent(
        new StorageEvent("storage", {
          key: ENGINE_STORAGE_KEY,
          newValue: key,
          storageArea: localStorage,
        })
      );
    } catch {
      /* storage disabled — the choice still applies to this session */
    }
    flash("Engine changed");
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
          <TabsTrigger value="runtime">Runtime</TabsTrigger>
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
                engine={engine}
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

          {/* Modality — only what the tier models cannot produce themselves. */}
          <h2 className="mt-section-title">Images &amp; video</h2>
          <p className="app-subtle mt-lede">
            Shown only for what your tier models cannot make on their own.
          </p>

          <div className="mt-modality">
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
                <ProviderMark providerId="google_genai" />
                <code className="mt-mono">gemini-3.1-flash-image</code>
                <StateChip tone="ok" title="Chosen for you — no tier model can generate images">
                  Auto
                </StateChip>
              </div>
              <p className="mt-mod-note">
                None of your tier models generate images, so Duct uses a dedicated one.
              </p>
            </div>

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
            Bring your own provider keys. They stay in this browser session — in the OS keychain
            on desktop — and are sent with each request, never stored on our servers. Tip: use a
            budget-capped or restricted key.
          </p>

          <div className="conn-grid">
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

        {/* ---------------------------------------------------------------- */}
        <TabsContent value="runtime">
          <p className="app-subtle mt-lede">
            The harness that runs the agents. Most people never change this — it decides what
            agents <em>can do</em>, not how good they are.
          </p>

          <div className="mt-engines">
            {ENGINES.map((option) => {
              const status = engineStatuses[option.key];
              const unavailable = status && status.status !== ENGINE_STATUS.ACTIVE;
              const active = engine === option.key;
              return (
                <button
                  key={option.key}
                  type="button"
                  className={`mt-engine${active ? " mt-engine--on" : ""}`}
                  onClick={() => !unavailable && chooseEngine(option.key)}
                  disabled={Boolean(unavailable)}
                  aria-pressed={active}
                >
                  <span className="mt-engine-badge">{option.badge}</span>
                  <span className="mt-engine-body">
                    <strong>{option.label}</strong>
                    <span>{option.description}</span>
                  </span>
                  <StateChip tone={unavailable ? "warn" : "ok"}>
                    {unavailable ? "Inactive" : "Active"}
                  </StateChip>
                </button>
              );
            })}
          </div>

          <p className="app-subtle mt-footnote">
            <KeyRound size={13} aria-hidden="true" /> Every agent runs on any provider you hold a
            key for. A tier you have no key for falls through to the next one down.{" "}
            <Link className="app-link" href="/connections">
              Data source connections <ChevronRight size={12} aria-hidden="true" />
            </Link>
          </p>
        </TabsContent>
      </Tabs>
    </section>
  );
}
