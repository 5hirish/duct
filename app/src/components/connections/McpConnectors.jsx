"use client";

// The MCP connectors on the Connections page: other companies' own servers,
// connected so Duct's agent can use their tools (issue #345).
//
// They sit in the same grid as the native connectors, each tile saying which
// kind it is and who publishes it (`lib/connectorSource.js`), because to the
// person setting Duct up both are "the tools Duct can reach" and one place is
// where they look. So this renders tiles, not a section: the caller puts it
// inside its `.conn-grid`. Three kinds of tile:
//
// - one per preset (OpenSEO, PostHog, Railway…), published by its vendor;
// - one per server added by address, so it is managed like any other card;
// - one to add a server by address.
//
// It also claims the sign-in's return, which lands on this page. What it has
// to say about that (connected, expired, declined) goes to `onMessage`, so
// the page shows it where its own connector messages go.
//
// Everything it fetches goes through `api`, so `/preview` can render every
// state with a stub and no backend.

import { useCallback, useEffect, useState } from "react";
import { Plus } from "lucide-react";
import { msg } from "@lingui/core/macro";
import { useLingui } from "@lingui/react/macro";
import { Skeleton } from "@/components/ui/skeleton";
import { useConfirm } from "@/components/ui/confirm-dialog";
import { AnalyticsEvent, AnalyticsParam, trackEvent } from "@/lib/analytics";
import {
  MCP_CONNECTOR,
  McpAuth,
  McpConnect,
  McpReturnError,
  McpServerStatus,
  claimMcpServer,
  connectMcpServer,
  deleteMcpServer,
  hasAuthToken,
  listMcpPresets,
  listMcpServers,
} from "@/lib/connectorsApi";
import { openVendorSignIn, usesSystemBrowser } from "@/lib/connectorAuth";
import { mcpSource } from "@/lib/connectorSource";
import { STORAGE_NONE, rowStorage } from "@/lib/credentialStorage";
import { isLocalBackendActive } from "@/lib/localBackend";
import { serverHost, serverSite } from "@/lib/mcpServers";
import ConnectorTile from "./ConnectorTile";
import EntityAvatar from "./EntityAvatar";
import McpConnectDialog from "./McpConnectDialog";

// `client` on the connect: the sign-in comes home through the desktop relay.
const DESKTOP_CLIENT = "desktop";
// The analytics `provider` for a server added by its address.
const CUSTOM_PROVIDER = "custom";
// Tiles the grid holds while the list loads: about one row of presets.
const LOADING_TILES = 3;
// "MCP" with no publisher: the add tile, and a server added by address, whose
// publisher is not Duct's to guess (its tile shows the host instead).
const MCP_ONLY = mcpSource("");

/** What each preset is for, in the reader's language. The backend holds facts
 *  only (presets.py); an id with no line here falls back to its host. */
const PRESET_COPY = {
  openseo: msg`Keyword volume, difficulty and backlinks for the topics you ask about.`,
  posthog: msg`Events, funnels and insights from your product analytics.`,
  notion: msg`Read and write pages in your Notion workspace.`,
  linear: msg`Look up issues and projects, or file a new issue.`,
  railway: msg`Your Railway projects: services, deployments, logs and variables.`,
  cloudflare: msg`Your Cloudflare account through its API: Workers, DNS, zones and analytics.`,
};

const RETURN_ERRORS = {
  [McpReturnError.EXPIRED]: msg`That sign-in expired before it came back. Connect the server again.`,
  [McpReturnError.CONSENT]: msg`The sign-in was cancelled or declined, so nothing was connected.`,
  [McpReturnError.EXCHANGE]: msg`The server's sign-in finished but it wouldn't hand over access. Try connecting again.`,
};

/** The real calls. Module level, so a caller's effects see one stable object. */
export const MCP_API = {
  listPresets: listMcpPresets,
  listServers: listMcpServers,
  connect: connectMcpServer,
  claim: claimMcpServer,
  remove: deleteMcpServer,
  systemBrowser: usesSystemBrowser,
  openSignIn: openVendorSignIn,
};

function track(server) {
  trackEvent(AnalyticsEvent.McpServerConnected, {
    [AnalyticsParam.Provider]: server?.preset || CUSTOM_PROVIDER,
    [AnalyticsParam.Method]: server?.auth || "",
  });
}

function noop() {}

