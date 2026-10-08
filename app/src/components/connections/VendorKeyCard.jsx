"use client";

// PostBridge and Apify on the Connections page.
//
// They are connections like the rest: a key the user brings, saved to their
// account as a connector row (service/vendor_keys.py), and the sidebar's
// count already included them. Until this card, the only place to paste
// or remove one was inside Content Studio, so the page that lists a
// person's connections left out two of them.
//
// Not a ManualConnectorCard, because neither key has accounts to pick or a
// project to bind: a project spends its owner's key, whoever is looking.
// The field is Content Studio's own (VendorKeyForm), so a key is checked with
// the vendor and refused in the same words wherever it is pasted.

import { useEffect, useState } from "react";
import { Trans, useLingui } from "@lingui/react/macro";
import { Button } from "@/components/ui/button";
import { useConfirm } from "@/components/ui/confirm-dialog";
import VendorKeyForm from "@/components/content/VendorKeyForm";
import {
  VENDOR,
  VENDOR_HOME,
  connectVendorKey,
  disconnectVendorKey,
  getVendorKeyStatus,
} from "@/lib/contentApi";
import { notifyConnectorsChanged } from "@/lib/connectorsApi";
import { STORAGE_NONE, rowStorage } from "@/lib/credentialStorage";
import { isLocalBackendActive } from "@/lib/localBackend";
import { SOURCE_DETAIL, SOURCE_LABELS } from "@/lib/modelTiers";
import { trackEvent, AnalyticsEvent } from "@/lib/analytics";
import ConnectorDialog from "./ConnectorDialog";
import ConnectorDot from "./ConnectorDot";
import ConnectorTile from "./ConnectorTile";
import StorageBadge from "./StorageBadge";

// The real routes. /preview passes its own, since a vendor that accepts or
// refuses a key cannot be arranged in a browser with no backend.
export const VENDOR_KEY_API = Object.freeze({
  status: getVendorKeyStatus,
  // A saved or forgotten key changes the sidebar's count of connections.
  connect: (vendor, apiKey) => connectVendorKey(vendor, apiKey).then((s) => {
    notifyConnectorsChanged();
    return s;
  }),
  disconnect: (vendor) => disconnectVendorKey(vendor).then(() => notifyConnectorsChanged()),
});

/**
 * @param vendor  VENDOR.POSTBRIDGE | VENDOR.APIFY
 * @param rows  the user's saved rows of this vendor's connector_type (at
 *   most one): whether *they* have a key, independent of the project
 * @param projectId, projectName  the project in the header. Its status says
 *   whether a key on this machine stands in for theirs, and whose key it
 *   spends when it belongs to someone else.
 * @param onChanged  async () => void, re-read the page's rows after a save
 *   or a removal
 */
