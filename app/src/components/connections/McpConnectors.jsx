"use client";

// The MCP connectors on the Connections page: other companies' own servers,
// connected so Duct's agent can use their tools (issue #345).
//
// They sit in the same catalogue as the native connectors, each tile saying
// which kind it is and who publishes it (`lib/connectorSource.js`), because
// to the person setting Duct up both are "the tools Duct can reach" and one
// place is where they look. `useMcpConnectors` is that for the Connections
// page: one catalogue entry per tile (lib/connectorCatalog.js), so a search
// or a filter there treats a server like any other source. The default
// export draws the same tiles into a grid, for `/preview`. Three kinds:
//
// - one per preset (OpenSEO, PostHog, Railway…), published by its vendor;
// - one per server added by address, so it is managed like any other card;
// - one to add a server by address.
//
// A search also asks the MCP Registry (issue #496), and what it finds comes
// back as `registry`: its own section under the catalogue's results, because
// those servers are not Duct's to file or vouch for. Each says where it runs;
// what its publisher runs is shown, the rest wait behind a button
// (`arrangeRegistry`). Connecting one is connecting by address, filled in.
//
// It also claims the sign-in's return, which lands on this page. What it has
// to say about that (connected, expired, declined) goes to `onMessage`, so
// the page shows it where its own connector messages go.
//
// Everything it fetches goes through `api`, so `/preview` can render every
// state with a stub and no backend.

import { useCallback, useEffect, useRef, useState } from "react";
import { Plus } from "lucide-react";
import { msg, plural } from "@lingui/core/macro";
import { Trans, useLingui } from "@lingui/react/macro";
import { Button } from "@/components/ui/button";
import { Section, TileGrid } from "@/components/ui/page";
import { Skeleton } from "@/components/ui/skeleton";
import { useConfirm } from "@/components/ui/confirm-dialog";
import { AnalyticsEvent, AnalyticsParam, trackEvent } from "@/lib/analytics";
import {
  MCP_CONNECTOR,
  McpAuth,
  McpConnect,
  McpReturnError,
  McpServerStatus,
  checkMcpServer,
  claimMcpServer,
  connectMcpServer,
  deleteMcpServer,
  hasAuthToken,
  listMcpPresets,
  listMcpServers,
  searchMcpRegistry,
} from "@/lib/connectorsApi";
import { openVendorSignIn, usesSystemBrowser } from "@/lib/connectorAuth";
import { mcpSource } from "@/lib/connectorSource";
import { STORAGE_NONE, rowStorage } from "@/lib/credentialStorage";
import { isLocalBackendActive } from "@/lib/localBackend";
import {
  PROBLEM_SHORT,
  arrangeRegistry,
  listingPublisher,
  serverHost,
  serverProblem,
  serverSite,
} from "@/lib/mcpServers";
import { Category, ConnectionStatus, MCP_CATEGORY, Origin } from "@/lib/connectorCatalog";
import ConnectorTile from "./ConnectorTile";
import EntityAvatar from "./EntityAvatar";
import McpConnectDialog from "./McpConnectDialog";

// `client` on the connect: the sign-in comes home through the desktop relay.
const DESKTOP_CLIENT = "desktop";
// The analytics `provider` for a server added by its address, and for one
// found in the MCP Registry: the split says whether search, not just the
// paste box, is what gets people connected.
const CUSTOM_PROVIDER = "custom";
const REGISTRY_PROVIDER = "registry";
// A registry connect that left for the vendor's sign-in, so the return can
// still be counted as one. The address only; nothing secret.
const REGISTRY_PENDING_KEY = "duct_mcp_registry_pending";
// A search is a name, so one letter finds nothing worth a request; the wait
// lets a word finish before the registry is asked.
const REGISTRY_MIN_CHARS = 2;
const REGISTRY_DEBOUNCE_MS = 300;
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
  check: checkMcpServer,
  searchRegistry: searchMcpRegistry,
  systemBrowser: usesSystemBrowser,
  openSignIn: openVendorSignIn,
};

