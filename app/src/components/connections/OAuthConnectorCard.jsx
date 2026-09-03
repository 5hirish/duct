"use client";

// Browser sign-in connectors (Google Ads, Analytics, Search Console, Tag
// Manager). The tile shows state; the dialog does the connecting, plus any
// extra credentials the platform needs on top of OAuth — Google Ads is the one
// that does, since Duct's developer token is still pending Google approval.
//
// Connecting goes through `startConnectorOAuth`, not a plain link: in the
// desktop shell the OAuth has to happen in the system browser, and the result
// comes back through the shell's deep link rather than by this window
// navigating anywhere. See `lib/connectorAuth.js`.

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { startConnectorOAuth } from "../../lib/connectorAuth";
import ConnectorDialog from "./ConnectorDialog";
import ConnectorTile from "./ConnectorTile";
import ProjectAccountSelect from "./ProjectAccountSelect";

export default function OAuthConnectorCard({
  title,
  description,
  logo,
  connected,          // fully usable (OAuth done + any extra credentials saved)
  oauthConnected,     // browser sign-in done — may still need extra credentials
  // One row per scope this connector asks for: {scope, label, why, access,
  // required, granted}. Joined server-side so the browser holds no catalog of
  // its own and cannot drift from what the backend actually requests.
  scopes = [],
  scopeStatus = "",   // "complete" | "partial" | "unknown" | "n/a" | ""
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
  // "" | "starting" | "browser". "browser" is a desktop shell waiting on the
  // system browser: this window stays put, so the state has to be visible or
  // the button just looks broken.
  const [phase, setPhase] = useState("");

  async function connect() {
    // "browser" is deliberately not blocked: that state's own "Open it again"
    // is the escape hatch for a browser that never surfaced the tab.
    if (phase === "starting") return;
    setPhase("starting");
    try {
      const mode = await startConnectorOAuth(authorizeUrl);
      // "redirect" means this window is already navigating away; leave the
      // button busy rather than flashing it back to idle mid-unload.
      setPhase(mode === "browser" ? "browser" : "starting");
    } catch {
      setPhase("");
    }
  }

  const connectLabel = phase === "browser" ? "Waiting for your browser…" : "Sign in with Google";

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
                <Button size="sm" variant="secondary" onClick={connect} disabled={phase === "starting"}>
                  {phase === "browser" ? "Waiting for your browser…" : "Reconnect"}
                </Button>
                <Button type="button" variant="outline" size="sm" onClick={onDisconnect}>
                  Disconnect
                </Button>
              </div>
            ) : (
              <Button size="sm" onClick={connect} disabled={phase === "starting"}>
                {connectLabel}
              </Button>
            )}
          </div>
          {phase === "browser" && (
            <p className="conn-hint">
              Finish in your browser — Google won&rsquo;t sign you in inside an app
              window. This card updates on its own when you&rsquo;re done.{" "}
              <button
                type="button"
                className="app-link underline underline-offset-2"
                onClick={connect}
              >
                Open it again
              </button>
            </p>
          )}
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

        {scopes.length > 0 && (
          <div className="conn-dialog-section">
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
              <span className="text-sm font-medium">Permissions</span>
              {scopeStatus === "partial" && (
                <span className="status-pill yellow">Some declined</span>
              )}
              {scopeStatus === "unknown" && (
                <span className="status-pill grey">Not recorded</span>
              )}
            </div>

            {scopeStatus === "unknown" ? (
              <p className="conn-hint" style={{ marginTop: 0 }}>
                This connection was made before Duct recorded which permissions
                Google granted. Reconnect to find out — nothing is assumed either way.
              </p>
            ) : (
              <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "grid", gap: 10 }}>
                {scopes.map((row) => (
                  <li key={row.scope} style={{ display: "flex", gap: 8, alignItems: "flex-start" }}>
                    <span
                      aria-hidden="true"
                      style={{ lineHeight: "1.25rem", flexShrink: 0 }}
                      className={row.granted ? "text-emerald-600" : "text-muted-foreground"}
                    >
                      {row.granted ? "✓" : "—"}
                    </span>
                    <div style={{ minWidth: 0 }}>
                      <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 6 }}>
                        <span className="text-sm">{row.label}</span>
                        <span className="status-pill grey">{row.access}</span>
                        {!row.granted && (
                          <span className={`status-pill ${row.required ? "yellow" : "grey"}`}>
                            {row.required ? "Not granted" : "Declined (optional)"}
                          </span>
                        )}
                      </div>
                      {row.why && (
                        <p className="conn-hint" style={{ marginTop: 2 }}>
                          {row.why}
                        </p>
                      )}
                    </div>
                  </li>
                ))}
              </ul>
            )}

            {scopeStatus === "partial" && (
              <p className="conn-hint">
                Everything ticked above still works. To grant the rest, choose
                Reconnect and tick them on Google&rsquo;s consent screen.
              </p>
            )}
          </div>
        )}

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
