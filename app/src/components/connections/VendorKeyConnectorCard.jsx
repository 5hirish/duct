"use client";

// A vendor Duct uses through the owner's own account (a scheduler such as
// Zernio or PostBridge, Apify for TikTok research) as a Toolbox connector:
// the tile, and the dialog that connects it with an API key or disconnects it.
//
// Connecting these lived inside Content Studio, on whichever tab needed the
// vendor (Accounts, Analytics, Plans, Discover), each with its own key form.
// Connecting an account is the Toolbox's job for every other tool, and the
// next vendors may come by OAuth or MCP rather than a key, which the Toolbox
// already draws. Content Studio keeps only the choices that are its own, such
// as which scheduler a project posts through.

import { useState } from "react";
import { ExternalLink } from "lucide-react";
import { Trans, useLingui } from "@lingui/react/macro";
import { Button } from "@/components/ui/button";
import { useConfirm } from "@/components/ui/confirm-dialog";
import { NATIVE_SOURCE } from "@/lib/connectorSource";
import ConnectorDialog from "./ConnectorDialog";
import ConnectorTile from "./ConnectorTile";
import { ReportedPlatforms } from "@/components/content/ConnectorGate";
import VendorKeyForm from "@/components/content/VendorKeyForm";

/**
 * @param vendor  `{ id, label, dashboard_url, connected, own_key, is_owner, reports? }`:
 *   a row of GET /content/publishers, or a vendor-key status with its name
 *   and home added.
 * @param logo  The tile's mark. Neither scheduler nor Apify ships one, and a
 *   redrawn brand is a trademark problem (logos.jsx), so callers pass a glyph
 *   for what the tool does.
 * @param usage  What connecting it is for, shown once it is connected.
 * @param forget  The disconnect confirmation's body: what stops, what stays.
 * @param onConnect  (vendor, apiKey) → resolves once the vendor accepted it.
 * @param onDisconnect  (vendor) → resolves once the key is forgotten.
 */
export default function VendorKeyConnectorCard({
  vendor, logo, description, usage, forget, onConnect, onDisconnect, featured, benefit,
}) {
  const { t } = useLingui();
  const [open, setOpen] = useState(false);
  const { confirm, dialog } = useConfirm();
  const name = vendor.label;
  const connected = vendor.connected;
  const status = connected ? t`Connected` : t`Not connected`;

  async function disconnect() {
    const ok = await confirm({
      title: t`Disconnect ${name}?`,
      description: forget,
      action: t`Disconnect`,
      destructive: true,
    });
    if (ok) await onDisconnect(vendor);
  }

  return (
    <>
      <ConnectorTile
        logo={logo}
        title={name}
        description={description}
        source={NATIVE_SOURCE}
        tone={connected ? "on" : "off"}
        status={status}
        onClick={() => setOpen(true)}
        featured={featured}
        benefit={benefit}
      />
      <ConnectorDialog
        open={open}
        onOpenChange={setOpen}
        logo={logo}
        title={name}
        description={description}
        source={NATIVE_SOURCE}
        status={
          <span className="conn-state">
            <span className="conn-state-glyph" title={status}>
              <span className={`conn-dot${connected ? " conn-dot--on" : ""}`} role="img" aria-label={status} />
            </span>
          </span>
        }
        footer={
          connected && vendor.own_key && vendor.is_owner ? (
            <Button type="button" size="sm" variant="destructive" onClick={disconnect}>
              <Trans>Disconnect</Trans>
            </Button>
          ) : undefined
        }
      >
        {vendor.reports?.length > 0 && (
          <div className="conn-dialog-section">
            <ReportedPlatforms platforms={vendor.reports} />
          </div>
        )}
        <div className="conn-dialog-section">
          {connected ? (
            <p className="text-sm text-muted-foreground">
              {usage}{" "}
              <a
                href={vendor.dashboard_url}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1 underline-offset-2 hover:text-foreground hover:underline"
              >
                <Trans>Open {name}</Trans>
                <ExternalLink className="size-3" aria-hidden />
              </a>
            </p>
          ) : (
            <VendorKeyForm
              layout="inline"
              vendor={name}
              homeUrl={vendor.dashboard_url}
              isOwner={vendor.is_owner}
              onConnect={async (apiKey) => {
                await onConnect(vendor, apiKey);
                setOpen(false);
              }}
            />
          )}
        </div>
      </ConnectorDialog>
      {dialog}
    </>
  );
}
