"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { Trans, useLingui } from "@lingui/react/macro";
import { plural } from "@lingui/core/macro";
import {
  bindProjectConnector,
  claimConnectorGrant,
  claimGitHubGrant,
  deleteServerConnector,
  getGitHubApp,
  hasAuthToken,
  listProjectConnectors,
  listServerConnectors,
  MCP_CONNECTOR,
  unbindProjectConnector,
  updateConnectorSettings,
} from "../../../lib/connectorsApi";
import {
  consumeConnectorReturn,
  markConnectorConnected,
  startConnectorOAuth,
} from "../../../lib/connectorAuth";
import { trackEvent, AnalyticsEvent } from "../../../lib/analytics";
import { getActiveProject } from "../../../lib/projects";
import { MCP_GUIDE_URL } from "../../../lib/mcpServers";
import { NATIVE_SOURCE } from "../../../lib/connectorSource";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent } from "@/components/ui/tabs";
import ConnectorTile from "../../../components/connections/ConnectorTile";
import ManualConnectorCard from "../../../components/connections/ManualConnectorCard";
import McpConnectors from "../../../components/connections/McpConnectors";
import OAuthConnectorCard from "../../../components/connections/OAuthConnectorCard";
import { DEFAULT_VALUE } from "../../../components/connections/ProjectAccountSelect";
import { LOGOS } from "../../../components/connections/logos";

