"use client";

// Browser sign-in connectors (Google Ads, Analytics, Search Console, Tag
// Manager). The tile shows state; the dialog does the connecting, plus any
// extra credentials the platform needs on top of OAuth — Google Ads is the one
// that does, since Duct's developer token is still pending Google approval.
//
// Connecting goes through `startConnectorOAuth`, not a plain link: it mints
// the link naming this session's user first, and in the desktop shell the
// OAuth has to happen in the system browser, with the result coming back
// through the shell's deep link rather than by this window navigating
// anywhere. See `lib/connectorAuth.js`.
//
// What the card shows is what the account has stored, nothing else: `rows`
// come from the server, and the token never reaches this app (issue #456).

import { useState } from "react";
import { Trans, useLingui } from "@lingui/react/macro";
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
import { STORAGE_NONE, rowStorage } from "../../lib/credentialStorage";
import { isLocalBackendActive } from "../../lib/localBackend";
import { startConnectorOAuth } from "../../lib/connectorAuth";
import { NATIVE_SOURCE } from "../../lib/connectorSource";
import StorageBadge from "./StorageBadge";
import ConnectorDialog from "./ConnectorDialog";
import ConnectorPermissions from "./ConnectorPermissions";
import ConnectorTile from "./ConnectorTile";
import ProjectBinding from "./ProjectBinding";

export default function OAuthConnectorCard({
  title,
  description,
  logo,
  connectorType,      // "google_ads" | "ga4" | "gsc" | "gtm"
  connected,          // fully usable (OAuth done + any extra credentials saved)
  oauthConnected,     // a stored row exists — may still need extra settings
  // One row per scope this connector asks for: {scope, label, why, access,
  // required, granted}. Joined server-side so the browser holds no catalog of
  // its own and cannot drift from what the backend actually requests.
  scopes = [],
  scopeStatus = "",   // "complete" | "partial" | "unknown" | "n/a" | ""
  tone,               // "on" | "partial" | "off"
  status,             // tile status line — phrased as the next action
  pillStatus,         // dialog pill — phrased as state; defaults to `status`
  onDisconnect,
  // How Connect starts; the preview passes a stub so pressing it mints no link.
  start = startConnectorOAuth,
  children,           // extra config rendered above the connect row
  // Per-project account mapping
  projectName,
  rows = [],
  binding,
  onMappingChange,
  onEntityChange,
  mappingBusy,
}) {
  const { t } = useLingui();
  // Where the stored row lives: the cloud, or this machine for a self-hosted
  // sidecar on its own database.
  const storage = oauthConnected
    ? rowStorage(rows[0], { localSidecar: isLocalBackendActive() })
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
      const mode = await start(connectorType);
      // "redirect" means this window is already navigating away; leave the
      // button busy rather than flashing it back to idle mid-unload.
      setPhase(mode === "browser" ? "browser" : "starting");
    } catch {
      // The link could not be minted (a dead session signs out on its own;
      // anything else leaves the button to try again).
      setPhase("");
    }
  }

  const connectLabel = phase === "browser" ? t`Waiting for your browser…` : t`Sign in with Google`;

  return (
    <>
      <ConnectorTile
        logo={logo}
        title={title}
        description={description}
        source={NATIVE_SOURCE}
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
        source={NATIVE_SOURCE}
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
                <Trans>Disconnect</Trans>
              </Button>
              <Button size="sm" variant="secondary" onClick={connect} disabled={phase === "starting"}>
                {phase === "browser" ? <Trans>Waiting for your browser…</Trans> : <Trans>Reconnect</Trans>}
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

        {/* The storage sentence lives in the glyph's tooltip; printing it
            here as well put the same words on screen twice. A section is
            rendered only when it has something in it: in a `gap` layout an
            empty wrapper still takes a grid row and the gap either side. */}
        {phase === "browser" && (
          <div className="conn-dialog-section">
            <p className="conn-hint">
              <Trans>
                Finish in your browser — Google won’t sign you in inside an app
                window. This card updates on its own when you’re done.{" "}
                <button
                  type="button"
                  className="app-link underline underline-offset-2"
                  onClick={connect}
                >
                  Open it again
                </button>
              </Trans>
            </p>
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
            <AlertDialogTitle>
              <Trans>Disconnect “{title}”?</Trans>
            </AlertDialogTitle>
            <AlertDialogDescription>
              <Trans>
                Duct forgets these credentials. Reports and scheduled runs that
                read from {title} stop working until you connect it again, and
                reconnecting means signing in with Google once more.
              </Trans>
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel type="button">
              <Trans>Keep it</Trans>
            </AlertDialogCancel>
            <AlertDialogAction
              type="button"
              className={buttonVariants({ variant: "destructive" })}
              onClick={() => {
                setConfirmingDisconnect(false);
                onDisconnect?.();
              }}
            >
              <Trans>Disconnect</Trans>
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
