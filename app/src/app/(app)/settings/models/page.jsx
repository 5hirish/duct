"use client";

/**
 * Models — the one page that answers "which model runs my work, whose key pays
 * for it, and what has that cost me".
 *
 * The first two questions used to live elsewhere: the model came from a server
 * env var nobody could see, and the provider keys sat on the Connections page
 * next to Google Ads. The failure that produced was specific — you could paste
 * an OpenAI key, watch it save, and have every run still go to Claude, with
 * nothing anywhere saying why.
 *
 * The third is the Usage tab, and it is here rather than only in the sidebar
 * because it is the evidence for the choice the other two tabs ask for. It
 * shares its whole implementation with `/usage`.
 *
 * ── On the shape of the Tiers tab ──
 *
 * This page had grown to ~300 words and twelve blocks of prose on that tab
 * alone. Every sentence had been added to fix a real failure and every one was
 * individually defensible; nothing had ever argued for the whole, which is the
 * specific way an agent-written surface fails. The rule that reorganised it:
 * **most people bring one key**, so the front door is the setup you already
 * have plus a row of providers to switch it to, and the three-way choice is
 * behind Customise. The tiers themselves did not change — they are still real,
 * still three, still resolved by the server.
 *
 * What went where, since a reader will look for the missing parts:
 *  * the fallback rule was told four times (a per-card chip, the chain, the
 *    note under it, and the quota switch's copy) — now the chain, once;
 *  * the credential chip repeated on all three cards — now one sentence on the
 *    summary, and per-card only when the three tiers disagree;
 *  * job chips and tier blurbs — gone; the tagline already says what the
 *    tier is for, and nine chips across the row explained a decision nobody
 *    is being asked to make;
 *  * quota fallback and context compression — Advanced. The image model came
 *    back *out* of that fold and into the summary card: it is a fourth thing
 *    Duct runs on your key, and it now picks rather than only reports.
 *
 * A third tab, Runtime, picked the agent harness. Once v3 was removed it
 * offered a single engine, always active, already selected — a radio group
 * with one button. The engine is still a question the server is asked (it
 * scopes the catalogue and the tier preview), just no longer one to answer
 * here; DEFAULT_ENGINE is what goes over the wire.
 */

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Anvil, ArrowRight, Feather, Scale } from "lucide-react";
import { Trans, useLingui } from "@lingui/react/macro";
import { Button } from "@/components/ui/button";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import ProviderCard from "@/components/connections/ProviderCard";
import TelemetryCard from "@/components/TelemetryCard.jsx";
import AdvancedSettings from "@/components/models/AdvancedSettings";
import TierCard from "@/components/models/TierCard";
import TierSummary from "@/components/models/TierSummary";
import UsagePanel from "@/components/models/UsagePanel";
import { LOGOS } from "@/components/connections/logos";
import { PROVIDERS } from "@/lib/providerKeys";
import {
  MODEL_MAP_CHANGED,
  TIERS,
  fetchModelCatalogue,
  fetchProviderStatus,
  fetchTierPreview,
  loadModelMap,
  agreedSource,
  saveModelMap,
  tierPicks,
} from "@/lib/modelTiers";
import { fetchModelSettings, saveModelSettings } from "@/lib/modelSettings";
import { DEFAULT_ENGINE } from "@/lib/engines";

/**
 * The tab lives in the URL so a refresh lands where you were.
 *
 * It used to be `defaultValue` — uncontrolled — which meant every reload of a
 * page whose whole purpose is pasting a key dropped you back on Tiers, with
 * the field you were filling one click away and no sign that it had moved.
 * Anything that sends someone here to add a key can now say so in the link.
 */
const TAB_QUERY = "tab";
const TABS = ["tiers", "providers", "usage"];

/** The tier's own mark, for the chain. Same three the cards use. */
const TIER_ICONS = { anvil: Anvil, scale: Scale, feather: Feather };

