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
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button, buttonVariants } from "@/components/ui/button";
import { STORAGE_NONE, STORAGE_SESSION, rowStorage } from "../../lib/credentialStorage";
import { isLocalBackendActive } from "../../lib/localBackend";
import { startConnectorOAuth } from "../../lib/connectorAuth";
import StorageBadge from "./StorageBadge";
import ConnectorDialog from "./ConnectorDialog";
import ConnectorPermissions from "./ConnectorPermissions";
import ConnectorTile from "./ConnectorTile";
import ProjectBinding from "./ProjectBinding";

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
  onEntityChange,
  mappingBusy,
}) {
  // A stored row is durable wherever the server happens to be; without one the
  // token exists only in this tab, which is the case worth naming.
  const storage = syncedToAccount
    ? rowStorage(rows[0], { localSidecar: isLocalBackendActive() })
    : oauthConnected
      ? STORAGE_SESSION
      : STORAGE_NONE;

  const [open, setOpen] = useState(false);
  const [confirmingDisconnect, setConfirmingDisconnect] = useState(false);
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
        storage={storage}
        onClick={() => setOpen(true)}
      />

      <ConnectorDialog
        open={open}
        onOpenChange={setOpen}
        logo={logo}
        title={title}
        description={description}
        status={
          <span className="conn-state">
            {/* Equal 20px slots. The dot is a 7px filled circle and the storage
                glyph a 16px outline in a padded box — centring those two boxes
                still leaves the shapes looking unaligned, because their widths
                (7 vs 24) and internal padding differ. Identical slots give them
                one rail and one optical centre. */}
            <span className="conn-state-glyph" title={pillStatus || status}>
              <span
                className={`conn-dot ${connected ? "conn-dot--on" : tone === "partial" ? "conn-dot--partial" : ""}`}
                role="img"
                aria-label={pillStatus || status}
              />
            </span>
            {oauthConnected && <StorageBadge storage={storage} />}
          </span>
        }
        footer={
          oauthConnected ? (
            <>
              {/* Destructive and irreversible, so it takes the destructive
                  style shadcn already ships — tinted, never filled, which is
                  the canon in DESIGN.md. It was grey-until-hover, which hid
                  the one action on this card worth hesitating over. Red at
                  rest is only safe because it now asks first. */}
              <Button
                type="button"
                size="sm"
                variant="destructive"
                onClick={() => setConfirmingDisconnect(true)}
              >
                Disconnect
              </Button>
              <Button size="sm" variant="secondary" onClick={connect} disabled={phase === "starting"}>
                {phase === "browser" ? "Waiting for your browser…" : "Reconnect"}
              </Button>
            </>
          ) : (
            <Button size="sm" onClick={connect} disabled={phase === "starting"}>
              {connectLabel}
            </Button>
          )
        }
      >
        {children && <div className="conn-dialog-section">{children}</div>}

        {(phase === "browser" || (oauthConnected && storage === STORAGE_SESSION)) && (
          <div className="conn-dialog-section">
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
            {/* The storage sentence lives in the glyph's tooltip; printing it
                here as well put the same words on screen twice. Only the
                session case keeps prose, because it is a call to action rather
                than a description — and it is now rendered only in that case.
                It used to be an always-present wrapper <div> holding a
                conditional <p>, which in a `gap` layout is not free: the empty
                div still took a grid row and 10px of the gap either side of a
                box with nothing in it. */}
            {oauthConnected && storage === STORAGE_SESSION && (
              <p className="conn-hint">
                {signedIn
                  ? "Reconnect to save it to your account."
                  : "Sign in to save it to your account."}
              </p>
            )}
          </div>
        )}

        <ConnectorPermissions scopes={scopes} scopeStatus={scopeStatus} />

        <ProjectBinding
          projectName={projectName}
          rows={rows}
          binding={binding}
          onMappingChange={onMappingChange}
          onEntityChange={onEntityChange}
          busy={mappingBusy}
        />
      </ConnectorDialog>

      {/* The canonical destructive confirm: the title quotes the object, the
          body states scope and irreversibility, and the action is verb + noun.
          Disconnect drops a stored credential — no undo, and any scheduled
          report that used it stops working — which is exactly the case
          DESIGN.md reserves this pattern for. */}
      <AlertDialog open={confirmingDisconnect} onOpenChange={setConfirmingDisconnect}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Disconnect &ldquo;{title}&rdquo;?</AlertDialogTitle>
            <AlertDialogDescription>
              Duct forgets these credentials. Reports and scheduled runs that
              read from {title} stop working until you connect it again, and
              reconnecting means signing in with Google once more.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel type="button">Keep it</AlertDialogCancel>
            <AlertDialogAction
              type="button"
              className={buttonVariants({ variant: "destructive" })}
              onClick={() => {
                setConfirmingDisconnect(false);
                onDisconnect?.();
              }}
            >
              Disconnect
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