/**
 * @param onMessage  `({ notice } | { error })` — what a connect, a disconnect
 *   or the sign-in's return has to tell the person, for the page to show.
 */
export default function McpConnectors({ signedIn, api = MCP_API, onMessage = noop }) {
  const { t, i18n } = useLingui();
  const { confirm, dialog: confirmDialog } = useConfirm();
  const [presets, setPresets] = useState([]);
  const [servers, setServers] = useState([]);
  // False until the first answer, so the grid holds tile shapes rather than
  // closing up and reopening a beat later.
  const [loaded, setLoaded] = useState(false);
  const [loadError, setLoadError] = useState("");
  // Which dialog is open, and a count so each opening starts fresh.
  const [target, setTarget] = useState(null);
  const [openCount, setOpenCount] = useState(0);
  const [dialogOpen, setDialogOpen] = useState(false);

  const refresh = useCallback(async () => {
    const [nextPresets, nextServers] = await Promise.all([api.listPresets(), api.listServers()]);
    setPresets(nextPresets || []);
    setServers(nextServers || []);
  }, [api]);

  const load = useCallback(async () => {
    setLoadError("");
    try {
      await refresh();
    } catch (err) {
      setLoadError(err?.message || "");
    } finally {
      setLoaded(true);
    }
  }, [refresh]);

  useEffect(() => {
    if (signedIn) load();
  }, [signedIn, load]);

  // The vendor sign-in comes home to /connections?connector=mcp, with either a
  // grant to claim or the kind of failure. Read once, scrubbed at once: the
  // code is single-use and two minutes long, and has no business in history.
  // Signed in is read from storage, not the prop: the page sets that prop in
  // an effect of its own, which runs after this one.
  useEffect(() => {
    const query = new URLSearchParams(window.location.search);
    if (query.get("connector") !== MCP_CONNECTOR) return;
    window.history.replaceState(null, "", window.location.pathname);
    const reason = query.get("error") || "";
    const code = query.get("auth_code") || "";
    if (reason) {
      onMessage({ error: i18n._(RETURN_ERRORS[reason] || RETURN_ERRORS[McpReturnError.EXCHANGE]) });
      return;
    }
    if (!code) return;
    if (!hasAuthToken()) {
      onMessage({ error: t`Sign in to finish connecting that MCP server.` });
      return;
    }
    api
      .claim(code)
      .then(async (server) => {
        track(server);
        const name = server?.name || serverHost(server?.url) || "";
        onMessage({ notice: t`${name} is connected. The insights chat can use its tools now.` });
        await refresh().catch(() => {});
      })
      .catch(() => onMessage({ error: t`That connection expired or was started from another account. Connect again.` }));
    // Once, on arrival.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function openDialog(next) {
    onMessage({});
    setTarget(next);
    setOpenCount((n) => n + 1);
    setDialogOpen(true);
  }

  async function connect(request) {
    const systemBrowser = await api.systemBrowser();
    const res = await api.connect({ ...request, client: systemBrowser ? DESKTOP_CLIENT : "" });
    if (res?.status === McpConnect.NEEDS_KEY) return { needsKey: true };
    if (res?.status === McpConnect.AUTHORIZE && res.authorize_url) {
      const mode = await api.openSignIn(res.authorize_url, { systemBrowser });
      return { waiting: mode === "browser" };
    }
    if (res?.status === McpConnect.CONNECTED) {
      track(res.server);
      const name = res.server?.name || "";
      onMessage({ notice: t`${name} is connected. The insights chat can use its tools now.` });
      await refresh().catch(() => {});
      return { done: true };
    }
    throw new Error(t`The server answered in a way Duct didn't expect. Try again.`);
  }

  async function disconnect(server) {
    const name = server.name || serverHost(server.url);
    const ok = await confirm({
      title: t`Disconnect “${name}”?`,
      description: t`Duct's agent stops using its tools straight away, in every project. Connecting it again means signing in again.`,
      action: t`Disconnect`,
      destructive: true,
    });
    if (!ok) return;
    onMessage({});
    try {
      await api.remove(server.id);
      setDialogOpen(false);
      await refresh();
    } catch (err) {
      const why = err?.message || "";
      onMessage({ error: t`Couldn't disconnect ${name}. ${why}`.trim() });
    }
  }

  const presetById = Object.fromEntries(presets.map((p) => [p.id, p]));
  const serverFor = (preset) => servers.find((s) => s.preset === preset.id) || null;
  const byAddress = servers.filter((s) => !presetById[s.preset]);
  const localSidecar = isLocalBackendActive();

  function presetDescription(preset) {
    return PRESET_COPY[preset.id] ? i18n._(PRESET_COPY[preset.id]) : serverHost(preset.url);
  }

  function presetLogo(preset) {
    return <EntityAvatar url={preset.home} name={preset.label} className="conn-favicon" />;
  }

  function serverLogo(server) {
    return <EntityAvatar url={serverSite(server.url)} name={server.name || serverHost(server.url)} className="conn-favicon" />;
  }

  const addLogo = <Plus className="mcp-add-icon" aria-hidden="true" />;
  const addDescription = t`Paste the address of any remote MCP server.`;

  function stateOf(server) {
    const needsReauth = server?.status === McpServerStatus.NEEDS_REAUTH;
    return {
      tone: !server ? "off" : needsReauth ? "partial" : "on",
      status: !server ? t`Not connected` : needsReauth ? t`Needs reconnecting` : t`Connected`,
      storage: server ? rowStorage(server, { localSidecar }) : STORAGE_NONE,
    };
  }

  // The dialog's props for whatever is open.
  const dialogPreset = target?.preset || null;
  const dialogServer = dialogPreset ? serverFor(dialogPreset) : target?.server || null;
  // A key-signed server reconnects with the field showing: nobody else can
  // paste it, so the dialog opens where the person has to act.
  const keyOpen = dialogServer?.auth === McpAuth.KEY && dialogServer?.status === McpServerStatus.NEEDS_REAUTH;
  const dialogSource = dialogPreset
    ? mcpSource(dialogPreset.publisher)
    : MCP_ONLY;

  if (!signedIn) {
    return (
      <ConnectorTile
        logo={addLogo}
        title={t`MCP connectors`}
        source={MCP_ONLY}
        description={t`Tools from OpenSEO, PostHog and other apps, for the insights chat. Saved to your account.`}
        status={t`Sign in to connect`}
        disabled
      />
    );
  }

  if (!loaded) {
    // One live region for the wait, not one per placeholder.
    const loading = { role: "status", "aria-label": t`Loading MCP connectors` };
    return Array.from({ length: LOADING_TILES }, (_, i) => (
      <Skeleton key={i} className="h-36 rounded-2xl" {...(i === 0 ? loading : {})} />
    ));
  }

  if (loadError && !presets.length) {
    return (
      <ConnectorTile
        logo={addLogo}
        title={t`MCP connectors`}
        source={MCP_ONLY}
        description={t`Couldn't load them. ${loadError}`.trim()}
        tone="partial"
        status={t`Open to try again`}
        onClick={load}
      />
    );
  }

  return (
    <>
      {presets.map((preset) => (
        <ConnectorTile
          key={preset.id}
          logo={presetLogo(preset)}
          title={preset.label}
          source={mcpSource(preset.publisher)}
          description={presetDescription(preset)}
          {...stateOf(serverFor(preset))}
          onClick={() => openDialog({ preset })}
        />
      ))}
      {byAddress.map((server) => (
        <ConnectorTile
          key={server.id}
          logo={serverLogo(server)}
          title={server.name || serverHost(server.url)}
          source={MCP_ONLY}
          description={serverHost(server.url)}
          {...stateOf(server)}
          onClick={() => openDialog({ url: server.url, name: server.name, server })}
        />
      ))}
      <ConnectorTile
        logo={addLogo}
        title={t`Any MCP server`}
        source={MCP_ONLY}
        description={addDescription}
        status={t`Add by address`}
        onClick={() => openDialog({})}
      />

      {target && (
        <McpConnectDialog
          key={openCount}
          open={dialogOpen}
          onOpenChange={setDialogOpen}
          preset={dialogPreset}
          server={dialogServer}
          source={dialogSource}
          logo={dialogPreset ? presetLogo(dialogPreset) : dialogServer ? serverLogo(dialogServer) : addLogo}
          description={
            dialogPreset ? presetDescription(dialogPreset) : dialogServer ? serverHost(dialogServer.url) : addDescription
          }
          initialUrl={target.url || ""}
          initialName={target.name || ""}
          initialKeyOpen={keyOpen}
          onConnect={connect}
          onDisconnect={disconnect}
        />
      )}
      {confirmDialog}
    </>
  );
}