export default function VendorKeyCard({
  vendor,
  title,
  description,
  logo,
  signedIn,
  rows = [],
  projectId,
  projectName,
  onChanged,
  api = VENDOR_KEY_API,
}) {
  const { t, i18n } = useLingui();
  const { confirm, dialog } = useConfirm();
  const [open, setOpen] = useState(false);
  const [replacing, setReplacing] = useState(false);
  const [status, setStatus] = useState(null);
  const [error, setError] = useState("");
  const [verified, setVerified] = useState(false);

  const own = rows.length > 0;
  // Re-asked after a save or a removal, which is when its answer changes.
  useEffect(() => {
    if (!signedIn || !projectId) return undefined;
    let cancelled = false;
    api.status(vendor, projectId)
      .then((s) => { if (!cancelled) setStatus(s); })
      .catch(() => { if (!cancelled) setStatus(null); });
    return () => { cancelled = true; };
  }, [api, vendor, projectId, signedIn, own]);

  // A key on the machine running Duct (local dev, the desktop sidecar) works
  // without one of theirs: blue, like a provider running on this computer's
  // key. Only readable on a project they own: on anyone else's, the status
  // describes the owner's key, not theirs.
  const machineKey = !own && Boolean(status?.is_owner && status.connected && !status.own_key);
  const tone = own ? "on" : machineKey ? "info" : "off";
  const label = own ? t`Connected` : machineKey ? i18n._(SOURCE_LABELS.env) : t`Not connected`;
  const storage = own ? rowStorage(rows[0], { localSidecar: isLocalBackendActive() }) : STORAGE_NONE;
  const someoneElses = status && !status.is_owner;

  // Resolves only once the vendor accepted the key and it is stored; a
  // refusal throws into the field, which shows the vendor's reason.
  async function connect(apiKey) {
    await api.connect(vendor, apiKey);
    trackEvent(AnalyticsEvent.ConnectorConnected, { provider: vendor });
    setReplacing(false);
    setVerified(true);
    await onChanged?.();
  }

  async function disconnect() {
    const ok = await confirm(vendor === VENDOR.APIFY
      ? {
        title: t`Disconnect Apify?`,
        description: t`Duct forgets your Apify token and stops searching through your account. References you saved stay saved.`,
        action: t`Disconnect`,
        destructive: true,
      }
      : {
        title: t`Disconnect PostBridge?`,
        description: t`Duct forgets your API key and stops publishing through your PostBridge account. Your accounts stay connected in PostBridge.`,
        action: t`Disconnect`,
        destructive: true,
      });
    if (!ok) return;
    setError("");
    setVerified(false);
    try {
      await api.disconnect(vendor);
    } catch (e) {
      setError(e?.message || t`That didn't disconnect. Try again.`);
    }
    await onChanged?.();
  }

  const form = (
    <VendorKeyForm
      layout="inline"
      vendor={title}
      homeUrl={VENDOR_HOME[vendor]}
      onConnect={connect}
    />
  );

  return (
    <>
      <ConnectorTile
        logo={logo}
        title={title}
        description={description}
        tone={tone}
        status={label}
        storage={storage}
        onClick={() => setOpen(true)}
      />

      <ConnectorDialog
        open={open}
        onOpenChange={(next) => {
          setOpen(next);
          if (!next) {
            setReplacing(false);
            setVerified(false);
          }
        }}
        logo={logo}
        title={title}
        description={description}
        status={
          <span className="conn-state">
            <span className="conn-state-glyph" title={label}>
              <ConnectorDot tone={tone} label={label} />
            </span>
            {own && <StorageBadge storage={storage} />}
          </span>
        }
        footer={own && signedIn ? (
          <Button type="button" size="sm" variant="destructive" onClick={disconnect}>
            <Trans>Disconnect</Trans>
          </Button>
        ) : null}
      >
        <div className="conn-dialog-section">
          {/* Before the field: it is the reason a key saved here will not
              change what the project in the header does. */}
          {someoneElses && (
            <p className="conn-hint">
              <Trans>
                {projectName} uses its owner&apos;s {title} account, so a key you save here is used
                for the projects you own.
              </Trans>
            </p>
          )}
          {!signedIn ? (
            <p className="conn-hint">
              <Trans>Sign in first — the connection is saved to your account.</Trans>
            </p>
          ) : own ? (
            <>
              <p className="conn-hint">
                {verified
                  ? <Trans>{title} accepted the key, and it is saved. Every project you own uses it.</Trans>
                  : <Trans>Your key is saved. Every project you own uses it.</Trans>}
              </p>
              {replacing ? form : (
                <div>
                  <Button type="button" size="sm" variant="secondary" onClick={() => setReplacing(true)}>
                    <Trans>Replace key</Trans>
                  </Button>
                </div>
              )}
            </>
          ) : (
            <>
              {machineKey && <p className="conn-hint">{i18n._(SOURCE_DETAIL.env)}</p>}
              {form}
            </>
          )}
          {error && <p role="alert" className="conn-hint conn-hint--alert">{error}</p>}
        </div>
      </ConnectorDialog>
      {dialog}
    </>
  );
}
