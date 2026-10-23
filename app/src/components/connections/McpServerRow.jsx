"use client";

// One MCP server the user connected, as a row: whose it is, where it lives,
// how it signs in, and what to do about it. The list is where a server added
// by URL is managed at all (it has no tile of its own), and where a server
// whose sign-in lapsed says so before a run trips over it.

import { msg } from "@lingui/core/macro";
import { Trans, useLingui } from "@lingui/react/macro";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { McpAuth, McpServerStatus } from "@/lib/connectorsApi";
import { serverHost, serverSite } from "@/lib/mcpServers";
import EntityAvatar from "./EntityAvatar";

const AUTH_WORDS = {
  [McpAuth.OAUTH]: msg`Signed in`,
  [McpAuth.KEY]: msg`API key`,
  [McpAuth.NONE]: msg`No sign-in`,
};

/**
 * @param preset  The preset this server is, when it is one: its `home` is the
 *   favicon a person recognises, where a server address rarely has one.
 */
export default function McpServerRow({ server, preset = null, onReconnect, onDisconnect, busy = false }) {
  const { i18n } = useLingui();
  const needsReauth = server.status === McpServerStatus.NEEDS_REAUTH;
  const host = serverHost(server.url);
  const auth = AUTH_WORDS[server.auth] ? i18n._(AUTH_WORDS[server.auth]) : "";

  return (
    <li className="mcp-server-row">
      <EntityAvatar url={preset?.home || serverSite(server.url)} name={server.name || host} />
      <div className="mcp-server-text">
        {/* The state rides with the name it is about, so when a narrow row
            wraps, only the buttons move. */}
        <span className="mcp-server-title">
          <span className="mcp-server-name">{server.name || host}</span>
          {needsReauth && (
            <Badge variant="warning" className="shrink-0">
              <Trans>Needs reconnecting</Trans>
            </Badge>
          )}
        </span>
        <span className="mcp-server-meta">{[host, auth].filter(Boolean).join(" · ")}</span>
      </div>
      <div className="conn-account-actions mcp-server-actions">
        {needsReauth && (
          <Button type="button" size="sm" variant="secondary" disabled={busy} onClick={() => onReconnect?.(server)}>
            <Trans>Reconnect</Trans>
          </Button>
        )}
        <Button type="button" size="sm" variant="destructive" disabled={busy} onClick={() => onDisconnect?.(server)}>
          <Trans>Disconnect</Trans>
        </Button>
      </div>
    </li>
  );
}