function track(server, via = "") {
  trackEvent(AnalyticsEvent.McpServerConnected, {
    [AnalyticsParam.Provider]: server?.preset || via || CUSTOM_PROVIDER,
    [AnalyticsParam.Method]: server?.auth || "",
  });
}

function rememberRegistryConnect(url) {
  try {
    window.sessionStorage.setItem(REGISTRY_PENDING_KEY, url);
  } catch {
    // Storage off: the connect still works, it is only counted as custom.
  }
}

/** REGISTRY_PROVIDER when the server that just came back was a registry
 *  connect that left for its sign-in, and the mark is spent either way. */
function registryReturn(server) {
  try {
    const pending = window.sessionStorage.getItem(REGISTRY_PENDING_KEY);
    window.sessionStorage.removeItem(REGISTRY_PENDING_KEY);
    return pending && pending === server?.url ? REGISTRY_PROVIDER : "";
  } catch {
    return "";
  }
}

function noop() {}

/** The tile's status, as the catalogue files it. */
const CATALOG_STATUS = {
  on: ConnectionStatus.CONNECTED,
  partial: ConnectionStatus.ATTENTION,
  off: ConnectionStatus.AVAILABLE,
};

/** Where a registry search is. OFF: this Duct turned the search off. */
const RegistryPhase = Object.freeze({
  IDLE: "idle",
  LOADING: "loading",
  READY: "ready",
  FAILED: "failed",
  OFF: "off",
});
const REGISTRY_IDLE = Object.freeze({ query: "", phase: RegistryPhase.IDLE, listings: [], error: "" });

/** Where the list is: the catalogue entries exist only once it is `READY`. */
export const McpPhase = Object.freeze({
  SIGNED_OUT: "signed-out",
  LOADING: "loading",
  FAILED: "failed",
  READY: "ready",
});

/**
 * The MCP servers as catalogue entries, plus what to draw while there are
 * none to give.
 *
 * Returns
 *   phase        McpPhase
 *   entries      one per preset and per server added by address, each a
 *                catalogue entry with `render()` for its tile
 *   addTile      `render()` for "Any MCP server", the way in for anything
 *                the catalogue does not list
 *   addServer    opens the same dialog, for a way in drawn elsewhere
 *   registryAvailable  false when a search can't reach the MCP Registry:
 *                signed out, or this Duct turned it off
 *   placeholder  the tiles that stand in until READY: sign in, loading,
 *                couldn't load
 *   overlays     the dialog and the confirm, mounted once by the caller
 *   registry     the "From the MCP Registry" section for `search`, or null
 *
 * @param search  What the catalogue search holds, when the registry should
 *   be asked too; "" leaves it alone.
 * @param onMessage  `({ notice } | { error })` — what a connect, a disconnect
 *   or the sign-in's return has to tell the person, for the page to show.
 */
