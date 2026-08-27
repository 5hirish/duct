"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { BASE } from "../../../lib/api";
import {
  clearAdsDeveloperToken,
  getAdsDeveloperToken,
  getAdsLoginCustomerId,
  setAdsDeveloperToken,
  setAdsLoginCustomerId,
} from "../../../lib/adsCredentials";
import { PROVIDERS, getProviderKey, setProviderKey, clearProviderKey } from "../../../lib/providerKeys";
import {
  deleteServerConnector,
  hasAuthToken,
  listServerConnectors,
  saveServerConnector,
} from "../../../lib/connectorsApi";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import ManualConnectorCard from "../../../components/connections/ManualConnectorCard";

export default function ConnectionsPage() {
  const [ga4Connected, setGa4Connected] = useState(false);
  const [gscConnected, setGscConnected] = useState(false);
  const [gtmConnected, setGtmConnected] = useState(false);
  const [gadsOauthConnected, setGadsOauthConnected] = useState(false);
  const [gadsDevTokenSaved, setGadsDevTokenSaved] = useState(false);
  const [devTokenInput, setDevTokenInput] = useState("");
  const [mccInput, setMccInput] = useState("");
  const [signedIn, setSignedIn] = useState(false);
  const [serverRows, setServerRows] = useState({}); // connector_type -> stored row

  async function refreshServerRows() {
    if (!hasAuthToken()) return;
    try {
      const rows = await listServerConnectors();
      const byType = {};
      for (const row of rows) byType[row.connector_type] = row;
      setServerRows(byType);
    } catch {
      /* offline / signed-out — session-only mode still works */
    }
  }

  // Upserts replace the stored blob whole, so a Google Ads sync must always
  // carry all three fields (refresh token + developer token + MCC).
  async function syncGadsToServer() {
    if (!hasAuthToken()) return;
    const refreshToken = sessionStorage.getItem("gads_refresh_token") || "";
    if (!refreshToken) return;
    const developerToken = (await getAdsDeveloperToken()) || "";
    const loginCustomerId = getAdsLoginCustomerId() || "";
    try {
      await saveServerConnector({
        connector_type: "google_ads",
        credentials: {
          refresh_token: refreshToken,
          developer_token: developerToken,
          login_customer_id: loginCustomerId,
        },
      });
      await refreshServerRows();
    } catch {
      /* session-only fallback keeps working */
    }
  }

  async function syncTokenToServer(connectorType, refreshToken) {
    if (!hasAuthToken() || !refreshToken) return;
    try {
      await saveServerConnector({
        connector_type: connectorType,
        credentials: { refresh_token: refreshToken },
      });
      await refreshServerRows();
    } catch {
      /* session-only fallback keeps working */
    }
  }

  async function removeServerRow(connectorType) {
    const row = serverRows[connectorType];
    if (!row) return;
    try {
      await deleteServerConnector(row.id);
      await refreshServerRows();
    } catch {
      /* best-effort */
    }
  }

  useEffect(() => {
    const arrived = {};
    const hash = window.location.hash;
    if (hash.startsWith("#")) {
      const params = new URLSearchParams(hash.slice(1));
      const fragmentKeys = {
        refresh_token: "gads_refresh_token",
        ga4_refresh_token: "ga4_refresh_token",
        gsc_refresh_token: "gsc_refresh_token",
        gtm_refresh_token: "gtm_refresh_token",
      };
      for (const [fragmentKey, storageKey] of Object.entries(fragmentKeys)) {
        const token = params.get(fragmentKey);
        if (token) {
          const decoded = decodeURIComponent(token);
          sessionStorage.setItem(storageKey, decoded);
          arrived[storageKey] = decoded;
        }
      }
      window.history.replaceState(null, "", window.location.pathname);
    }

    setGadsOauthConnected(!!sessionStorage.getItem("gads_refresh_token"));
    setMccInput(getAdsLoginCustomerId());
    setGa4Connected(!!sessionStorage.getItem("ga4_refresh_token"));
    setGscConnected(!!sessionStorage.getItem("gsc_refresh_token"));
    setGtmConnected(!!sessionStorage.getItem("gtm_refresh_token"));
    getAdsDeveloperToken().then((token) => setGadsDevTokenSaved(!!token));

    const authed = hasAuthToken();
    setSignedIn(authed);
    if (authed) {
      refreshServerRows();
      // Persist newly-arrived OAuth tokens server-side (encrypted) so agent
      // executions and scheduled pulls can run without this browser tab.
      if (arrived.gads_refresh_token) syncGadsToServer();
      if (arrived.ga4_refresh_token) syncTokenToServer("ga4", arrived.ga4_refresh_token);
      if (arrived.gsc_refresh_token) syncTokenToServer("gsc", arrived.gsc_refresh_token);
      if (arrived.gtm_refresh_token) syncTokenToServer("gtm", arrived.gtm_refresh_token);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function saveGadsApiAccess(event) {
    event.preventDefault();
    const token = devTokenInput.trim();
    const mcc = mccInput.replace(/-/g, "").trim();
    if (token) {
      await setAdsDeveloperToken(token);
      setGadsDevTokenSaved(true);
      setDevTokenInput("");
    }
    setAdsLoginCustomerId(mcc);
    setMccInput(mcc);
    await syncGadsToServer();
  }

  async function signOutGads() {
    sessionStorage.removeItem("gads_refresh_token");
    sessionStorage.removeItem("gads_customer_id");
    await clearAdsDeveloperToken();
    setAdsLoginCustomerId("");
    setGadsOauthConnected(false);
    setGadsDevTokenSaved(false);
    setDevTokenInput("");
    setMccInput("");
    await removeServerRow("google_ads");
  }

  async function signOutGa4() {
    sessionStorage.removeItem("ga4_refresh_token");
    setGa4Connected(false);
    await removeServerRow("ga4");
  }

  async function signOutGsc() {
    sessionStorage.removeItem("gsc_refresh_token");
    setGscConnected(false);
    await removeServerRow("gsc");
  }

  async function signOutGtm() {
    sessionStorage.removeItem("gtm_refresh_token");
    setGtmConnected(false);
    await removeServerRow("gtm");
  }

  const gadsConnected = gadsOauthConnected && gadsDevTokenSaved;

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

          <form onSubmit={saveGadsApiAccess} style={{ display: "grid", gap: 10, marginTop: 12 }}>
            <p className="app-subtle" style={{ margin: 0, fontSize: 13 }}>
              Duct&rsquo;s Google Ads API access is pending Google approval — bring your own{" "}
              <a
                className="app-link"
                href="https://developers.google.com/google-ads/api/docs/get-started/dev-token"
                target="_blank"
                rel="noreferrer"
              >
                developer token
              </a>{" "}
              from your manager account. It stays on this device and is only sent with your requests.
            </p>
            <div style={{ display: "grid", gap: 4 }}>
              <Label htmlFor="gads-dev-token">Developer token</Label>
              <Input
                id="gads-dev-token"
                type="password"
                autoComplete="off"
                placeholder={gadsDevTokenSaved ? "Saved — paste to replace" : "Paste your developer token"}
                value={devTokenInput}
                onChange={(e) => setDevTokenInput(e.target.value)}
              />
            </div>
            <div style={{ display: "grid", gap: 4 }}>
              <Label htmlFor="gads-mcc">Manager account ID (MCC, optional)</Label>
              <Input
                id="gads-mcc"
                inputMode="numeric"
                placeholder="e.g. 1234567890"
                value={mccInput}
                onChange={(e) => setMccInput(e.target.value)}
              />
            </div>
            <div>
              <Button type="submit" size="sm" variant="secondary" disabled={!devTokenInput.trim() && !gadsDevTokenSaved}>
                Save API access
              </Button>
            </div>
          </form>

          <div className="connection-status-row">
            <span className={`status-pill ${gadsConnected ? "green" : gadsOauthConnected || gadsDevTokenSaved ? "yellow" : "grey"}`}>
              {gadsConnected
                ? "Connected"
                : gadsOauthConnected
                  ? "Add developer token"
                  : gadsDevTokenSaved
                    ? "Sign in with Google"
                    : "Not connected"}
            </span>
            {gadsOauthConnected ? (
              <Button type="button" variant="outline" size="sm" onClick={signOutGads}>
                Disconnect
              </Button>
            ) : (
              <Button size="sm" asChild>
                <a href={`${BASE}/auth/connectors/google_ads/oauth/authorize`}>Connect</a>
              </Button>
            )}
          </div>
          {gadsOauthConnected && (
            <ServerSyncHint signedIn={signedIn} saved={!!serverRows.google_ads} />
          )}
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
          {gscConnected && <ServerSyncHint signedIn={signedIn} saved={!!serverRows.gsc} />}
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
          {ga4Connected && <ServerSyncHint signedIn={signedIn} saved={!!serverRows.ga4} />}
        </article>

        <article className="connection-card">
          <div className="connection-card-head">
            <div className="connection-logo" aria-hidden="true">
              <svg
                width="28"
                height="28"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.6"
                strokeLinejoin="round"
              >
                <path d="M20.59 10.59 13.4 3.4a2 2 0 0 0-2.83 0l-7.17 7.18a2 2 0 0 0 0 2.83l7.17 7.18a2 2 0 0 0 2.83 0l7.18-7.18a2 2 0 0 0 0-2.83Z" />
                <circle cx="12" cy="12" r="1.6" fill="currentColor" stroke="none" />
              </svg>
            </div>
            <div>
              <h2 className="connection-title">Google Tag Manager</h2>
              <p className="connection-description">
                Tags, variables, and container versions — measurement fixes with staged
                publishes and one-command rollback.
              </p>
            </div>
          </div>
          <div className="connection-status-row">
            <span className={`status-pill ${gtmConnected ? "green" : "grey"}`}>
              {gtmConnected ? "Connected" : "Not connected"}
            </span>
            {gtmConnected ? (
              <Button type="button" variant="outline" size="sm" onClick={signOutGtm}>
                Disconnect
              </Button>
            ) : (
              <Button size="sm" asChild>
                <a href={`${BASE}/auth/connectors/gtm/oauth/authorize`}>Connect</a>
              </Button>
            )}
          </div>
          {gtmConnected && <ServerSyncHint signedIn={signedIn} saved={!!serverRows.gtm} />}
        </article>

        <ManualConnectorCard
          type="meta_ads"
          title="Meta Ads"
          description="Facebook and Instagram campaign performance including spend, reach, conversions, and CPA."
          logo={<img src="/icons/meta-ads.svg" alt="Meta Ads logo" width="28" height="28" />}
          fields={[
            {
              key: "access_token",
              label: "System User access token",
              placeholder: "EAA…",
              secret: true,
              hint:
                "Business settings → Users → System users → Generate token with scope ads_read " +
                "(+ business_management for account discovery). System User tokens don't expire; regular user tokens die in ~60 days.",
            },
            {
              key: "account_id",
              label: "Ad account id",
              placeholder: "act_1234567890",
              optional: true,
              hint: "Needed only if the token lacks business_management (no account discovery).",
            },
            { key: "app_secret", label: "App secret", placeholder: "Only if 'Require App Secret' is on", secret: true, optional: true },
          ]}
          accountField="account_id"
          docsUrl="https://business.facebook.com/settings/system-users"
          docsLabel="Create a System User token (Business settings)"
          signedIn={signedIn}
          serverRow={serverRows.meta_ads}
          onSaved={refreshServerRows}
          onRemove={removeServerRow}
        />

        <ManualConnectorCard
          type="stripe"
          title="Stripe"
          description="Settled revenue, subscriptions, refunds, and payment outcomes — the money truth your ad platforms get reconciled against."
          logo={<img src="https://upload.wikimedia.org/wikipedia/commons/b/ba/Stripe_Logo%2C_revised_2016.svg" alt="Stripe logo" width="28" height="28" />}
          fields={[
            {
              key: "api_key",
              label: "Restricted API key",
              placeholder: "rk_live_…",
              secret: true,
              hint:
                "Create a RESTRICTED key with read access to Subscriptions, Charges, Invoices, " +
                "Customers, Products and Prices. Duct only ever reads.",
            },
          ]}
          docsUrl="https://dashboard.stripe.com/apikeys"
          docsLabel="Create a restricted key (Stripe dashboard)"
          signedIn={signedIn}
          serverRow={serverRows.stripe}
          onSaved={refreshServerRows}
          onRemove={removeServerRow}
        />

        <ManualConnectorCard
          type="apple_ads"
          title="Apple Search Ads"
          description="App Store search campaign performance — spend, taps, and installs by campaign and search term."
          logo={<span style={{ fontSize: 22 }}>🍎</span>}
          fields={[
            { key: "client_id", label: "Client ID", placeholder: "SEARCHADS.xxxxxxxx-…" },
            { key: "team_id", label: "Team ID", placeholder: "SEARCHADS.xxxxxxxx-…" },
            { key: "key_id", label: "Key ID", placeholder: "xxxxxxxx-xxxx-…" },
            {
              key: "private_key",
              label: "EC private key (PEM)",
              placeholder: "-----BEGIN PRIVATE KEY-----…",
              multiline: true,
              hint:
                "Generate an EC P-256 key pair, upload the PUBLIC half at ads.apple.com → " +
                "Account Settings → API, then paste the private key here. Apple has no browser sign-in for this — key material is the official method.",
            },
          ]}
          accountField="org_id"
          docsUrl="https://searchads.apple.com/help/campaigns/0022-use-the-campaign-management-api"
          docsLabel="Apple's API access guide"
          signedIn={signedIn}
          serverRow={serverRows.apple_ads}
          onSaved={refreshServerRows}
          onRemove={removeServerRow}
        />

        <ManualConnectorCard
          type="revenuecat"
          title="RevenueCat"
          description="Mobile subscription truth — trials, renewals, refunds, grace periods, and MRR across the App Store and Play."
          logo={<span style={{ fontSize: 22 }}>📱</span>}
          fields={[
            {
              key: "api_key",
              label: "Secret API key (V2)",
              placeholder: "sk_…",
              secret: true,
              hint:
                "Project settings → API keys → Secret API key (V2) with the read scopes. " +
                "Public SDK keys (appl_/goog_) cannot read the REST API.",
            },
          ]}
          accountField="project_id"
          docsUrl="https://www.revenuecat.com/docs/projects/authentication"
          docsLabel="RevenueCat API keys guide"
          signedIn={signedIn}
          serverRow={serverRows.revenuecat}
          onSaved={refreshServerRows}
          onRemove={removeServerRow}
        />

        <ManualConnectorCard
          type="openai_ads"
          title="OpenAI Ads"
          description="ChatGPT Ads campaign delivery — impressions, clicks, and spend (conversions live only in Ads Manager)."
          logo={<span style={{ fontSize: 22 }}>✳️</span>}
          fields={[
            {
              key: "api_key",
              label: "Ads API key",
              placeholder: "From Ads Manager → Settings → API keys",
              secret: true,
              hint: "A key is scoped to ONE ad account — make sure it's the right one.",
            },
          ]}
          docsUrl="https://developers.openai.com/ads/api-quickstart"
          docsLabel="OpenAI Ads API quickstart"
          signedIn={signedIn}
          serverRow={serverRows.openai_ads}
          onSaved={refreshServerRows}
          onRemove={removeServerRow}
        />

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

function ServerSyncHint({ signedIn, saved }) {
  return (
    <p className="app-subtle" style={{ margin: "6px 0 0", fontSize: 12 }}>
      {saved
        ? "Synced to your account — available to agents and server-side runs."
        : signedIn
          ? "This session only — reconnect to sync to your account."
          : "This session only — sign in to sync to your account."}
    </p>
  );
}

function ProvidersPanel() {
  return (
    <>
      <p className="app-subtle" style={{ marginTop: 0, marginBottom: 18 }}>
        Bring your own model-provider API keys. During the beta these power
        insight generation on your own account. Keys stay in this browser
        session and are sent securely with each request — never stored on our
        servers. Tip: use a budget-capped or restricted key.
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
  const [value, setValue] = useState("");
  const [saved, setSaved] = useState(false);
  const [revealed, setRevealed] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let alive = true;
    getProviderKey(provider.id).then((stored) => {
      if (!alive) return;
      setValue(stored || "");
      setSaved(Boolean(stored));
    });
    return () => {
      alive = false;
    };
  }, [provider.id]);

  const trimmed = value.trim();
  const looksValid = !provider.prefix || trimmed.startsWith(provider.prefix);

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
    <article className="connection-card">
      <div className="connection-card-head">
        <div>
          <h2 className="connection-title">{provider.label}</h2>
          <p className="connection-description">
            {provider.description}{" "}
            <a className="app-link" href={provider.consoleUrl} target="_blank" rel="noreferrer">
              Get a key
            </a>
            .
          </p>
        </div>
      </div>

      <div style={{ display: "flex", gap: 8, marginTop: 4 }}>
        <Input
          type={revealed ? "text" : "password"}
          value={value}
          placeholder={provider.placeholder}
          onChange={(event) => setValue(event.target.value)}
          autoComplete="off"
          autoCapitalize="off"
          autoCorrect="off"
          spellCheck={false}
          aria-label={`${provider.label} API key`}
        />
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={() => setRevealed((shown) => !shown)}
          disabled={!value}
        >
          {revealed ? "Hide" : "Show"}
        </Button>
      </div>

      {trimmed && !looksValid && (
        <p className="app-subtle" style={{ marginTop: 6, fontSize: 12 }}>
          {`Keys usually start with "${provider.prefix}".`}
        </p>
      )}

      <div className="connection-status-row">
        <span className={`status-pill ${saved ? "green" : "grey"}`}>
          {saved ? "Saved" : "Not set"}
        </span>
        <div style={{ display: "flex", gap: 8 }}>
          {saved && (
            <Button type="button" variant="outline" size="sm" onClick={remove} disabled={busy}>
              Remove
            </Button>
          )}
          <Button
            type="button"
            size="sm"
            onClick={save}
            disabled={busy || !trimmed || !looksValid}
          >
            Save
          </Button>
        </div>
      </div>
    </article>
  );
}