export default function ConnectionsPage() {
  const { t } = useLingui();
  const router = useRouter();
  const notSignedInHere = t`Google approved the connection, but you're not signed in to Duct here, so it wasn't saved. Sign in, then connect again.`;
  // What the person is typing into the MCC field; null follows the stored value.
  const [mccDraft, setMccDraft] = useState(null);
  const [signedIn, setSignedIn] = useState(false);
  const [connectError, setConnectError] = useState("");
  const [connectNotice, setConnectNotice] = useState("");
  // Whether this server connects GitHub in one click. null until asked, and
  // for a signed-out visitor, who gets the token form the card always had.
  const [githubApp, setGithubApp] = useState(null);
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
      /* offline — the cards show what was last read */
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

  // A Google connector's grant, home from Google: the browser directly, the
  // desktop shell through its deep link. Claimed with this session — the
  // backend honours it only for the account whose link started the connect —
  // and stored there, never here. The card turns green from the row the claim
  // wrote, so a connection is never one this tab alone believes in.
  async function adoptConnectorGrant(connectorType, code) {
    try {
      const row = await claimConnectorGrant(code);
      await refreshServerRows();
      const provider = row?.connector_type || connectorType;
      // Activation. Only here, after the server took it: a claim that failed
      // is not a connection, and a disconnect is not an activation either.
      trackEvent(AnalyticsEvent.ConnectorConnected, { provider });
      await returnToRequester(provider, Promise.resolve());
    } catch (err) {
      setConnectError(
        err?.status === 401
          ? notSignedInHere
          : t`That connection didn't finish. The link lasts two minutes and works only for the account that started it. Please connect again.`,
      );
    }
  }

  // A connect that started from a conversation ends back in it. Only after
  // the server row is written: the agent answers "connected" by re-reading
  // the database, so returning a beat early would have it report the source
  // as still missing.
  async function returnToRequester(connectorType, pending) {
    const back = consumeConnectorReturn();
    if (!back) return;
    try {
      await pending;
    } catch {
      /* the card keeps its manual "I've connected it" button for this case */
    }
    markConnectorConnected(connectorType);
    router.replace(back);
  }

  // GitHub App (backend/service/github/app.py). A single-use link names this
  // session's user, then the same navigation every OAuth card makes.
  function connectGitHub() {
    return startConnectorOAuth("github");
  }

  // GitHub came back with a grant. Claimed by this signed-in session, which is
  // the only way an App grant is ever saved: the backend honours the code for
  // the account whose link started the connect and for nobody else.
  async function adoptGitHubGrant(code) {
    setConnectNotice("");
    try {
      const { connectors = [], omitted = 0 } = await claimGitHubGrant(code);
      await refreshServerRows();
      const count = connectors.length;
      if (!count) {
        setConnectNotice(
          t`GitHub is connected, but it granted no repositories you can read. Open the GitHub card and choose repositories on GitHub.`,
        );
        return;
      }
      trackEvent(AnalyticsEvent.ConnectorConnected, { provider: "github" });
      const connected = plural(count, {
        one: "GitHub connected: # repository.",
        other: "GitHub connected: # repositories.",
      });
      const more = omitted
        ? " " +
          plural(omitted, {
            one: "# more was left out; choose specific repositories on GitHub to reach it.",
            other: "# more were left out; choose specific repositories on GitHub to reach them.",
          })
        : "";
      setConnectNotice(connected + more);
      await returnToRequester("github", Promise.resolve());
    } catch {
      setConnectError(
        t`That GitHub connection didn't finish. The link lasts two minutes and works only for the account that started it. Please connect again.`,
      );
    }
  }

  useEffect(() => {
    const authed = hasAuthToken();
    setSignedIn(authed);
    if (authed) refreshServerRows();

    // Every sign-in connect comes home here as /connections?connector=&auth_code=:
    // the browser straight from the callback, the desktop shell through the
    // relay page and its deep link. The code is a claim ticket, not a token.
    const query = new URLSearchParams(window.location.search);
    const connectorParam = query.get("connector") || "";
    const codeParam = query.get("auth_code") || "";
    if (connectorParam === "github" && codeParam) {
      window.history.replaceState(null, "", window.location.pathname);
      setConnectError("");
      if (authed) adoptGitHubGrant(codeParam);
      else setConnectError(t`Sign in to finish connecting GitHub.`);
    } else if (connectorParam === "github" && query.get("installed")) {
      // Back from GitHub's install or configure page without our state, so
      // the backend could not tell whose it was. This page can: start the
      // connect again, which GitHub now answers without asking.
      window.history.replaceState(null, "", window.location.pathname);
      if (authed) {
        setConnectNotice(t`GitHub app installed. Finishing the connection…`);
        connectGitHub().catch(() =>
          setConnectError(t`GitHub is installed, but finishing the connection failed. Open the GitHub card and connect again.`),
        );
      } else {
        setConnectError(t`Sign in to finish connecting GitHub.`);
      }
    } else if (connectorParam === MCP_CONNECTOR) {
      // An MCP server's sign-in. McpConnectors claims it, with its own route:
      // the Google claim would not recognise its code.
    } else if (connectorParam && codeParam) {
      // Single-use and two minutes, but there is no reason to leave it in the
      // address bar or in history either.
      window.history.replaceState(null, "", window.location.pathname);
      setConnectError("");
      if (authed) adoptConnectorGrant(connectorParam, codeParam);
      else setConnectError(notSignedInHere);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!signedIn) return;
    let alive = true;
    getGitHubApp()
      .then((info) => alive && setGithubApp(info))
      .catch(() => {
        /* the token form still works */
      });
    return () => {
      alive = false;
    };
  }, [signedIn]);

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

  // Choosing an entity implies a binding: someone picking a Search Console
  // property has decided which credential this project uses, even if they never
  // touched the account row. Creating it here is what lets the account picker
  // stay hidden until a user actually has more than one account.
  const changeEntity = useCallback(
    async (connectorType, credentialId, { entityId, entityName }) => {
      if (!projectId || !credentialId) return;
      setMappingBusy(connectorType);
      try {
        const row = await bindProjectConnector(projectId, connectorType, credentialId, {
          entityId,
          entityName,
        });
        setBindings((prev) => ({ ...prev, [connectorType]: row }));
      } catch {
        /* leave the previous choice showing rather than a half-applied one */
      } finally {
        setMappingBusy("");
      }
    },
    [projectId],
  );

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
          const kept = bindings[connectorType];
          const row = await bindProjectConnector(projectId, connectorType, value, {
            entityId: kept?.entity_id || "",
            entityName: kept?.entity_name || "",
          });
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
      onEntityChange: (credentialId, choice) => changeEntity(type, credentialId, choice),
      mappingBusy: mappingBusy === type,
    };
  }

  // The manager (MCC) id lives on the stored Google Ads row beside the token,
  // so every device and every scheduled read uses the same one. The field
  // shows the stored value until someone types; a save merges it on the
  // server without touching the token.
  const gadsRow = serverRows.google_ads;
  const mccInput = mccDraft ?? (gadsRow?.settings?.login_customer_id || "");

  async function saveGadsManagerAccount(event) {
    event.preventDefault();
    if (!gadsRow) return;
    // Google Ads shows manager ids dashed and its API refuses them that way.
    const mcc = mccInput.replace(/-/g, "").trim();
    try {
      await updateConnectorSettings(gadsRow.id, { login_customer_id: mcc });
      await refreshServerRows();
      setMccDraft(null);
    } catch (err) {
      setConnectError(t`The manager account wasn't saved.` + (err?.message ? ` (${err.message})` : ""));
    }
  }

  // Disconnect forgets every stored account of the connector, not just the
  // first: picking a property stores a row per account, and one left behind
  // would keep the card green over a connection the user just removed.
  async function disconnect(connectorType) {
    try {
      await Promise.all((serverRowsAll[connectorType] || []).map((row) => deleteServerConnector(row.id)));
    } catch {
      /* the refresh below shows whatever is still stored */
    }
    if (connectorType === "google_ads") setMccDraft(null);
    await refreshServerRows();
  }

  // Connected means stored on the account. It used to also mean "this tab
  // holds a token", which is how a card read green in one tab and "Not
  // connected" in the next, and how a failed sync still turned it green.
  const gadsAuthorized = !!serverRows.google_ads;
  const ga4Authorized = !!serverRows.ga4;
  const gscAuthorized = !!serverRows.gsc;
  const gtmAuthorized = !!serverRows.gtm;

  // Authorized is not the same as fully permitted. Google's consent screen has
  // a tickbox per scope, so a connector can hold a valid token and still be
  // missing half of what it asked for — GA4 asks for analytics.edit alongside
  // readonly, GTM asks for three. Green there would claim access we do not
  // have, and the first sign of it would be a 403 mid-run.
  function scopeProps(type) {
    const row = serverRows[type] || {};
    return { scopes: row.scopes || [], scopeStatus: row.scope_status || "" };
  }

  function toneFor(authorized, type) {
    if (!authorized) return "off";
    return serverRows[type]?.scope_status === "partial" ? "partial" : "on";
  }

  function connectionStatusFor(authorized, type) {
    if (!authorized) return t`Not connected`;
    const missing = serverRows[type]?.missing_scopes?.length || 0;
    if (!missing) return t`Connected`;
    return plural(missing, {
      one: "Connected · # permission missing",
      other: "Connected · # permissions missing",
    });
  }

  const projectName = project?.name || t`this project`;

  // The MCP tiles report into the same two lines as every other connector.
  const showMcpMessage = useCallback(({ error = "", notice = "" }) => {
    setConnectError(error);
    setConnectNotice(notice);
  }, []);

  return (
    <section>
      <div className="page-toolbar-back">
        <Button
          variant="ghost"
          size="icon"
          className="connection-back-btn shrink-0 rounded-full"
          asChild
        >
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
        <h1 className="page-toolbar-title text-2xl font-semibold tracking-tight"><Trans>Connections</Trans></h1>
      </div>

      <Tabs defaultValue="connections">
        <TabsContent value="connections">
          <p className="app-subtle" style={{ marginTop: 0, marginBottom: 8, maxWidth: 720 }}>
            <Trans>
              Connect an account once — it&rsquo;s saved for your whole account. Open a card
              to set it up and to pick which of your accounts{" "}
              <strong className="font-medium text-foreground">{projectName}</strong>{" "}
              reads from.
            </Trans>
          </p>
          <p className="app-subtle" style={{ marginTop: 0, marginBottom: 18, maxWidth: 720 }}>
            <Trans>
              <strong className="font-medium text-foreground">Native</strong> connectors are built by Duct and feed
              briefs, alerts and the chat. <strong className="font-medium text-foreground">MCP</strong> connectors
              are each company&rsquo;s own server; the insights chat calls their tools.{" "}
              <a className="app-link underline underline-offset-2" href={MCP_GUIDE_URL} target="_blank" rel="noreferrer">
                How MCP works
              </a>
            </Trans>
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
          {connectNotice && !connectError && (
            <p
              role="status"
              className="text-sm text-muted-foreground"
              style={{ marginTop: -8, marginBottom: 18, maxWidth: 720 }}
            >
              {connectNotice}
            </p>
          )}

          <div className="conn-grid">
            <OAuthConnectorCard
              title={t`Google Ads`}
              description={t`Spend, clicks, impressions, conversions and ROAS, per campaign.`}
              logo={LOGOS.google_ads}
              connected={gadsAuthorized}
              oauthConnected={gadsAuthorized}
              tone={toneFor(gadsAuthorized, "google_ads")}
              {...scopeProps("google_ads")}
              status={connectionStatusFor(gadsAuthorized, "google_ads")}
              connectorType="google_ads"
              onDisconnect={() => disconnect("google_ads")}
              rows={serverRowsAll.google_ads || []}
              {...mappingProps("google_ads")}
            >
              <form onSubmit={saveGadsManagerAccount} style={{ display: "grid", gap: 10 }}>
                <p className="conn-hint">
                  <Trans>
                    Signing in with Google is all Duct needs. If your accounts sit under a manager
                    account, name it here so Duct reads the child accounts through it.
                  </Trans>
                </p>
                <div className="conn-field">
                  <Label htmlFor="gads-mcc"><Trans>Manager account ID (MCC, optional)</Trans></Label>
                  <Input
                    id="gads-mcc"
                    inputMode="numeric"
                    placeholder="e.g. 1234567890"
                    value={mccInput}
                    onChange={(e) => setMccDraft(e.target.value)}
                  />
                </div>
                <div>
                  <Button type="submit" size="sm" variant="secondary" disabled={!gadsAuthorized}>
                    <Trans>Save manager account</Trans>
                  </Button>
                </div>
              </form>
            </OAuthConnectorCard>

            <OAuthConnectorCard
              title={t`Google Search Console`}
              description={t`Search queries, clicks, impressions and average position.`}
              logo={LOGOS.gsc}
              connected={gscAuthorized}
              oauthConnected={gscAuthorized}
              tone={toneFor(gscAuthorized, "gsc")}
              status={connectionStatusFor(gscAuthorized, "gsc")}
              {...scopeProps("gsc")}
              connectorType="gsc"
              onDisconnect={() => disconnect("gsc")}
              rows={serverRowsAll.gsc || []}
              {...mappingProps("gsc")}
            />

            <OAuthConnectorCard
              title={t`Google Analytics`}
              description={t`Traffic, sessions, engagement and conversions.`}
              logo={LOGOS.ga4}
              connected={ga4Authorized}
              oauthConnected={ga4Authorized}
              tone={toneFor(ga4Authorized, "ga4")}
              status={connectionStatusFor(ga4Authorized, "ga4")}
              {...scopeProps("ga4")}
              connectorType="ga4"
              onDisconnect={() => disconnect("ga4")}
              rows={serverRowsAll.ga4 || []}
              {...mappingProps("ga4")}
            />

            <OAuthConnectorCard
              title={t`Google Tag Manager`}
              description={t`Tags, variables and container versions — staged, with rollback.`}
              logo={LOGOS.gtm}
              connected={gtmAuthorized}
              oauthConnected={gtmAuthorized}
              tone={toneFor(gtmAuthorized, "gtm")}
              status={connectionStatusFor(gtmAuthorized, "gtm")}
              {...scopeProps("gtm")}
              connectorType="gtm"
              onDisconnect={() => disconnect("gtm")}
              rows={serverRowsAll.gtm || []}
              {...mappingProps("gtm")}
            />

            <ManualConnectorCard
              type="meta_ads"
              title={t`Meta Ads`}
              description={t`Facebook and Instagram spend, reach, conversions and CPA.`}
              logo={LOGOS.meta_ads}
              fields={[
                {
                  key: "access_token",
                  label: t`System User access token`,
                  placeholder: "EAA…",
                  secret: true,
                  hint: t`Business settings → Users → System users → Generate token with scope ads_read (+ business_management for account discovery). System User tokens don't expire; regular user tokens die in ~60 days.`,
                },
                {
                  key: "account_id",
                  label: t`Ad account id`,
                  placeholder: "act_1234567890",
                  optional: true,
                  hint: t`Needed only if the token lacks business_management (no account discovery).`,
                },
                { key: "app_secret", label: t`App secret`, placeholder: t`Only if 'Require App Secret' is on`, secret: true, optional: true },
              ]}
              accountField="account_id"
              docsUrl="https://business.facebook.com/settings/system-users"
              docsLabel={t`Create a System User token (Business settings)`}
              signedIn={signedIn}
              serverRowList={serverRowsAll.meta_ads || []}
              onSaved={refreshServerRows}
              onRemoveRow={removeServerRowById}
              {...mappingProps("meta_ads")}
            />

            <ManualConnectorCard
              type="stripe"
              title="Stripe"
              description={t`Settled revenue, subscriptions, refunds and payment outcomes.`}
              logo={LOGOS.stripe}
              fields={[
                {
                  key: "api_key",
                  label: t`Restricted API key`,
                  placeholder: "rk_live_…",
                  secret: true,
                  hint: t`Create a RESTRICTED key with read access to Subscriptions, Charges, Invoices, Customers, Products and Prices. Duct only ever reads.`,
                },
              ]}
              docsUrl="https://dashboard.stripe.com/apikeys"
              docsLabel={t`Create a restricted key (Stripe dashboard)`}
              signedIn={signedIn}
              serverRowList={serverRowsAll.stripe || []}
              onSaved={refreshServerRows}
              onRemoveRow={removeServerRowById}
              {...mappingProps("stripe")}
            />

            <ManualConnectorCard
              type="apple_ads"
              title={t`Apple Search Ads`}
              description={t`Spend, taps and installs, by campaign and search term.`}
              logo={LOGOS.apple_ads}
              fields={[
                { key: "client_id", label: t`Client ID`, placeholder: "SEARCHADS.xxxxxxxx-…" },
                { key: "team_id", label: t`Team ID`, placeholder: "SEARCHADS.xxxxxxxx-…" },
                { key: "key_id", label: t`Key ID`, placeholder: "xxxxxxxx-xxxx-…" },
                {
                  key: "private_key",
                  label: t`EC private key (PEM)`,
                  placeholder: "-----BEGIN PRIVATE KEY-----…",
                  multiline: true,
                  hint: t`Generate an EC P-256 key pair, upload the PUBLIC half at ads.apple.com → Account Settings → API, then paste the private key here. Apple has no browser sign-in for this — key material is the official method.`,
                },
              ]}
              accountField="org_id"
              docsUrl="https://searchads.apple.com/help/campaigns/0022-use-the-campaign-management-api"
              docsLabel={t`Apple's API access guide`}
              signedIn={signedIn}
              serverRowList={serverRowsAll.apple_ads || []}
              onSaved={refreshServerRows}
              onRemoveRow={removeServerRowById}
              {...mappingProps("apple_ads")}
            />

            <ManualConnectorCard
              type="revenuecat"
              title={t`RevenueCat`}
              description={t`Trials, renewals, refunds and MRR across the App Store and Play.`}
              logo={LOGOS.revenuecat}
              fields={[
                {
                  key: "api_key",
                  label: t`Secret API key (V2)`,
                  placeholder: "sk_…",
                  secret: true,
                  hint: t`Project settings → API keys → Secret API key (V2) with the read scopes. Public SDK keys (appl_/goog_) cannot read the REST API.`,
                },
              ]}
              accountField="project_id"
              docsUrl="https://www.revenuecat.com/docs/projects/authentication"
              docsLabel={t`RevenueCat API keys guide`}
              signedIn={signedIn}
              serverRowList={serverRowsAll.revenuecat || []}
              onSaved={refreshServerRows}
              onRemoveRow={removeServerRowById}
              {...mappingProps("revenuecat")}
            />

            <ManualConnectorCard
              type="openai_ads"
              title={t`OpenAI Ads`}
              description={t`Impressions, clicks and spend. Conversions stay in Ads Manager.`}
              logo={LOGOS.openai_ads}
              fields={[
                {
                  key: "api_key",
                  label: t`Ads API key`,
                  placeholder: t`From Ads Manager → Settings → API keys`,
                  secret: true,
                  hint: t`A key is scoped to ONE ad account — make sure it's the right one.`,
                },
              ]}
              docsUrl="https://developers.openai.com/ads/api-quickstart"
              docsLabel={t`OpenAI Ads API quickstart`}
              signedIn={signedIn}
              serverRowList={serverRowsAll.openai_ads || []}
              onSaved={refreshServerRows}
              onRemoveRow={removeServerRowById}
              {...mappingProps("openai_ads")}
            />

            <ManualConnectorCard
              type="mixpanel"
              title="Mixpanel"
              description={t`Signups, logins and upgrades, one name across web and app.`}
              logo={LOGOS.mixpanel}
              fields={[
                { key: "service_account_username", label: t`Service account username`, placeholder: "duct.xxxxxx.mp-service-account" },
                {
                  key: "service_account_secret",
                  label: t`Service account secret`,
                  placeholder: t`Shown once when the account is created`,
                  secret: true,
                  hint: t`Organization settings → Service Accounts → Add. Grant it the project(s) Duct should read. Project tokens and API secrets cannot read the Query API.`,
                },
                {
                  key: "region",
                  label: t`Data residency`,
                  placeholder: "us | eu | in",
                  optional: true,
                  hint: t`EU and India projects live on their own hosts — a wrong region looks like a bad secret.`,
                },
                {
                  key: "internal_patterns",
                  label: t`Internal-traffic patterns`,
                  placeholder: t`qa-, @yourcompany.com, test-account`,
                  optional: true,
                  hint: t`Comma-separated distinct_id substrings to exclude. Mixpanel has no internal-traffic filter — QA accounts corrupt every funnel until excluded.`,
                },
              ]}
              accountField="project_id"
              docsUrl="https://docs.mixpanel.com/docs/other-bits/service-accounts"
              docsLabel={t`Mixpanel service accounts guide`}
              signedIn={signedIn}
              serverRowList={serverRowsAll.mixpanel || []}
              onSaved={refreshServerRows}
              onRemoveRow={removeServerRowById}
              {...mappingProps("mixpanel")}
            />

            <ManualConnectorCard
              type="clarity"
              title={t`Microsoft Clarity`}
              description={t`Rage clicks, dead clicks, quick-backs and script errors, per page.`}
              logo={LOGOS.clarity}
              fields={[
                {
                  key: "api_token",
                  label: t`Data Export API token`,
                  placeholder: t`From Clarity → Settings → Data Export`,
                  secret: true,
                  hint: t`The token IS the project. Clarity allows 10 API requests per project per day; verifying spends 1 and each Duct pull spends 2.`,
                },
                {
                  key: "project_id",
                  label: t`Project id`,
                  placeholder: t`e.g. tbnrkp3gk9 (from the Clarity URL)`,
                  optional: true,
                  hint: t`Label only — the token already selects the project.`,
                },
              ]}
              accountField="project_id"
              docsUrl="https://learn.microsoft.com/en-us/clarity/setup-and-installation/clarity-data-export-api"
              docsLabel={t`Clarity Data Export API docs`}
              signedIn={signedIn}
              serverRowList={serverRowsAll.clarity || []}
              onSaved={refreshServerRows}
              onRemoveRow={removeServerRowById}
              {...mappingProps("clarity")}
            />

            <ManualConnectorCard
              type="growthbook"
              title="GrowthBook"
              description={t`Which tests are live, whether they still bucket, per-metric results.`}
              logo={LOGOS.growthbook}
              fields={[
                {
                  key: "api_key",
                  label: t`API key`,
                  placeholder: "secret_…",
                  secret: true,
                  hint: t`Settings → API Keys. A read-only key is enough — Duct never flips flags.`,
                },
                {
                  key: "base_url",
                  label: t`Self-hosted API URL`,
                  placeholder: t`https://growthbook.example.com (leave empty for GrowthBook Cloud)`,
                  optional: true,
                },
              ]}
              accountField="project_id"
              docsUrl="https://docs.growthbook.io/api"
              docsLabel={t`GrowthBook REST API docs`}
              signedIn={signedIn}
              serverRowList={serverRowsAll.growthbook || []}
              onSaved={refreshServerRows}
              onRemoveRow={removeServerRowById}
              {...mappingProps("growthbook")}
            />

            <ManualConnectorCard
              type="github"
              title="GitHub"
              description={t`Merged pull requests, releases, closed issues and doc changes, by date.`}
              logo={LOGOS.github}
              fields={[
                {
                  key: "token",
                  label: t`Fine-grained personal access token`,
                  placeholder: "github_pat_…",
                  secret: true,
                  hint: t`Choose "Only select repositories", then read-only access to Contents, Pull requests, Issues and Metadata. Duct only ever reads.`,
                },
              ]}
              accountField="repo"
              docsUrl="https://github.com/settings/personal-access-tokens/new"
              docsLabel={t`Create a fine-grained token (GitHub settings)`}
              oneClick={
                githubApp?.available
                  ? {
                      label: t`Connect GitHub`,
                      againLabel: t`Refresh from GitHub`,
                      blurb: t`Choose the repositories on GitHub. Duct gets read-only access to those and nothing else.`,
                      waiting: t`Finish on GitHub in your browser. Your repositories appear here when you come back.`,
                      onStart: connectGitHub,
                      manageUrl: githubApp.manage_url,
                      manageLabel: t`Choose repositories on GitHub`,
                      tokenLabel: t`Use a token instead`,
                    }
                  : null
              }
              signedIn={signedIn}
              serverRowList={serverRowsAll.github || []}
              onSaved={refreshServerRows}
              onRemoveRow={removeServerRowById}
              {...mappingProps("github")}
            />

            <ConnectorTile
              logo={LOGOS.hubspot}
              title="HubSpot"
              source={NATIVE_SOURCE}
              description={t`CRM lifecycle stages, pipeline and closed revenue.`}
              tone="off"
              status={t`Coming soon`}
              disabled
            />

            <McpConnectors signedIn={signedIn} onMessage={showMcpMessage} />
          </div>
        </TabsContent>

      </Tabs>
    </section>
  );
}
