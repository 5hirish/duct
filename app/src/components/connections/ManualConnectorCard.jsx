"use client";

// Reusable manual-credentials connector card (Phase 7 connectors: Apple
// Search Ads, Meta Ads, Stripe, RevenueCat, OpenAI Ads).
//
// These platforms either have no OAuth at all or gate it behind app-review
// processes (Meta App Review, Stripe App publishing, RevenueCat support
// registration), so the user pastes read credentials instead. Flow:
// paste → "Verify & save" calls POST /api/connectors/{id}/accounts to prove
// the credentials work and list reachable accounts → pick one when several →
// credentials are stored Fernet-encrypted server-side (/api/user/connectors).
// Unlike the Google OAuth cards there is no session-only mode: manual
// credentials exist to make server-side pulls possible, so saving requires
// being signed in.
//
// The paste form lives in the tile's dialog — a five-field Apple Search Ads
// form inline would set the height of every card in the grid.

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  listConnectorAccounts,
  saveServerConnector,
} from "../../lib/connectorsApi";
import ConnectorDialog from "./ConnectorDialog";
import ConnectorTile from "./ConnectorTile";
import ProjectAccountSelect from "./ProjectAccountSelect";

export default function ManualConnectorCard({
  type,            // connector id: "apple_ads" | "meta_ads" | ...
  title,
  description,
  logo,
  fields,          // [{key, label, placeholder, secret?, multiline?, optional?, hint?}]
  accountField = "account_id", // credential key the picked account id is saved under
  docsUrl,
  docsLabel,
  signedIn,
  serverRowList = [], // ALL stored rows for this connector_type (one per account)
  onSaved,         // async () => void — refresh the stored-rows map
  onRemoveRow,     // async (rowId) => void — remove one stored account row
  // Per-project account mapping
  projectName,
  binding,
  onMappingChange,
  mappingBusy,
}) {
  const [open, setOpen] = useState(false);
  const [values, setValues] = useState({});
  const [accounts, setAccounts] = useState(null); // null = not verified yet
  const [pickedAccount, setPickedAccount] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  // Several projects can use several accounts (per-project mappings), so a
  // connected card can still open the paste form to add another one.
  const [adding, setAdding] = useState(false);

  const connected = serverRowList.length > 0;
  const formOpen = !connected || adding;

  function setValue(key, v) {
    setValues((prev) => ({ ...prev, [key]: v }));
  }

  function credentialDict() {
    const creds = {};
    for (const f of fields) {
      const v = (values[f.key] || "").trim();
      if (v) creds[f.key] = v;
    }
    return creds;
  }

  async function verifyAndSave(event) {
    event.preventDefault();
    setError("");
    setNotice("");
    const missing = fields.filter((f) => !f.optional && !(values[f.key] || "").trim());
    if (missing.length) {
      setError(`Missing: ${missing.map((f) => f.label).join(", ")}`);
      return;
    }
    setBusy(true);
    try {
      const creds = credentialDict();
      const rows = await listConnectorAccounts(type, creds);
      setAccounts(rows);
      const warning = rows.find((r) => r.warning)?.warning || "";

      // One reachable account → save immediately; several → wait for a pick.
      if (rows.length === 1 || pickedAccount) {
        const chosen = rows.find((r) => r.account_id === pickedAccount) || rows[0] || {};
        await persist(creds, chosen);
        setNotice(
          `Verified${chosen.account_name ? ` — ${chosen.account_name}` : ""}. Credentials saved (encrypted).`
          + (warning ? ` ⚠ ${warning}` : "")
        );
      } else if (rows.length > 1) {
        setNotice(`Verified — ${rows.length} accounts reachable. Pick one below to finish.`);
      } else {
        setNotice("Credentials verified, but no accounts are reachable with them.");
      }
    } catch (err) {
      setAccounts(null);
      setError(err.message || String(err));
    } finally {
      setBusy(false);
    }
  }

  async function persist(creds, account) {
    if (!signedIn) {
      throw new Error("Sign in to save — manual credentials are stored server-side (encrypted) so agents and scheduled pulls can use them.");
    }
    const blob = { ...creds };
    if (account?.account_id) blob[accountField] = account.account_id;
    await saveServerConnector({
      connector_type: type,
      account_id: account?.account_id || "",
      account_name: account?.account_name || "",
      credentials: blob,
    });
    setValues({});
    setAccounts(null);
    setPickedAccount("");
    setAdding(false);
    await onSaved?.();
  }

  async function pickAccount(accountId) {
    setPickedAccount(accountId);
    setBusy(true);
    setError("");
    try {
      const chosen = (accounts || []).find((r) => r.account_id === accountId);
      await persist(credentialDict(), chosen);
      setNotice(`Saved — ${chosen?.account_name || accountId}.`);
    } catch (err) {
      setError(err.message || String(err));
    } finally {
      setBusy(false);
    }
  }

  const status = connected
    ? serverRowList.length > 1
      ? `Connected — ${serverRowList.length} accounts`
      : `Connected${serverRowList[0].account_name ? ` — ${serverRowList[0].account_name}` : ""}`
    : "Not connected";

  return (
    <>
      <ConnectorTile
        logo={logo}
        title={title}
        description={description}
        tone={connected ? "on" : "off"}
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
        {connected && (
          <div className="conn-dialog-section">
            {serverRowList.map((row) => (
              <div key={row.id} className="conn-account-row">
                <span>{row.account_name || row.account_id || "Default account"}</span>
                <Button type="button" variant="outline" size="sm" onClick={() => onRemoveRow?.(row.id)}>
                  Remove
                </Button>
              </div>
            ))}
            <div>
              <Button
                type="button"
                variant="secondary"
                size="sm"
                onClick={() => setAdding((isOpen) => !isOpen)}
              >
                {adding ? "Cancel" : "Add another account"}
              </Button>
            </div>
          </div>
        )}

        {formOpen && (
          <form onSubmit={verifyAndSave} className="conn-dialog-section">
            {docsUrl && (
              <p className="conn-hint">
                <a className="app-link" href={docsUrl} target="_blank" rel="noreferrer">
                  {docsLabel || "Where to find these credentials"}
                </a>
              </p>
            )}
            {fields.map((f) => (
              <div key={f.key} className="conn-field">
                <Label htmlFor={`${type}-${f.key}`}>
                  {f.label}
                  {f.optional ? " (optional)" : ""}
                </Label>
                {f.multiline ? (
                  <textarea
                    id={`${type}-${f.key}`}
                    rows={4}
                    autoComplete="off"
                    placeholder={f.placeholder}
                    value={values[f.key] || ""}
                    onChange={(e) => setValue(f.key, e.target.value)}
                    className="rounded-md border border-input bg-transparent px-3 py-2 text-sm font-mono"
                    spellCheck={false}
                  />
                ) : (
                  <Input
                    id={`${type}-${f.key}`}
                    type={f.secret ? "password" : "text"}
                    autoComplete="off"
                    placeholder={f.placeholder}
                    value={values[f.key] || ""}
                    onChange={(e) => setValue(f.key, e.target.value)}
                  />
                )}
                {f.hint && <p className="conn-hint">{f.hint}</p>}
              </div>
            ))}
            <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
              <Button type="submit" size="sm" disabled={busy || !signedIn}>
                {busy ? "Verifying…" : "Verify & save"}
              </Button>
              {!signedIn && (
                <span className="conn-hint">
                  Sign in first — credentials are stored encrypted server-side.
                </span>
              )}
            </div>
          </form>
        )}

        {accounts && accounts.length > 1 && formOpen && (
          <div className="conn-dialog-section">
            <p className="conn-hint">Pick the account to use:</p>
            {accounts.map((a) => (
              <Button
                key={a.account_id || a.account_name}
                type="button"
                size="sm"
                variant={pickedAccount === a.account_id ? "default" : "outline"}
                disabled={busy}
                onClick={() => pickAccount(a.account_id)}
                style={{ justifyContent: "flex-start" }}
              >
                {a.account_name || a.account_id}
                {a.currency ? ` · ${a.currency}` : ""}
              </Button>
            ))}
          </div>
        )}

        {error && (
          <p role="alert" className="text-destructive" style={{ margin: "12px 0 0", fontSize: 13 }}>
            {error}
          </p>
        )}
        {notice && !error && (
          <p className="conn-hint" style={{ marginTop: 12 }}>{notice}</p>
        )}

        <ProjectAccountSelect
          projectName={projectName}
          rows={serverRowList}
          binding={binding}
          onChange={onMappingChange}
          busy={mappingBusy}
        />
      </ConnectorDialog>
    </>
  );
}
