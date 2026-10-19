"use client";

// The Connections page's "MCP servers" section: other apps' tools, connected
// over MCP, for Duct's agent to use (issue #345).
//
// Today only the insights chat reaches these servers (agents/core/mcp_tools.py),
// so the copy says that and no more. Four parts:
//
// - the servers already connected, as rows — the one place a server added by
//   address is managed, and where a lapsed sign-in shows before a run finds it;
// - a tile per preset plus one for any server by address, each opening the
//   connect dialog, so the grid reads like the connector grid above it;
// - the two facts someone deciding whether to connect deserves: what asks
//   before it runs, and whose servers a shared project reads through;
// - the sign-in's return, which lands on this page and is claimed here.
//
// Everything it fetches goes through `api`, so `/preview` can render every
// state with a stub and no backend.

import { useCallback, useEffect, useState } from "react";
import { ExternalLink, Plus, ShieldCheck, Users } from "lucide-react";
import { msg, plural } from "@lingui/core/macro";
import { Trans, useLingui } from "@lingui/react/macro";
import { Button } from "@/components/ui/button";
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
import { STORAGE_NONE, rowStorage } from "@/lib/credentialStorage";
import { isLocalBackendActive } from "@/lib/localBackend";
import { serverHost } from "@/lib/mcpServers";
import ConnectorTile from "./ConnectorTile";
import EntityAvatar from "./EntityAvatar";
import McpConnectDialog from "./McpConnectDialog";
import McpServerRow from "./McpServerRow";

/** The public page that walks through each preset and the by-address path. */
export const MCP_GUIDE_URL = "https://getduct.ai/mcp";

// `client` on the connect: the sign-in comes home through the desktop relay.
const DESKTOP_CLIENT = "desktop";
// The analytics `provider` for a server added by its address.
const CUSTOM_PROVIDER = "custom";

/** What each preset is for, in the reader's language. The backend holds facts
 *  only (presets.py); an id with no line here falls back to its host. */
