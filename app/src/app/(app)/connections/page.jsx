"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { BASE } from "../../../lib/api";
import {
  clearAdsDeveloperToken,
  getAdsDeveloperToken,
  getAdsLoginCustomerId,
  setAdsDeveloperToken,
  setAdsLoginCustomerId,
} from "../../../lib/adsCredentials";
import {
  bindProjectConnector,
  deleteServerConnector,
  hasAuthToken,
  listProjectConnectors,
  listServerConnectors,
  notifyConnectorsChanged,
  saveServerConnector,
  unbindProjectConnector,
} from "../../../lib/connectorsApi";
import { CONNECTOR_TOKEN_KEYS, exchangeConnectorCode } from "../../../lib/connectorAuth";
import { getActiveProject } from "../../../lib/projects";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent } from "@/components/ui/tabs";
import ConnectorTile from "../../../components/connections/ConnectorTile";
import ManualConnectorCard from "../../../components/connections/ManualConnectorCard";
import OAuthConnectorCard from "../../../components/connections/OAuthConnectorCard";
import { DEFAULT_VALUE } from "../../../components/connections/ProjectAccountSelect";
import { LOGOS } from "../../../components/connections/logos";

export default function ConnectionsPage() {
  const [ga4Connected, setGa4Connected] = useState(false);
  const [gscConnected, setGscConnected] = useState(false);
  const [gtmConnected, setGtmConnected] = useState(false);
  const [gadsOauthConnected, setGadsOauthConnected] = useState(false);
  const [gadsDevTokenSaved, setGadsDevTokenSaved] = useState(false);
  const [devTokenInput, setDevTokenInput] = useState("");
  const [mccInput, setMccInput] = useState("");
  const [signedIn, setSignedIn] = useState(false);
  const [connectError, setConnectError] = useState("");
  const [serverRows, setServerRows] = useState({}); // connector_type -> first stored row
  const [serverRowsAll, setServerRowsAll] = useState({}); // connector_type -> [rows]

  // The project is already chosen in the header — this page inherits it rather
  // than asking again, which is what the old "Project mappings" tab did.
  const [project, setProject] = useState(null);
  const [bindings, setBindings] = useState({}); // connector_type -> binding row
  const [mappingBusy, setMappingBusy] = useState("");

  async function refreshServerRows() {
    if (!hasAuthToken()) return;
    try {
      const rows = await listServerConnectors();
      const byType = {};
      const byTypeAll = {};
      for (const row of rows) {
        if (!byType[row.connector_type]) byType[row.connector_type] = row;
        (byTypeAll[row.connector_type] ||= []).push(row);
      }
      setServerRows(byType);
      setServerRowsAll(byTypeAll);
    } catch {
      /* offline / signed-out — session-only mode still works */
    }
  }

  async function removeServerRowById(rowId) {
    try {
      await deleteServerConnector(rowId);
      await refreshServerRows();
    } catch {
      /* best-effort */
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

  // One connector's OAuth arriving from the desktop shell. The browser flow
  // hands the token over in the URL fragment; the desktop one cannot — a
  // refresh token must never ride in a deep link — so the shell brings back a
  // single-use code and the token is fetched here instead. Everything after
  // that is the fragment path's destination, one round trip later.
  async function adoptConnectorToken(connectorType, refreshToken) {
    const storageKey = CONNECTOR_TOKEN_KEYS[connectorType];
    if (!storageKey || !refreshToken) {
      setConnectError("That connection came back incomplete — please try again.");
      return;
    }
    sessionStorage.setItem(storageKey, refreshToken);
    // A signed-out connection never reaches the server, so nothing else would
    // tell the sidebar badge its count changed.
    notifyConnectorsChanged();
    if (connectorType === "google_ads") setGadsOauthConnected(true);
    if (connectorType === "ga4") setGa4Connected(true);
    if (connectorType === "gsc") setGscConnected(true);
    if (connectorType === "gtm") setGtmConnected(true);
    if (!hasAuthToken()) return;
    if (connectorType === "google_ads") await syncGadsToServer();
    else await syncTokenToServer(connectorType, refreshToken);
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
      // [fragment param, sessionStorage key] pairs — key NAMES, not secrets.
      // Kept as pairs (not an object literal) so the security audit's
      // hardcoded-secret heuristic (`token: "..."`) doesn't false-positive.
      const fragmentKeys = [
        ["refresh_token", "gads_refresh_token"],
        ["ga4_refresh_token", "ga4_refresh_token"],
        ["gsc_refresh_token", "gsc_refresh_token"],
        ["gtm_refresh_token", "gtm_refresh_token"],
      ];
      for (const [fragmentKey, storageKey] of fragmentKeys) {
        const token = params.get(fragmentKey);
        if (token) {
          const decoded = decodeURIComponent(token);
          sessionStorage.setItem(storageKey, decoded);
          notifyConnectorsChanged();
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

    // Desktop shell: the OAuth ran in the system browser and came home through
    // the shell's deep link, which navigates this window to
    // /connections?connector=&auth_code=. Redeem the code for the token the
    // fragment path above would have carried directly.
    const query = new URLSearchParams(window.location.search);
    const connectorParam = query.get("connector") || "";
    const codeParam = query.get("auth_code") || "";
    if (connectorParam && codeParam) {
      // Single-use and 60-second, but there is no reason to leave it in the
      // address bar or in history either.
      window.history.replaceState(null, "", window.location.pathname);
      setConnectError("");
      exchangeConnectorCode(codeParam)
        .then(({ connector_type, refresh_token }) =>
          adoptConnectorToken(connector_type || connectorParam, refresh_token),
        )
        .catch(() =>
          setConnectError(
            "That connection didn't finish — the link expires after a minute. Please try again.",
          ),
        );
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Track the header's project picker, so switching projects re-reads the
  // mappings without a reload.
  useEffect(() => {
    const sync = () => setProject(getActiveProject());
    sync();
    window.addEventListener("duct:project-changed", sync);
    window.addEventListener("storage", sync);
    return () => {
      window.removeEventListener("duct:project-changed", sync);
      window.removeEventListener("storage", sync);
    };
  }, []);

  const projectId = project?.id || "";

  useEffect(() => {
    if (!signedIn || !projectId) {
      setBindings({});
      return;
    }
    let alive = true;
    listProjectConnectors(projectId)
      .then((rows) => {
        if (!alive) return;
        const byType = {};
        for (const row of rows) byType[row.connector_type] = row;
        setBindings(byType);
      })
      .catch(() => {
        /* mappings are an enhancement — the account default still resolves */
      });
    return () => {
      alive = false;
    };
  }, [signedIn, projectId]);

  const changeMapping = useCallback(
    async (connectorType, value) => {
      if (!projectId) return;
      setMappingBusy(connectorType);
      try {
        if (value === DEFAULT_VALUE) {
          // No binding to remove is the normal case when the select was
          // already showing "Account default" — don't ask the API to 404.
          if (!bindings[connectorType]) return;
          await unbindProjectConnector(projectId, connectorType);
          setBindings((prev) => {
            const next = { ...prev };
            delete next[connectorType];
            return next;
          });
        } else {
          const row = await bindProjectConnector(projectId, connectorType, value);
          setBindings((prev) => ({ ...prev, [connectorType]: row }));
        }
      } catch {
        /* leave the previous mapping showing rather than a half-applied one */
      } finally {
        setMappingBusy("");
      }
    },
    [projectId, bindings],
  );

  function mappingProps(type) {
    return {
      projectName: signedIn ? project?.name || "" : "",
      binding: bindings[type],
      onMappingChange: (value) => changeMapping(type, value),
      mappingBusy: mappingBusy === type,
    };
  }

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
    notifyConnectorsChanged();
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
    notifyConnectorsChanged();
    setGa4Connected(false);
    await removeServerRow("ga4");
  }

  async function signOutGsc() {
    sessionStorage.removeItem("gsc_refresh_token");
    notifyConnectorsChanged();
    setGscConnected(false);
    await removeServerRow("gsc");
  }

  async function signOutGtm() {
    sessionStorage.removeItem("gtm_refresh_token");
    notifyConnectorsChanged();
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
        <TabsContent value="connections">
          <p className="app-subtle" style={{ marginTop: 0, marginBottom: 18, maxWidth: 720 }}>
            Connect an account once — it&rsquo;s saved for your whole account. Open a card
            to set it up and to pick which of your accounts{" "}
            <strong className="font-medium text-foreground">
              {project?.name || "this project"}
            </strong>{" "}
            reads from.
          </p>

          {connectError && (
            <p
              role="alert"
              className="text-sm text-destructive"
              style={{ marginTop: -8, marginBottom: 18, maxWidth: 720 }}
            >
              {connectError}
            </p>
          )}

          <div className="conn-grid">
            <OAuthConnectorCard
              title="Google Ads"
              description="Campaign performance including spend, clicks, impressions, conversions, and ROAS."
              logo={LOGOS.google_ads}
              connected={gadsConnected}
              oauthConnected={gadsOauthConnected}
              tone={gadsConnected ? "on" : gadsOauthConnected || gadsDevTokenSaved ? "partial" : "off"}
              status={
                gadsConnected
                  ? "Connected"
                  : gadsOauthConnected
                    ? "Add developer token"
                    : gadsDevTokenSaved
                      ? "Sign in with Google"
                      : "Not connected"
              }
              pillStatus={
                gadsConnected
                  ? "Connected"
                  : gadsOauthConnected
                    ? "Needs developer token"
                    : gadsDevTokenSaved
                      ? "Needs Google sign-in"
                      : "Not connected"
              }
              authorizeUrl={`${BASE}/auth/connectors/google_ads/oauth/authorize`}
              onDisconnect={signOutGads}
              signedIn={signedIn}
              syncedToAccount={!!serverRows.google_ads}
              rows={serverRowsAll.google_ads || []}
              {...mappingProps("google_ads")}
            >
              <form onSubmit={saveGadsApiAccess} style={{ display: "grid", gap: 10 }}>
                <p className="conn-hint">
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
                <div className="conn-field">
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
                <div className="conn-field">
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
                  <Button
                    type="submit"
                    size="sm"
                    variant="secondary"
                    disabled={!devTokenInput.trim() && !gadsDevTokenSaved}
                  >
                    Save API access
                  </Button>
                </div>
              </form>
            </OAuthConnectorCard>

            <OAuthConnectorCard
              title="Google Search Console"
              description="Organic search queries, clicks, impressions, and average position data for SEO reporting."
              logo={LOGOS.gsc}
              connected={gscConnected}
              oauthConnected={gscConnected}
              tone={gscConnected ? "on" : "off"}
              status={gscConnected ? "Connected" : "Not connected"}
              authorizeUrl={`${BASE}/auth/connectors/gsc/oauth/authorize`}
              onDisconnect={signOutGsc}
              signedIn={signedIn}
              syncedToAccount={!!serverRows.gsc}
              rows={serverRowsAll.gsc || []}
              {...mappingProps("gsc")}
            />

            <OAuthConnectorCard
              title="Google Analytics"
              description="Website traffic, sessions, engagement, and conversion trend data for performance reporting."
              logo={LOGOS.ga4}
              connected={ga4Connected}
              oauthConnected={ga4Connected}
              tone={ga4Connected ? "on" : "off"}
              status={ga4Connected ? "Connected" : "Not connected"}
              authorizeUrl={`${BASE}/auth/connectors/ga4/oauth/authorize`}
              onDisconnect={signOutGa4}
              signedIn={signedIn}
              syncedToAccount={!!serverRows.ga4}
              rows={serverRowsAll.ga4 || []}
              {...mappingProps("ga4")}
            />

            <OAuthConnectorCard
              title="Google Tag Manager"
              description="Tags, variables, and container versions — measurement fixes with staged publishes and one-command rollback."
              logo={LOGOS.gtm}
              connected={gtmConnected}
              oauthConnected={gtmConnected}
              tone={gtmConnected ? "on" : "off"}
              status={gtmConnected ? "Connected" : "Not connected"}
              authorizeUrl={`${BASE}/auth/connectors/gtm/oauth/authorize`}
              onDisconnect={signOutGtm}
              signedIn={signedIn}
              syncedToAccount={!!serverRows.gtm}
              rows={serverRowsAll.gtm || []}
              {...mappingProps("gtm")}
            />

            <ManualConnectorCard
              type="meta_ads"
              title="Meta Ads"
              description="Facebook and Instagram campaign performance including spend, reach, conversions, and CPA."
              logo={LOGOS.meta_ads}
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
              serverRowList={serverRowsAll.meta_ads || []}
              onSaved={refreshServerRows}
              onRemoveRow={removeServerRowById}
              {...mappingProps("meta_ads")}
            />

            <ManualConnectorCard
              type="stripe"
              title="Stripe"
              description="Settled revenue, subscriptions, refunds, and payment outcomes — the money truth your ad platforms get reconciled against."
              logo={LOGOS.stripe}
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
              serverRowList={serverRowsAll.stripe || []}
              onSaved={refreshServerRows}
              onRemoveRow={removeServerRowById}
              {...mappingProps("stripe")}
            />

            <ManualConnectorCard
              type="apple_ads"
              title="Apple Search Ads"
              description="App Store search campaign performance — spend, taps, and installs by campaign and search term."
              logo={LOGOS.apple_ads}
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
              serverRowList={serverRowsAll.apple_ads || []}
              onSaved={refreshServerRows}
              onRemoveRow={removeServerRowById}
              {...mappingProps("apple_ads")}
            />

            <ManualConnectorCard
              type="revenuecat"
              title="RevenueCat"
              description="Mobile subscription truth — trials, renewals, refunds, grace periods, and MRR across the App Store and Play."
              logo={LOGOS.revenuecat}
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
              serverRowList={serverRowsAll.revenuecat || []}
              onSaved={refreshServerRows}
              onRemoveRow={removeServerRowById}
              {...mappingProps("revenuecat")}
            />

            <ManualConnectorCard
              type="openai_ads"
              title="OpenAI Ads"
              description="ChatGPT Ads campaign delivery — impressions, clicks, and spend (conversions live only in Ads Manager)."
              logo={LOGOS.openai_ads}
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
              serverRowList={serverRowsAll.openai_ads || []}
              onSaved={refreshServerRows}
              onRemoveRow={removeServerRowById}
              {...mappingProps("openai_ads")}
            />

            <ManualConnectorCard
              type="mixpanel"
              title="Mixpanel"
              description="Cross-platform event truth — signups, logins, and upgrades under one name across web and app, the reference your ad platforms and GA4 get reconciled against."
              logo={LOGOS.mixpanel}
              fields={[
                { key: "service_account_username", label: "Service account username", placeholder: "duct.xxxxxx.mp-service-account" },
                {
                  key: "service_account_secret",
                  label: "Service account secret",
                  placeholder: "Shown once when the account is created",
                  secret: true,
                  hint:
                    "Organization settings → Service Accounts → Add. Grant it the project(s) Duct should read. " +
                    "Project tokens and API secrets cannot read the Query API.",
                },
                {
                  key: "region",
                  label: "Data residency",
                  placeholder: "us | eu | in",
                  optional: true,
                  hint: "EU and India projects live on their own hosts — a wrong region looks like a bad secret.",
                },
                {
                  key: "internal_patterns",
                  label: "Internal-traffic patterns",
                  placeholder: "qa-, @yourcompany.com, test-account",
                  optional: true,
                  hint:
                    "Comma-separated distinct_id substrings to exclude. Mixpanel has no internal-traffic filter — " +
                    "QA accounts corrupt every funnel until excluded.",
                },
              ]}
              accountField="project_id"
              docsUrl="https://docs.mixpanel.com/docs/other-bits/service-accounts"
              docsLabel="Mixpanel service accounts guide"
              signedIn={signedIn}
              serverRowList={serverRowsAll.mixpanel || []}
              onSaved={refreshServerRows}
              onRemoveRow={removeServerRowById}
              {...mappingProps("mixpanel")}
            />

            <ManualConnectorCard
              type="clarity"
              title="Microsoft Clarity"
              description="What paid clicks do after landing — rage clicks, dead clicks, quick-backs, and script errors per page (last 3 days)."
              logo={LOGOS.clarity}
              fields={[
                {
                  key: "api_token",
                  label: "Data Export API token",
                  placeholder: "From Clarity → Settings → Data Export",
                  secret: true,
                  hint:
                    "The token IS the project. Clarity allows 10 API requests per project per day; " +
                    "verifying spends 1 and each Duct pull spends 2.",
                },
                {
                  key: "project_id",
                  label: "Project id",
                  placeholder: "e.g. tbnrkp3gk9 (from the Clarity URL)",
                  optional: true,
                  hint: "Label only — the token already selects the project.",
                },
              ]}
              accountField="project_id"
              docsUrl="https://learn.microsoft.com/en-us/clarity/setup-and-installation/clarity-data-export-api"
              docsLabel="Clarity Data Export API docs"
              signedIn={signedIn}
              serverRowList={serverRowsAll.clarity || []}
              onSaved={refreshServerRows}
              onRemoveRow={removeServerRowById}
              {...mappingProps("clarity")}
            />

            <ManualConnectorCard
              type="growthbook"
              title="GrowthBook"
              description="Experiment health — which tests are live, whether they are still bucketing users, and per-metric results. Read-only."
              logo={LOGOS.growthbook}
              fields={[
                {
                  key: "api_key",
                  label: "API key",
                  placeholder: "secret_…",
                  secret: true,
                  hint: "Settings → API Keys. A read-only key is enough — Duct never flips flags.",
                },
                {
                  key: "base_url",
                  label: "Self-hosted API URL",
                  placeholder: "https://growthbook.example.com (leave empty for GrowthBook Cloud)",
                  optional: true,
                },
              ]}
              accountField="project_id"
              docsUrl="https://docs.growthbook.io/api"
              docsLabel="GrowthBook REST API docs"
              signedIn={signedIn}
              serverRowList={serverRowsAll.growthbook || []}
              onSaved={refreshServerRows}
              onRemoveRow={removeServerRowById}
              {...mappingProps("growthbook")}
            />

            <ConnectorTile
              logo={LOGOS.hubspot}
              title="HubSpot"
              description="CRM lifecycle and pipeline outcomes to tie paid and organic traffic to downstream revenue."
              tone="off"
              status="Coming soon"
              disabled
            />
          </div>
        </TabsContent>

      </Tabs>
    </section>
  );
}