export function useMcpConnectors({ signedIn, search = "", api = MCP_API, onMessage = noop }) {
  const { t, i18n } = useLingui();
  const { confirm, dialog: confirmDialog } = useConfirm();
  const [presets, setPresets] = useState([]);
  const [servers, setServers] = useState([]);
  // False until the first answer, so the grid holds tile shapes rather than
  // closing up and reopening a beat later.
  const [loaded, setLoaded] = useState(false);
  const [loadError, setLoadError] = useState("");
  // A 404 is a Duct server from before MCP connectors, usually a desktop app
  // not yet updated. Trying again changes nothing, so the tile says what does.
  const [outdated, setOutdated] = useState(false);
  // Which dialog is open, and a count so each opening starts fresh.
  const [target, setTarget] = useState(null);
  const [openCount, setOpenCount] = useState(0);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [registry, setRegistry] = useState(REGISTRY_IDLE);
  const [registryRetry, setRegistryRetry] = useState(0);
  const [showMoreFor, setShowMoreFor] = useState("");
  // Only the newest search may answer: a slow reply to "fig" must not land
  // over the one to "figma".
  const registrySeq = useRef(0);

  const refresh = useCallback(async () => {
    const [nextPresets, nextServers] = await Promise.all([api.listPresets(), api.listServers()]);
    setPresets(nextPresets || []);
    setServers(nextServers || []);
  }, [api]);

  const load = useCallback(async () => {
    setLoadError("");
    setOutdated(false);
    try {
      await refresh();
    } catch (err) {
      setLoadError(err?.message || String(err?.status || "error"));
      setOutdated(err?.status === 404);
    } finally {
      setLoaded(true);
    }
  }, [refresh]);

  useEffect(() => {
    if (signedIn) load();
  }, [signedIn, load]);

  const query = search.trim();
  const registryOff = registry.phase === RegistryPhase.OFF;
  useEffect(() => {
    if (registryOff) return undefined;
    const seq = ++registrySeq.current;
    if (!signedIn || query.length < REGISTRY_MIN_CHARS) {
      setRegistry(REGISTRY_IDLE);
      return undefined;
    }
    setRegistry({ query, phase: RegistryPhase.LOADING, listings: [], error: "" });
    const timer = setTimeout(async () => {
      try {
        const res = await api.searchRegistry(query);
        if (seq !== registrySeq.current) return;
        const phase = res?.available === false ? RegistryPhase.OFF : RegistryPhase.READY;
        setRegistry({ query, phase, listings: res?.servers || [], error: "" });
      } catch (err) {
        if (seq !== registrySeq.current) return;
        // A status means the server said something worth showing. Without one
        // the request never landed, or the server crashed on it and its 500 has
        // no CORS header to be read by. The browser's own words ("Load failed")
        // tell nobody anything; the section has a sentence for that.
        setRegistry({ query, phase: RegistryPhase.FAILED, listings: [], error: err?.status ? err.message : "" });
      }
    }, REGISTRY_DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [query, signedIn, api, registryOff, registryRetry]);

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
        track(server, registryReturn(server));
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

  async function connect(request, via = "") {
    const systemBrowser = await api.systemBrowser();
    const res = await api.connect({ ...request, client: systemBrowser ? DESKTOP_CLIENT : "" });
    if (res?.status === McpConnect.NEEDS_KEY) return { needsKey: true };
    if (res?.status === McpConnect.AUTHORIZE && res.authorize_url) {
      if (via === REGISTRY_PROVIDER) rememberRegistryConnect(request.url);
      const mode = await api.openSignIn(res.authorize_url, { systemBrowser });
      return { waiting: mode === "browser" };
    }
    if (res?.status === McpConnect.CONNECTED) {
      track(res.server, via);
      const name = res.server?.name || "";
      onMessage({ notice: t`${name} is connected. The insights chat can use its tools now.` });
      await refresh().catch(() => {});
      return { done: true };
    }
    throw new Error(t`The server answered in a way Duct didn't expect. Try again.`);
  }

  /** Try a saved server with what is saved. The dialog says the outcome. */
  async function check(server) {
    const res = await api.check(server.id);
    await refresh().catch(() => {});
    return res || {};
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
    const problem = serverProblem(server);
    const reason = problem ? i18n._(PROBLEM_SHORT[problem]) : "";
    return {
      tone: !server ? "off" : problem ? "partial" : "on",
      status: !server ? t`Not connected` : problem ? t`Needs attention · ${reason}` : t`Connected`,
      storage: server ? rowStorage(server, { localSidecar }) : STORAGE_NONE,
    };
  }

  function listingLogo(listing) {
    return <EntityAvatar url={listing.website || serverSite(listing.url)} name={listing.title} className="conn-favicon" />;
  }

  // The dialog's props for whatever is open. A registry listing that has
  // since been connected is that server's dialog, so Disconnect is there.
  const dialogPreset = target?.preset || null;
  const connectedListing = target?.listing ? servers.find((s) => s.url === target.listing.url) || null : null;
  const dialogListing = connectedListing ? null : target?.listing || null;
  const dialogServer = dialogPreset ? serverFor(dialogPreset) : target?.server || connectedListing;
  // A key-signed server reconnects with the field showing: nobody else can
  // paste it, so the dialog opens where the person has to act.
  const keyOpen = dialogServer?.auth === McpAuth.KEY && dialogServer?.status === McpServerStatus.NEEDS_REAUTH;
  const dialogSource = dialogPreset
    ? mcpSource(dialogPreset.publisher)
    : dialogListing
      ? mcpSource(listingPublisher(dialogListing))
      : MCP_ONLY;
  const dialogLogo = dialogPreset
    ? presetLogo(dialogPreset)
    : dialogListing
      ? listingLogo(dialogListing)
      : dialogServer
        ? serverLogo(dialogServer)
        : addLogo;
  const dialogDescription = dialogPreset
    ? presetDescription(dialogPreset)
    : dialogListing
      ? dialogListing.description || dialogListing.host
      : dialogServer
        ? serverHost(dialogServer.url)
        : addDescription;

  const overlays = (
    <>
      {target && (
        <McpConnectDialog
          key={openCount}
          open={dialogOpen}
          onOpenChange={setDialogOpen}
          preset={dialogPreset}
          server={dialogServer}
          listing={dialogListing}
          source={dialogSource}
          logo={dialogLogo}
          description={dialogDescription}
          initialUrl={target.url || ""}
          initialName={target.name || ""}
          initialNeedsKey={dialogListing?.auth === McpAuth.KEY}
          initialKeyOpen={keyOpen}
          onConnect={(request) => connect(request, dialogListing ? REGISTRY_PROVIDER : "")}
          onCheck={check}
          onDisconnect={disconnect}
        />
      )}
      {confirmDialog}
    </>
  );

  const addTile = () => (
    <ConnectorTile
      key="mcp-add"
      logo={addLogo}
      title={t`Any MCP server`}
      source={MCP_ONLY}
      description={addDescription}
      status={t`Add by address`}
      onClick={() => openDialog({})}
    />
  );

  const shared = {
    addTile,
    addServer: () => openDialog({}),
    overlays,
    registryAvailable: signedIn && !registryOff,
  };

  const knownUrls = [...presets.map((p) => p.url), ...servers.map((s) => s.url)];
  const registrySection = renderRegistry();

  function renderRegistry() {
    if (registry.phase === RegistryPhase.IDLE || registry.phase === RegistryPhase.OFF) return null;
    const { shown, more } = arrangeRegistry(registry.listings, knownUrls);
    const moreOpen = showMoreFor === registry.query;
    // No MCP badge: the section says what every tile in it is, and the
    // badge plus Official left a name like Stripe as "Stri…". Where it runs
    // takes the state line instead; none of these is connected yet.
    const listingTile = (listing) => {
      const site = listingPublisher(listing);
      return (
        <ConnectorTile
          key={listing.url}
          logo={listingLogo(listing)}
          title={listing.title}
          description={listing.description || listing.host}
          tag={listing.official ? t`Official` : undefined}
          status={listing.auth === McpAuth.KEY ? t`Runs at ${site} · needs an API key` : t`Runs at ${site}`}
          onClick={() => openDialog({ listing })}
        />
      );
    };
    let body;
    if (registry.phase === RegistryPhase.LOADING) {
      body = (
        <TileGrid>
          {Array.from({ length: LOADING_TILES }, (_, i) => (
            <Skeleton
              key={i}
              className="h-36 rounded-2xl"
              {...(i === 0 ? { role: "status", "aria-label": t`Searching the MCP Registry` } : {})}
            />
          ))}
        </TileGrid>
      );
    } else if (registry.phase === RegistryPhase.FAILED) {
      body = (
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
          {/* The server's sentence already names the registry. */}
          <p className="text-sm text-muted-foreground">{registry.error || t`Couldn't search the MCP Registry.`}</p>
          <Button variant="ghost" size="sm" onClick={() => setRegistryRetry((n) => n + 1)}>
            <Trans>Try again</Trans>
          </Button>
        </div>
      );
    } else if (!shown.length && !more.length) {
      body = (
        <p className="text-sm text-muted-foreground">
          <Trans>Nothing else in the MCP Registry matches “{registry.query}”.</Trans>
        </p>
      );
    } else {
      body = (
        <>
          {shown.length > 0 ? (
            <TileGrid>{shown.map(listingTile)}</TileGrid>
          ) : (
            <p className="text-sm text-muted-foreground">
              <Trans>No server run by its own publisher matches “{registry.query}”.</Trans>
            </p>
          )}
          {more.length > 0 && !moreOpen && (
            <div>
              <Button variant="ghost" size="sm" className="-ml-3" onClick={() => setShowMoreFor(registry.query)}>
                {plural(more.length, {
                  one: "Show # more from other publishers",
                  other: "Show # more from other publishers",
                })}
              </Button>
            </div>
          )}
          {moreOpen && more.length > 0 && <TileGrid>{more.map(listingTile)}</TileGrid>}
        </>
      );
    }
    return (
      <Section key="mcp-registry" title={<Trans>From the MCP Registry</Trans>}>
        {body}
      </Section>
    );
  }

  if (!signedIn) {
    return {
      phase: McpPhase.SIGNED_OUT,
      entries: [],
      ...shared,
      registry: null,
      placeholder: (
        <ConnectorTile
          logo={addLogo}
          title={t`MCP connectors`}
          source={MCP_ONLY}
          description={t`Tools from OpenSEO, PostHog and other apps, for the insights chat. Saved to your account.`}
          status={t`Sign in to connect`}
          disabled
        />
      ),
    };
  }

  if (!loaded) {
    // One live region for the wait, not one per placeholder.
    const loading = { role: "status", "aria-label": t`Loading MCP connectors` };
    return {
      phase: McpPhase.LOADING,
      entries: [],
      ...shared,
      registry: registrySection,
      placeholder: Array.from({ length: LOADING_TILES }, (_, i) => (
        <Skeleton key={i} className="h-36 rounded-2xl" {...(i === 0 ? loading : {})} />
      )),
    };
  }

  if (loadError && !presets.length) {
    return {
      phase: McpPhase.FAILED,
      entries: [],
      ...shared,
      registry: registrySection,
      placeholder: (
        <ConnectorTile
          logo={addLogo}
          title={t`MCP connectors`}
          source={MCP_ONLY}
          description={
            outdated
              ? t`This copy of Duct is older than MCP servers. Update it to connect them.`
              : t`Couldn't load them. ${loadError}`.trim()
          }
          tone="partial"
          status={outdated ? t`Needs an update` : t`Open to try again`}
          onClick={load}
        />
      ),
    };
  }

  const presetEntries = presets.map((preset) => {
    const state = stateOf(serverFor(preset));
    const description = presetDescription(preset);
    return {
      id: `mcp:${preset.id}`,
      title: preset.label,
      description,
      category: MCP_CATEGORY[preset.id] || Category.OTHER,
      status: CATALOG_STATUS[state.tone],
      origin: Origin.VENDOR,
      publisher: preset.publisher || "",
      keywords: ["mcp"],
      render: () => (
        <ConnectorTile
          key={preset.id}
          logo={presetLogo(preset)}
          title={preset.label}
          source={mcpSource(preset.publisher)}
          description={description}
          {...state}
          onClick={() => openDialog({ preset })}
        />
      ),
    };
  });
  const addressEntries = byAddress.map((server) => {
    const state = stateOf(server);
    const title = server.name || serverHost(server.url);
    return {
      id: `mcp-url:${server.id}`,
      title,
      description: serverHost(server.url),
      category: Category.OTHER,
      status: CATALOG_STATUS[state.tone],
      origin: Origin.YOURS,
      publisher: "",
      keywords: ["mcp"],
      render: () => (
        <ConnectorTile
          key={server.id}
          logo={serverLogo(server)}
          title={title}
          source={MCP_ONLY}
          description={serverHost(server.url)}
          {...state}
          onClick={() => openDialog({ url: server.url, name: server.name, server })}
        />
      ),
    };
  });

  return {
    phase: McpPhase.READY,
    entries: [...presetEntries, ...addressEntries],
    ...shared,
    registry: registrySection,
    placeholder: null,
  };
}

/** The MCP tiles alone, in a grid the caller provides, for `/preview`. */
export default function McpConnectors(props) {
  const { phase, entries, addTile, placeholder, overlays } = useMcpConnectors(props);
  if (phase !== McpPhase.READY) return placeholder;
  return (
    <>
      {entries.map((entry) => entry.render())}
      {addTile()}
      {overlays}
    </>
  );
}