const PRESET_COPY = {
  openseo: msg`Keyword volume, difficulty and backlinks for the topics you ask about.`,
  notion: msg`Read and write pages in your Notion workspace.`,
  linear: msg`Look up issues and projects, or file a new issue.`,
  posthog: msg`Events, funnels and insights from your product analytics.`,
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

export default function McpServers({ signedIn, api = MCP_API }) {
  const { t, i18n } = useLingui();
  const { confirm, dialog: confirmDialog } = useConfirm();
  const [presets, setPresets] = useState([]);
  const [servers, setServers] = useState([]);
  // null until the first answer, so the grid draws its shape rather than an
  // empty section that fills in a beat later.
  const [loaded, setLoaded] = useState(false);
  const [loadError, setLoadError] = useState("");
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [busyId, setBusyId] = useState("");
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
      setError(i18n._(RETURN_ERRORS[reason] || RETURN_ERRORS[McpReturnError.EXCHANGE]));
      return;
    }
    if (!code) return;
    if (!hasAuthToken()) {
      setError(t`Sign in to finish connecting that MCP server.`);
      return;
    }
    api
      .claim(code)
      .then(async (server) => {
        track(server);
        const name = server?.name || serverHost(server?.url) || "";
        setNotice(t`${name} is connected. The insights chat can use its tools now.`);
        await refresh().catch(() => {});
      })
      .catch(() => setError(t`That connection expired or was started from another account. Connect again.`));
    // Once, on arrival.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function openDialog(next) {
    setNotice("");
    setError("");
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
      setNotice(t`${name} is connected. The insights chat can use its tools now.`);
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
    setBusyId(server.id);
    setNotice("");
    setError("");
    try {
      await api.remove(server.id);
      setDialogOpen(false);
      await refresh();
    } catch (err) {
      const why = err?.message || "";
      setError(t`Couldn't disconnect ${name}. ${why}`.trim());
    } finally {
      setBusyId("");
    }
  }

  const presetById = Object.fromEntries(presets.map((p) => [p.id, p]));
  const serverFor = (preset) => servers.find((s) => s.preset === preset.id) || null;
  const customCount = servers.filter((s) => !presetById[s.preset]).length;
  const localSidecar = isLocalBackendActive();

  function presetDescription(preset) {
    return PRESET_COPY[preset.id] ? i18n._(PRESET_COPY[preset.id]) : serverHost(preset.url);
  }

  function presetLogo(preset) {
    return <EntityAvatar url={preset.home} name={preset.label} className="conn-favicon" />;
  }

  const customLogo = <Plus className="mcp-add-icon" aria-hidden="true" />;
  const customDescription = t`Paste the address of any remote MCP server.`;

  // A row's Reconnect runs the connect at once: the person already said what
  // they want. Except for a key, which nobody can paste for them — that opens
  // with the field showing instead.
  function reconnect(server) {
    const preset = presetById[server.preset];
    const how = server.auth === McpAuth.KEY ? { keyOpen: true } : { autoStart: true };
    openDialog(preset ? { preset, ...how } : { url: server.url, name: server.name, server, ...how });
  }

  // The dialog's props for whatever is open.
  const dialogPreset = target?.preset || null;
  const dialogServer = dialogPreset ? serverFor(dialogPreset) : target?.server || null;

  return (
    <section className="mcp-section" aria-labelledby="mcp-heading">
      <div className="mcp-head">
        <div className="mcp-head-text">
          <h2 id="mcp-heading" className="mcp-title">
            <Trans>MCP servers</Trans>
          </h2>
          <p className="app-subtle mcp-lede">
            <Trans>
              Give Duct&rsquo;s agent tools from the other apps you use. Connect a server over MCP and the
              insights chat can use it mid-answer: keyword volumes from OpenSEO, a page from Notion, an
              issue in Linear.
            </Trans>
          </p>
        </div>
        <a className="app-link mcp-guide" href={MCP_GUIDE_URL} target="_blank" rel="noreferrer">
          <Trans>Setup guide</Trans>
          <ExternalLink className="size-3.5" aria-hidden="true" />
        </a>
      </div>

      {error && (
        <p role="alert" className="mcp-message text-sm text-destructive">
          {error}
        </p>
      )}
      {notice && !error && (
        <p role="status" className="mcp-message text-sm text-muted-foreground">
          {notice}
        </p>
      )}

      {!signedIn ? (
        <p className="conn-hint">
          <Trans>Sign in to connect an MCP server. It&rsquo;s saved to your account, like your other connections.</Trans>
        </p>
      ) : !loaded ? (
        <div className="conn-grid" role="status" aria-label={t`Loading MCP servers`}>
          {[0, 1, 2, 3, 4].map((i) => (
            <Skeleton key={i} className="h-28 rounded-2xl" />
          ))}
        </div>
      ) : loadError && !presets.length ? (
        <div className="mcp-load-error">
          <p role="alert" className="text-sm text-destructive">
            <Trans>Couldn&rsquo;t load your MCP servers.</Trans> {loadError}
          </p>
          <Button type="button" size="sm" variant="secondary" onClick={load}>
            <Trans>Retry</Trans>
          </Button>
        </div>
      ) : (
        <>
          {servers.length > 0 && (
            <div className="mcp-block">
              <h3 className="conn-dialog-heading">
                <Trans>Connected</Trans>
              </h3>
              <ul className="mcp-server-list">
                {servers.map((server) => (
                  <McpServerRow
                    key={server.id}
                    server={server}
                    preset={presetById[server.preset] || null}
                    busy={busyId === server.id}
                    onReconnect={reconnect}
                    onDisconnect={disconnect}
                  />
                ))}
              </ul>
            </div>
          )}

          <div className="mcp-block">
            {servers.length > 0 && (
              <h3 className="conn-dialog-heading">
                <Trans>Add a server</Trans>
              </h3>
            )}
            <div className="conn-grid">
              {presets.map((preset) => {
                const server = serverFor(preset);
                const needsReauth = server?.status === McpServerStatus.NEEDS_REAUTH;
                return (
                  <ConnectorTile
                    key={preset.id}
                    logo={presetLogo(preset)}
                    title={preset.label}
                    description={presetDescription(preset)}
                    tone={!server ? "off" : needsReauth ? "partial" : "on"}
                    status={!server ? t`Not connected` : needsReauth ? t`Needs reconnecting` : t`Connected`}
                    storage={server ? rowStorage(server, { localSidecar }) : STORAGE_NONE}
                    onClick={() => openDialog({ preset })}
                  />
                );
              })}
              <ConnectorTile
                logo={customLogo}
                title={t`Any MCP server`}
                description={customDescription}
                tone={customCount ? "on" : "off"}
                status={customCount ? plural(customCount, { one: "# connected", other: "# connected" }) : t`Add by address`}
                onClick={() => openDialog({})}
              />
            </div>
          </div>

          <ul className="mcp-notes">
            <li>
              <ShieldCheck className="mcp-note-icon" aria-hidden="true" />
              <span>
                <Trans>
                  Duct asks before it runs a tool its server doesn&rsquo;t mark as read-only, and before every call
                  to a server you added by address.
                </Trans>
              </span>
            </li>
            <li>
              <Users className="mcp-note-icon" aria-hidden="true" />
              <span>
                <Trans>
                  Only your own chats use your servers, in any project. People you share a project with connect
                  their own.
                </Trans>
              </span>
            </li>
          </ul>
        </>
      )}

      {target && (
        <McpConnectDialog
          key={openCount}
          open={dialogOpen}
          onOpenChange={setDialogOpen}
          preset={dialogPreset}
          server={dialogServer}
          logo={dialogPreset ? presetLogo(dialogPreset) : customLogo}
          description={dialogPreset ? presetDescription(dialogPreset) : customDescription}
          initialUrl={target.url || ""}
          initialName={target.name || ""}
          initialNeedsKey={Boolean(target.needsKey)}
          initialKeyOpen={Boolean(target.keyOpen)}
          autoStart={Boolean(target.autoStart)}
          onConnect={connect}
          onDisconnect={disconnect}
        />
      )}
      {confirmDialog}
    </section>
  );
}
