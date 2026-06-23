"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Eye, EyeOff, Video } from "lucide-react";
import { BASE } from "../../../lib/api";
import { PROVIDERS, getProviderKey, setProviderKey, clearProviderKey } from "../../../lib/providerKeys";
import { listConnectors, saveConnector, deleteConnector } from "../../../lib/connectorsApi";
import { ProviderLogo } from "@/components/ProviderLogo";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";

export default function ConnectionsPage() {
  const [ga4Connected, setGa4Connected] = useState(false);
  const [gscConnected, setGscConnected] = useState(false);

  useEffect(() => {
    const hash = window.location.hash;
    if (hash.startsWith("#")) {
      const params = new URLSearchParams(hash.slice(1));
      const ga4Token = params.get("ga4_refresh_token");
      const gscToken = params.get("gsc_refresh_token");
      if (ga4Token) sessionStorage.setItem("ga4_refresh_token", decodeURIComponent(ga4Token));
      if (gscToken) sessionStorage.setItem("gsc_refresh_token", decodeURIComponent(gscToken));
      window.history.replaceState(null, "", window.location.pathname);
    }

    setGa4Connected(!!sessionStorage.getItem("ga4_refresh_token"));
    setGscConnected(!!sessionStorage.getItem("gsc_refresh_token"));
  }, []);

  function signOutGa4() {
    sessionStorage.removeItem("ga4_refresh_token");
    setGa4Connected(false);
  }

  function signOutGsc() {
    sessionStorage.removeItem("gsc_refresh_token");
    setGscConnected(false);
  }

  return (
    <section>
      <div className="page-toolbar-back">
        <Button
          variant="ghost"
          size="icon"
          className="connection-back-btn shrink-0 rounded-full"
          asChild
        >
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
        <h1 className="page-toolbar-title text-2xl font-semibold tracking-tight">Connections</h1>
      </div>

      <Tabs defaultValue="connections">
        <TabsList>
          <TabsTrigger value="connections">Data sources</TabsTrigger>
          <TabsTrigger value="providers">Providers</TabsTrigger>
        </TabsList>

        <TabsContent value="connections">
      <p className="app-subtle" style={{ marginTop: 0, marginBottom: 18 }}>
        Manage data source connections for insights. Choose your Google Ads account when you{" "}
        <Link href="/insights/organic-growth/generate" className="app-link">
          generate an insight
        </Link>
        .
      </p>

      <div className="connection-grid">
        <article className="connection-card">
          <div className="connection-card-head">
            <div className="connection-logo" aria-hidden="true">
              <img
                src="https://upload.wikimedia.org/wikipedia/commons/c/c7/Google_Ads_logo.svg"
                alt="Google Ads logo"
                width="28"
                height="28"
              />
            </div>
            <div>
              <h2 className="connection-title">Google Ads</h2>
              <p className="connection-description">
                Campaign performance metrics including spend, clicks, impressions, conversions, and ROAS.
              </p>
            </div>
          </div>
          <div className="connection-status-row">
            <span className="status-pill yellow">Coming Soon</span>
            <Button type="button" variant="secondary" size="sm" disabled>
              Coming Soon
            </Button>
          </div>
        </article>

        <article className="connection-card">
          <div className="connection-card-head">
            <div className="connection-logo" aria-hidden="true">
              <img
                src="/icons/google-search-console.png"
                alt="Google Search Console logo"
                width="28"
                height="28"
              />
            </div>
            <div>
              <h2 className="connection-title">Google Search Console</h2>
              <p className="connection-description">
                Organic search queries, clicks, impressions, and average position data for SEO reporting.
              </p>
            </div>
          </div>
          <div className="connection-status-row">
            <span className={`status-pill ${gscConnected ? "green" : "grey"}`}>
              {gscConnected ? "Connected" : "Not connected"}
            </span>
            {gscConnected ? (
              <Button type="button" variant="outline" size="sm" onClick={signOutGsc}>
                Disconnect
              </Button>
            ) : (
              <Button size="sm" asChild>
                <a href={`${BASE}/auth/connectors/gsc/oauth/authorize`}>Connect</a>
              </Button>
            )}
          </div>
        </article>

        <article className="connection-card">
          <div className="connection-card-head">
            <div className="connection-logo" aria-hidden="true">
              <img
                src="https://upload.wikimedia.org/wikipedia/commons/7/77/GAnalytics.svg"
                alt="Google Analytics logo"
                width="28"
                height="28"
              />
            </div>
            <div>
              <h2 className="connection-title">Google Analytics</h2>
              <p className="connection-description">
                Website traffic, sessions, engagement, and conversion trend data for performance reporting.
              </p>
            </div>
          </div>
          <div className="connection-status-row">
            <span className={`status-pill ${ga4Connected ? "green" : "grey"}`}>
              {ga4Connected ? "Connected" : "Not connected"}
            </span>
            {ga4Connected ? (
              <Button type="button" variant="outline" size="sm" onClick={signOutGa4}>
                Disconnect
              </Button>
            ) : (
              <Button size="sm" asChild>
                <a href={`${BASE}/auth/connectors/ga4/oauth/authorize`}>Connect</a>
              </Button>
            )}
          </div>
        </article>

        <HiggsfieldCard />

        <article className="connection-card">
          <div className="connection-card-head">
            <div className="connection-logo" aria-hidden="true">
              <img
                src="/icons/meta-ads.svg"
                alt="Meta Ads logo"
                width="28"
                height="28"
              />
            </div>
            <div>
              <h2 className="connection-title">Meta Ads</h2>
              <p className="connection-description">
                Facebook and Instagram campaign performance including spend, reach, conversions, and CPA.
              </p>
            </div>
          </div>
          <div className="connection-status-row">
            <span className="status-pill yellow">Coming soon</span>
            <Button type="button" variant="secondary" size="sm" disabled>
              Coming soon
            </Button>
          </div>
        </article>

        <article className="connection-card">
          <div className="connection-card-head">
            <div className="connection-logo" aria-hidden="true">
              <img
                src="https://upload.wikimedia.org/wikipedia/commons/b/ba/Stripe_Logo%2C_revised_2016.svg"
                alt="Stripe logo"
                width="28"
                height="28"
              />
            </div>
            <div>
              <h2 className="connection-title">Stripe</h2>
              <p className="connection-description">
                Revenue, subscriptions, churn, and payment outcomes to connect marketing performance to business impact.
              </p>
            </div>
          </div>
          <div className="connection-status-row">
            <span className="status-pill yellow">Coming soon</span>
            <Button type="button" variant="secondary" size="sm" disabled>
              Coming soon
            </Button>
          </div>
        </article>

        <article className="connection-card">
          <div className="connection-card-head">
            <div className="connection-logo" aria-hidden="true">
              <img
                src="/icons/hubspot.svg"
                alt="HubSpot logo"
                width="28"
                height="28"
              />
            </div>
            <div>
              <h2 className="connection-title">HubSpot</h2>
              <p className="connection-description">
                CRM lifecycle and pipeline outcomes to tie paid and organic traffic to downstream revenue.
              </p>
            </div>
          </div>
          <div className="connection-status-row">
            <span className="status-pill yellow">Coming soon</span>
            <Button type="button" variant="secondary" size="sm" disabled>
              Coming soon
            </Button>
          </div>
        </article>
      </div>
        </TabsContent>

        <TabsContent value="providers">
          <ProvidersPanel />
        </TabsContent>
      </Tabs>

    </section>
  );
}