function ModelSettings() {
  const { t, i18n } = useLingui();
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  // An unknown `?tab=` is someone's typo or a stale link, not a fourth view —
  // fall back rather than render a page with no tab selected at all.
  const requested = searchParams.get(TAB_QUERY);
  const tab = TABS.includes(requested) ? requested : TABS[0];

  const [map, setMap] = useState({});
  const [catalogue, setCatalogue] = useState(null);
  // null until the server answers, not []. An empty array is a real answer
  // ("no providers"), and the cards rendered it as "Not set" — a definite
  // claim about every provider, made before anything had been asked.
  const [providers, setProviders] = useState(null);
  // The server's pick for the image tools, or null until it answers.
  const [images, setImages] = useState(null);
  // The backend's kill switch for the ChatGPT tile; off until it answers.
  const [chatgptAuthEnabled, setChatgptAuthEnabled] = useState(false);
  const [preview, setPreview] = useState(null);
  // Closed until asked for. The summary above it is the whole answer for
  // anyone on one key, which is most people.
  const [customising, setCustomising] = useState(false);
  const [saved, setSaved] = useState("");
  const savedTimer = useRef(null);

  // First paint: everything the page renders is server-owned except the map.
  useEffect(() => {
    setMap(loadModelMap());
    // The server's copy is the one every run reads — including the scheduled
    // brief, which has no browser. localStorage paints first so the page is
    // never blank; this corrects it a moment later, and a stale tab loses.
    fetchModelSettings().then((settings) => {
      const tiers = Object.keys(settings.tiers || {}).length ? settings.tiers : null;
      if (!tiers && !settings.image_model) return;
      setMap((current) => {
        const next = { ...current };
        if (tiers) next.tiers = tiers;
        // Mirrors the tier map: the server's copy is what a run reads, and the
        // local one only paints first.
        if (settings.image_model) {
          next.modality = { ...(current.modality || {}), image: settings.image_model };
        }
        saveModelMap(next);
        return next;
      });
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
    for (const provider of providers ?? []) byId[provider.id] = provider;
    return byId;
  }, [providers]);

  const previewByTier = useMemo(() => {
    const byTier = {};
    for (const row of preview?.tiers ?? []) byTier[row.id] = row;
    return byTier;
  }, [preview]);

  // What each tier is actually set to, defaults filled in. Both the summary
  // and the cards read this, so neither can disagree with the other about
  // which model a tier is on.
  const effective = useMemo(() => {
    const byTier = {};
    for (const tier of TIERS) {
      byTier[tier.key] =
        picks[tier.key] ||
        (catalogue?.tiers ?? []).find((row) => row.id === tier.key)?.default_model ||
        "";
    }
    return byTier;
  }, [picks, catalogue]);

  // Whose key pays, when all three tiers say the same thing. The summary
  // prints it, the tier cards stay quiet about it, and the Images row omits
  // its own chip when its answer is this one — three surfaces, one fact.
  const sharedSource = useMemo(
    () => agreedSource(previewByTier, providersById),
    [previewByTier, providersById]
  );

  // The whole catalogue. The picker annotates what this engine cannot serve
  // rather than hiding it — see ModelPicker for why filtering was wrong.
  const models = catalogue?.models ?? [];

  // `replace`, not `push`: the tabs are one page seen three ways, and a Back
  // button that walks back through tab switches instead of leaving is the
  // thing nobody expects. `scroll: false` because a tab change is not a
  // navigation you should be yanked to the top for.
  const selectTab = useCallback(
    (next) => {
      const params = new URLSearchParams(searchParams);
      params.set(TAB_QUERY, next);
      router.replace(`${pathname}?${params}`, { scroll: false });
    },
    [pathname, router, searchParams]
  );

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
    commit({ ...map, tiers: nextTiers }, t`Saved`);
  }

  function setImageModel(model) {
    const modality = { ...(map.modality || {}) };
    // Absent, not empty-string: an absent key is what `modelPayload` already
    // treats as "nothing configured", and writing "" would make an untouched
    // install start sending a modality block that says nothing.
    if (model) modality.image = model;
    else delete modality.image;
    const next = { ...map, modality };
    setMap(next);
    saveModelMap(next);
    saveModelSettings({ image_model: model || "" });
    flash(t`Saved`);
  }

  function fillFromProvider(providerId) {
    const triple = catalogue?.provider_triples?.[providerId];
    if (!triple) return;
    const providerLabel = providersById[providerId]?.label || providerId;
    commit({ ...map, tiers: { ...triple } }, t`Switched to ${providerLabel}`);
  }

  function resetToDefaults() {
    const { tiers, ...rest } = map;
    commit(rest, t`Reset to defaults`);
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
          <Link href="/insights/organic-growth" aria-label={t`Back to Insights`} title={t`Back to Insights`}>
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
        {/* Same words as the menu item that leads here — a menu reading
            "Models & providers" that lands on a page headed "Models" reads as
            the wrong page for half a second, every time. */}
        <h1 className="page-toolbar-title text-2xl font-semibold tracking-tight">
          <Trans>Models &amp; providers</Trans>
        </h1>
        <span aria-live="polite" className={`mt-saved${saved ? " mt-saved--on" : ""}`}>
          {saved}
        </span>
      </div>

      <Tabs value={tab} onValueChange={selectTab}>
        <TabsList>
          <TabsTrigger value="tiers"><Trans>Tiers</Trans></TabsTrigger>
          <TabsTrigger value="providers"><Trans>Providers</Trans></TabsTrigger>
          {/* Third because it is the evidence for the first two, and reading
              it is what makes them worth changing. */}
          <TabsTrigger value="usage"><Trans>Usage</Trans></TabsTrigger>
        </TabsList>

        {/* ---------------------------------------------------------------- */}
        <TabsContent value="tiers">
          <TierSummary
            picks={effective}
            models={models}
            providersById={providersById}
            previewByTier={previewByTier}
            loading={!catalogue}
            expanded={customising}
            onToggle={() => setCustomising((open) => !open)}
            fillable={fillable}
            onFill={fillFromProvider}
            configuredCount={configuredCount}
            onReset={resetToDefaults}
            images={images}
            imageModels={catalogue?.image_models ?? []}
            imagePick={map.modality?.image || ""}
            onImageChange={setImageModel}
          />

          {customising && (
            <div className="mt-custom">
              <p className="app-subtle mt-lede">
                <Trans>Duct sends each job to the rung it deserves. Pick what sits on each one.</Trans>
              </p>

              <div className="mt-tiers">
                {TIERS.map((tier, index) => (
                  <TierCard
                    key={tier.key}
                    tier={tier}
                    index={index}
                    value={effective[tier.key]}
                    models={models}
                    providersById={providersById}
                    engine={DEFAULT_ENGINE}
                    loading={!catalogue}
                    preview={previewByTier[tier.key]}
                    showSource={!sharedSource}
                    onChange={setTier}
                  />
                ))}
              </div>

              {/* The ladder, drawn — and the only place the fall-through rule
                  is stated. Three cards side by side show three settings; they
                  do not show that one falls through to the next, which is the
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
                        {i18n._(tier.label)}
                      </span>
                    </span>
                  );
                })}
                <span className="mt-chain-step">
                  <ArrowRight className="mt-chain-arrow" size={13} />
                  <span className="mt-chain-node mt-chain-node--floor"><Trans>this engine&rsquo;s default</Trans></span>
                </span>
              </div>
              <p className="mt-chain-note">
                <Trans>A tier whose model has no key falls through to the next one along.</Trans>
              </p>
            </div>
          )}

          <AdvancedSettings ladder={TIERS.map((tier) => i18n._(tier.label))} />
        </TabsContent>

        {/* ---------------------------------------------------------------- */}
        <TabsContent value="providers">
          {/* Where a key is kept used to be spelled out here in full — keychain,
              session, remembered-and-encrypted — which is the same answer each
              card gives for itself, for its own provider, with the storage
              glyph beside it. Two copies of that rule is how one of them goes
              stale. This says what the page is for; the card says where your
              key went. */}
          <p className="app-subtle mt-lede">
            <Trans>
              Duct runs on your own provider keys &mdash; paste one below, and its card says
              where that key is kept. Use a restricted or budget-capped key if your provider
              offers one.
            </Trans>
          </p>

          <div className="conn-grid">
            {/* The ChatGPT plan is inside the OpenAI card, not a tile of its
                own: one company, one card. `planEnabled` is the backend's
                kill switch for that path and only OpenAI reads it. */}
            {PROVIDERS.map((provider) => (
              <ProviderCard
                key={provider.id}
                provider={provider}
                logo={LOGOS[provider.id]}
                status={providersById[provider.statusId]}
                planEnabled={chatgptAuthEnabled}
                loading={providers === null}
              />
            ))}
            {/* Desktop only, and only in a build that can actually report —
                renders nothing otherwise. It belongs on this page because this
                is where the other "what leaves my machine" decisions are made. */}
            <TelemetryCard />
          </div>
        </TabsContent>

        {/* ---------------------------------------------------------------- */}
        <TabsContent value="usage">
          {/* The catalogue is already loaded for the pickers, so the rows can
              name models the same way the pickers do rather than printing the
              raw id the provider answered with. */}
          <UsagePanel catalogue={catalogue} />
        </TabsContent>
      </Tabs>
    </section>
  );
}

export default function ModelSettingsPage() {
  // useSearchParams needs a Suspense boundary in the App Router. The fallback
  // is the toolbar alone: the tab it is waiting on decides everything below
  // it, so guessing one would flash the wrong half of the page.
  return (
    <Suspense
      fallback={
        <section>
          <div className="page-toolbar-back">
            <h1 className="page-toolbar-title text-2xl font-semibold tracking-tight">
              <Trans>Models &amp; providers</Trans>
            </h1>
          </div>
          <p className="app-subtle"><Trans>Loading&hellip;</Trans></p>
        </section>
      }
    >
      <ModelSettings />
    </Suspense>
  );
}
