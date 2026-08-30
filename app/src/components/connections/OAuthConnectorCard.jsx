"use client";

// Browser sign-in connectors (Google Ads, Analytics, Search Console, Tag
// Manager). The tile shows state; the dialog does the connecting, plus any
// extra credentials the platform needs on top of OAuth — Google Ads is the one
// that does, since Duct's developer token is still pending Google approval.

import { useState } from "react";
import { Button } from "@/components/ui/button";
import ConnectorDialog from "./ConnectorDialog";
import ConnectorTile from "./ConnectorTile";
import ProjectAccountSelect from "./ProjectAccountSelect";

export default function OAuthConnectorCard({
  title,
  description,
  logo,
  connected,          // fully usable (OAuth done + any extra credentials saved)
  oauthConnected,     // browser sign-in done — may still need extra credentials
  tone,               // "on" | "partial" | "off"
  status,             // tile status line — phrased as the next action
  pillStatus,         // dialog pill — phrased as state; defaults to `status`
  authorizeUrl,
  onDisconnect,
  signedIn,
  syncedToAccount,    // credentials stored server-side for this connector
  children,           // extra config rendered above the connect row
  // Per-project account mapping
  projectName,
  rows = [],
  binding,
  onMappingChange,
  mappingBusy,
}) {
  const [open, setOpen] = useState(false);

  return (
    <>
      <ConnectorTile
        logo={logo}
        title={title}
        description={description}
        tone={tone}
        status={status}
        onClick={() => setOpen(true)}
      />

      <ConnectorDialog
        open={open}
        onOpenChange={setOpen}
        logo={logo}
        title={title}
        description={description}
      >
        {children && <div className="conn-dialog-section">{children}</div>}

        <div className="conn-dialog-section">
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10 }}>
            <span className={`status-pill ${connected ? "green" : tone === "partial" ? "yellow" : "grey"}`}>
              {pillStatus || status}
            </span>
            {oauthConnected ? (
              <div style={{ display: "flex", gap: 8 }}>
                <Button size="sm" variant="secondary" asChild>
                  <a href={authorizeUrl}>Reconnect</a>
                </Button>
                <Button type="button" variant="outline" size="sm" onClick={onDisconnect}>
                  Disconnect
                </Button>
              </div>
            ) : (
              <Button size="sm" asChild>
                <a href={authorizeUrl}>Sign in with Google</a>
              </Button>
            )}
          </div>
          {oauthConnected && (
            <p className="conn-hint">
              {syncedToAccount
                ? "Synced to your account — available to agents and server-side runs."
                : signedIn
                  ? "This session only — reconnect to sync to your account."
                  : "This session only — sign in to sync to your account."}
            </p>
          )}
        </div>

        <ProjectAccountSelect
          projectName={projectName}
          rows={rows}
          binding={binding}
          onChange={onMappingChange}
          busy={mappingBusy}
        />
      </ConnectorDialog>
    </>
  );
}