// Higgsfield — AI video generation for content posts. Unlike the Google cards
// (OAuth redirect) this is a token paste stored server-side via
// /api/user/connectors; the headless content runner reads it to wire the
// Higgsfield MCP when drafting a video. See service/higgsfield/auth.py.
function HiggsfieldCard() {
  const [connected, setConnected] = useState(false);
  const [connectorId, setConnectorId] = useState(null);
  const [token, setToken] = useState("");
  const [revealed, setRevealed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let alive = true;
    listConnectors()
      .then((rows) => {
        if (!alive) return;
        const hf = rows.find((r) => r.connector_type === "higgsfield");
        if (hf) {
          setConnected(true);
          setConnectorId(hf.id);
        }
      })
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, []);

  async function connect() {
    const trimmed = token.trim();
    if (!trimmed) return;
    setBusy(true);
    setError("");
    try {
      const row = await saveConnector({
        connectorType: "higgsfield",
        accountName: "Higgsfield",
        credentials: { api_token: trimmed },
      });
      setConnected(true);
      setConnectorId(row.id);
      setToken("");
    } catch {
      setError("Couldn't save the token — make sure you're signed in, then try again.");
    } finally {
      setBusy(false);
    }
  }

  async function disconnect() {
    if (!connectorId) return;
    setBusy(true);
    setError("");
    try {
      await deleteConnector(connectorId);
      setConnected(false);
      setConnectorId(null);
    } catch {
      setError("Couldn't disconnect — try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <article className="connection-card">
      <div className="connection-card-head">
        <div className="connection-logo" aria-hidden="true">
          <Video size={24} />
        </div>
        <div>
          <h2 className="connection-title">Higgsfield</h2>
          <p className="connection-description">
            AI video generation for content posts — generate and clone short videos. Billed to your
            Higgsfield subscription.
          </p>
        </div>
      </div>

      {connected ? (
        <div className="connection-status-row">
          <span className="status-pill green">Connected</span>
          <Button type="button" variant="outline" size="sm" onClick={disconnect} disabled={busy}>
            Disconnect
          </Button>
        </div>
      ) : (
        <>
          <div className="prov-field" style={{ marginTop: 8 }}>
            <div className="prov-input-wrap">
              <Input
                type={revealed ? "text" : "password"}
                value={token}
                placeholder="Higgsfield token"
                onChange={(event) => setToken(event.target.value)}
                autoComplete="off"
                autoCapitalize="off"
                autoCorrect="off"
                spellCheck={false}
                aria-label="Higgsfield token"
              />
              <button
                type="button"
                className="prov-reveal"
                onClick={() => setRevealed((shown) => !shown)}
                disabled={!token}
                aria-label={revealed ? "Hide token" : "Show token"}
              >
                {revealed ? <EyeOff size={16} /> : <Eye size={16} />}
              </button>
            </div>
          </div>
          <p className="prov-help">
            Generate a token with <code>higgsfield auth login</code> (or copy one from your Higgsfield
            dashboard).
          </p>
          <div className="connection-status-row">
            <span className="status-pill grey">Not connected</span>
            <Button type="button" size="sm" onClick={connect} disabled={busy || !token.trim()}>
              Connect
            </Button>
          </div>
        </>
      )}

      {error && <p className="prov-help prov-help--warn">{error}</p>}
    </article>
  );
}

function ProvidersPanel() {
  return (
    <>
      <p className="app-subtle prov-intro" style={{ marginTop: 0, marginBottom: 20 }}>
        Bring your own model keys. During the beta they power generation on your
        own account — keys live only in this browser session, travel encrypted
        with each request, and never touch our servers. Use a budget-capped key
        if you can.
      </p>
      <div className="connection-grid">
        {PROVIDERS.map((provider) => (
          <ProviderCard key={provider.id} provider={provider} />
        ))}
      </div>
    </>
  );
}

function ProviderCard({ provider }) {
  const supportsOauth = Boolean(provider.oauth);
  const [value, setValue] = useState("");
  const [saved, setSaved] = useState(false);
  const [revealed, setRevealed] = useState(false);
  const [busy, setBusy] = useState(false);
  // Which credential the card is entering. Only a hint to the user and the
  // backend (which routes by prefix) — initialised from a saved value's shape.
  const [mode, setMode] = useState("api");

  useEffect(() => {
    let alive = true;
    getProviderKey(provider.id).then((stored) => {
      if (!alive) return;
      setValue(stored || "");
      setSaved(Boolean(stored));
      if (supportsOauth && stored && stored.trim().startsWith(provider.oauth.prefix)) {
        setMode("oauth");
      }
    });
    return () => {
      alive = false;
    };
  }, [provider.id, supportsOauth, provider.oauth]);

  const oauthMode = mode === "oauth" && supportsOauth;
  const cred = oauthMode ? provider.oauth : provider;
  const credLabel = oauthMode ? "OAuth token" : "API key";
  const trimmed = value.trim();
  const looksValid = !cred.prefix || trimmed.startsWith(cred.prefix);

  async function save() {
    setBusy(true);
    await setProviderKey(provider.id, trimmed);
    setSaved(Boolean(trimmed));
    setBusy(false);
  }

  async function remove() {
    setBusy(true);
    await clearProviderKey(provider.id);
    setValue("");
    setSaved(false);
    setBusy(false);
  }

  return (
    <article className={`connection-card prov-card${provider.recommended ? " prov-card--recommended" : ""}`}>
      <div className="prov-head">
        <span className={`prov-logo prov-logo--${provider.id}`} aria-hidden="true">
          <ProviderLogo id={provider.id} />
        </span>
        <div className="prov-head-text">
          <h3 className="prov-title">
            {provider.label}
            {provider.recommended && <span className="prov-tag">Recommended</span>}
          </h3>
          <p className="prov-desc">{provider.description}</p>
        </div>
      </div>

      <div className="prov-powers">
        <span className="prov-powers-label">Powers</span>
        {provider.powers.map((agent) => (
          <span key={agent} className="prov-chip">
            {agent}
          </span>
        ))}
      </div>

      {supportsOauth && (
        <div className="prov-seg" role="tablist" aria-label={`${provider.label} credential type`}>
          <button
            type="button"
            role="tab"
            aria-selected={!oauthMode}
            className="prov-seg-btn"
            onClick={() => setMode("api")}
          >
            API key
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={oauthMode}
            className="prov-seg-btn"
            onClick={() => setMode("oauth")}
          >
            OAuth token
          </button>
        </div>
      )}

      <div className="prov-field">
        <div className="prov-input-wrap">
          <Input
            type={revealed ? "text" : "password"}
            value={value}
            placeholder={cred.placeholder}
            onChange={(event) => setValue(event.target.value)}
            autoComplete="off"
            autoCapitalize="off"
            autoCorrect="off"
            spellCheck={false}
            aria-label={`${provider.label} ${credLabel}`}
          />
          <button
            type="button"
            className="prov-reveal"
            onClick={() => setRevealed((shown) => !shown)}
            disabled={!value}
            aria-label={revealed ? `Hide ${credLabel}` : `Show ${credLabel}`}
          >
            {revealed ? <EyeOff size={16} /> : <Eye size={16} />}
          </button>
        </div>
      </div>

      {trimmed && !looksValid ? (
        <p className="prov-help prov-help--warn">
          {oauthMode ? (
            <>
              OAuth tokens start with “{cred.prefix}”. Generate one with{" "}
              <code>{provider.oauth.setup}</code>.
            </>
          ) : (
            <>API keys start with “{cred.prefix}”.</>
          )}
        </p>
      ) : oauthMode ? (
        <p className="prov-help">
          {provider.oauth.hint} Generate one with <code>{provider.oauth.setup}</code>.
        </p>
      ) : (
        <p className="prov-help">
          Billed to your {provider.label} account.{" "}
          <a className="app-link" href={provider.consoleUrl} target="_blank" rel="noreferrer">
            Get a key
          </a>
          .
        </p>
      )}

      <div className="prov-foot">
        <span className={`status-pill ${saved ? "green" : "grey"}`}>
          <span className="prov-dot" />
          {saved ? "Saved" : "Not set"}
        </span>
        <div className="prov-foot-actions">
          {saved && (
            <Button type="button" variant="outline" size="sm" onClick={remove} disabled={busy}>
              Remove
            </Button>
          )}
          <Button type="button" size="sm" onClick={save} disabled={busy || !trimmed || !looksValid}>
            Save
          </Button>
        </div>
      </div>
    </article>
  );
}
