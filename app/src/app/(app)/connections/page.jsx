"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { Trans, useLingui } from "@lingui/react/macro";
import { plural } from "@lingui/core/macro";
import { BASE } from "../../../lib/api";
import { getAdsLoginCustomerId, setAdsLoginCustomerId } from "../../../lib/adsCredentials";
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
import {
  CONNECTOR_TOKEN_KEYS,
  consumeConnectorReturn,
  exchangeConnectorCode,
  markConnectorConnected,
} from "../../../lib/connectorAuth";
import { trackEvent, AnalyticsEvent } from "../../../lib/analytics";
import { getActiveProject } from "../../../lib/projects";

/** Storage key back to the connector it belongs to. */
function connectorTypeForStorageKey(storageKey) {
  const hit = Object.entries(CONNECTOR_TOKEN_KEYS).find(([, key]) => key === storageKey);
  return hit ? hit[0] : "";
}
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
  const { t } = useLingui();
  const router = useRouter();
  const [ga4Connected, setGa4Connected] = useState(false);
  const [gscConnected, setGscConnected] = useState(false);
  const [gtmConnected, setGtmConnected] = useState(false);
  const [gadsOauthConnected, setGadsOauthConnected] = useState(false);
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
  // carry both fields (refresh token + MCC).
  async function syncGadsToServer() {
    if (!hasAuthToken()) return;
    const refreshToken = sessionStorage.getItem("gads_refresh_token") || "";
    if (!refreshToken) return;
    const loginCustomerId = getAdsLoginCustomerId() || "";
    try {
      await saveServerConnector({
        connector_type: "google_ads",
        credentials: {
          refresh_token: refreshToken,
          login_customer_id: loginCustomerId,
        },
        granted_scopes: grantedScopesFor("google_ads"),
      });
      await refreshServerRows();
    } catch (err) {
      reportSyncFailure(err);
    }
  }

  // Saving the token to the account is what makes a connection outlive this
  // tab; swallowing its failure is how one silently becomes session-only —
  // the card goes green off the sessionStorage write, no row is ever stored,
  // and every later open reports "Not connected" with nothing to explain it.
  function reportSyncFailure(err) {
    // A 401 is not "you are offline" and telling someone to retry is useless:
    // the token is well-formed and correctly signed, it just names a user this
    // backend's database has never seen — a session left over from a different
    // environment. Only signing in again fixes it.
    if (err?.status === 401) {
      // Keep the backend's own words. "Token expired" and "User not found" are
      // different faults with different causes — one is age, the other is a
      // session pointing at a database that has never seen this account — and
      // collapsing them into one friendly sentence throws away the only thing
      // that tells you which you are looking at.
      //
      // Name the backend too. Which server answered is the other half of the
      // diagnosis and the half nobody can see: the desktop shell and a browser
      // on the same origin call different backends, so "rejected" without a
      // destination is unactionable — and reproducing it took three rounds of
      // asking which one the reporter had been using.
      const backend = BASE || t`the API`;
      setConnectError(
        t`Connected to Google, but your Duct session was rejected by ${backend}, so the connection could not be saved to your account. Sign out and sign in again, then reconnect.` +
          (err?.message ? ` (${err.message})` : ""),
      );
      return;
    }
    setConnectError(
      t`Signed in with Google, but saving the connection to your account failed, so it will only last this browser session. Try Reconnect once you're back online.` +
        " " +
        (err?.message || ""),
    );
  }

  /** Scopes stashed alongside the token by whichever leg delivered it. */
  function grantedScopesFor(connectorType) {
    const key = CONNECTOR_TOKEN_KEYS[connectorType];
    if (!key) return "";
    try {
      return sessionStorage.getItem(`${key}_scopes`) || "";
    } catch {
      return "";
    }
  }

  async function syncTokenToServer(connectorType, refreshToken) {
    if (!hasAuthToken() || !refreshToken) return;
    try {
      await saveServerConnector({
        connector_type: connectorType,
        credentials: { refresh_token: refreshToken },
        granted_scopes: grantedScopesFor(connectorType),
      });
      await refreshServerRows();
    } catch (err) {
      reportSyncFailure(err);
    }
  }

  // One connector's OAuth arriving from the desktop shell. The browser flow
  // hands the token over in the URL fragment; the desktop one cannot — a
  // refresh token must never ride in a deep link — so the shell brings back a
  // single-use code and the token is fetched here instead. Everything after
  // that is the fragment path's destination, one round trip later.
  async function adoptConnectorToken(connectorType, refreshToken, grantedScopes = "") {
    const storageKey = CONNECTOR_TOKEN_KEYS[connectorType];
    if (!storageKey || !refreshToken) {
      setConnectError(t`That connection came back incomplete — please try again.`);
      return;
    }
    sessionStorage.setItem(storageKey, refreshToken);
    if (grantedScopes) sessionStorage.setItem(`${storageKey}_scopes`, grantedScopes);
    // A signed-out connection never reaches the server, so nothing else would
    // tell the sidebar badge its count changed.
    notifyConnectorsChanged();
    // Activation. Deliberately here and not inside notifyConnectorsChanged(),
    // which the four signOut* handlers also call — that would count a
    // disconnect as an activation. A partial scope grant still counts: the
    // tool is connected, which is the thing being measured.
    trackEvent(AnalyticsEvent.ConnectorConnected, { provider: connectorType });
    if (connectorType === "google_ads") setGadsOauthConnected(true);
    if (connectorType === "ga4") setGa4Connected(true);
    if (connectorType === "gsc") setGscConnected(true);
    if (connectorType === "gtm") setGtmConnected(true);
    if (!hasAuthToken()) return;
    if (connectorType === "google_ads") await syncGadsToServer();
    else await syncTokenToServer(connectorType, refreshToken);
  }

  // A connect that started from a conversation ends back in it. Only after
  // the server row is written: the agent answers "connected" by re-reading
  // the database, not by trusting the browser, so returning a beat early
  // would have it report the source as still missing.
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
      // One grant per callback — the fragment carries exactly one connector's
      // result, so a single key serves whichever token arrived with it.
      const grantedScopes = decodeURIComponent(params.get("granted_scopes") || "");
      for (const [fragmentKey, storageKey] of fragmentKeys) {
        const token = params.get(fragmentKey);
        if (token) {
          const decoded = decodeURIComponent(token);
          sessionStorage.setItem(storageKey, decoded);
          if (grantedScopes) sessionStorage.setItem(`${storageKey}_scopes`, grantedScopes);
          notifyConnectorsChanged();
          trackEvent(AnalyticsEvent.ConnectorConnected, {
            provider: connectorTypeForStorageKey(storageKey),
          });
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

    const authed = hasAuthToken();
    setSignedIn(authed);
    const synced = [];
    if (authed) {
      refreshServerRows();
      // Persist newly-arrived OAuth tokens server-side (encrypted) so agent
      // executions and scheduled pulls can run without this browser tab.
      if (arrived.gads_refresh_token) synced.push(syncGadsToServer());
      if (arrived.ga4_refresh_token) synced.push(syncTokenToServer("ga4", arrived.ga4_refresh_token));
      if (arrived.gsc_refresh_token) synced.push(syncTokenToServer("gsc", arrived.gsc_refresh_token));
      if (arrived.gtm_refresh_token) synced.push(syncTokenToServer("gtm", arrived.gtm_refresh_token));
    }
    // One grant per callback, so the first arrival names the connector.
    const arrivedKey = Object.keys(arrived)[0];
    if (arrivedKey) returnToRequester(connectorTypeForStorageKey(arrivedKey), Promise.all(synced));

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
        .then(({ connector_type, refresh_token, granted_scopes }) => {
          const type = connector_type || connectorParam;
          // adoptConnectorToken awaits the server sync, so the return waits too.
          return returnToRequester(type, adoptConnectorToken(type, refresh_token, granted_scopes || ""));
        })
        .catch(() =>
          setConnectError(
            t`That connection didn't finish — the link expires after a minute. Please try again.`,
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

  async function saveGadsManagerAccount(event) {
    event.preventDefault();
    const mcc = mccInput.replace(/-/g, "").trim();
    setAdsLoginCustomerId(mcc);
    setMccInput(mcc);
    await syncGadsToServer();
  }

  async function signOutGads() {
    sessionStorage.removeItem("gads_refresh_token");
    sessionStorage.removeItem("gads_customer_id");
    notifyConnectorsChanged();
    setAdsLoginCustomerId("");
    setGadsOauthConnected(false);
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

  // "Connected" has to survive closing the tab, and sessionStorage does not:
  // it is per-tab and dies with it. A card reading only the session key reports
  // "Not connected" on every fresh open of a connector that IS connected, while
  // the project's data-source inventory — which reads the stored rows — says the
  // opposite about the same connector. The stored row is the durable half of the
  // answer; the session key still counts on its own, because a signed-out
  // connect never reaches the server at all. The manual cards below have always
  // worked this way (`serverRowList.length > 0`); these four were the exception.
  const gadsAuthorized = gadsOauthConnected || !!serverRows.google_ads;
  const ga4Authorized = ga4Connected || !!serverRows.ga4;
  const gscAuthorized = gscConnected || !!serverRows.gsc;
  const gtmAuthorized = gtmConnected || !!serverRows.gtm;

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
          <p className="app-subtle" style={{ marginTop: 0, marginBottom: 18, maxWidth: 720 }}>
            <Trans>
              Connect an account once — it&rsquo;s saved for your whole account. Open a card
              to set it up and to pick which of your accounts{" "}
              <strong className="font-medium text-foreground">{projectName}</strong>{" "}
              reads from.
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
              authorizeUrl={`${BASE}/auth/connectors/google_ads/oauth/authorize`}
              onDisconnect={signOutGads}
              signedIn={signedIn}
              syncedToAccount={!!serverRows.google_ads}
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
                    onChange={(e) => setMccInput(e.target.value)}
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
              authorizeUrl={`${BASE}/auth/connectors/gsc/oauth/authorize`}
              onDisconnect={signOutGsc}
              signedIn={signedIn}
              syncedToAccount={!!serverRows.gsc}
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
              authorizeUrl={`${BASE}/auth/connectors/ga4/oauth/authorize`}
              onDisconnect={signOutGa4}
              signedIn={signedIn}
              syncedToAccount={!!serverRows.ga4}
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
              authorizeUrl={`${BASE}/auth/connectors/gtm/oauth/authorize`}
              onDisconnect={signOutGtm}
              signedIn={signedIn}
              syncedToAccount={!!serverRows.gtm}
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

            <ConnectorTile
              logo={LOGOS.hubspot}
              title="HubSpot"
              description={t`CRM lifecycle stages, pipeline and closed revenue.`}
              tone="off"
              status={t`Coming soon`}
              disabled
            />
          </div>
        </TabsContent>

      </Tabs>
    </section>
  );
}
