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

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  listConnectorAccounts,
  saveServerConnector,
} from "../../lib/connectorsApi";

export default function ManualConnectorCard({
  type,            // connector id: "apple_ads" | "meta_ads" | ...
  title,
  description,
  logo,            // emoji string
  fields,          // [{key, label, placeholder, secret?, multiline?, optional?, hint?}]
  accountField = "account_id", // credential key the picked account id is saved under
  docsUrl,
  docsLabel,
  signedIn,
  serverRow,       // stored row for this connector_type (or undefined)
  onSaved,         // async () => void — refresh the stored-rows map
  onRemove,        // async (connectorType) => void
}) {
  const [values, setValues] = useState({});
  const [accounts, setAccounts] = useState(null); // null = not verified yet
  const [pickedAccount, setPickedAccount] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const connected = !!serverRow;

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

  return (
    <article className="connection-card">
      <div className="connection-card-head">
        <div className="connection-logo" aria-hidden="true" style={{ fontSize: 22 }}>
          {logo}
        </div>
        <div>
          <h2 className="connection-title">{title}</h2>
          <p className="connection-description">{description}</p>
        </div>
      </div>

      {!connected && (
        <form onSubmit={verifyAndSave} style={{ display: "grid", gap: 10, marginTop: 12 }}>
          {docsUrl && (
            <p className="app-subtle" style={{ margin: 0, fontSize: 13 }}>
              <a className="app-link" href={docsUrl} target="_blank" rel="noreferrer">
                {docsLabel || "Where to find these credentials"}
              </a>
            </p>
          )}
          {fields.map((f) => (
            <div key={f.key} style={{ display: "grid", gap: 4 }}>
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
              {f.hint && (
                <p className="app-subtle" style={{ margin: 0, fontSize: 12 }}>{f.hint}</p>
              )}
            </div>
          ))}
          <div>
            <Button type="submit" size="sm" disabled={busy || !signedIn}>
              {busy ? "Verifying…" : "Verify & save"}
            </Button>
            {!signedIn && (
              <span className="app-subtle" style={{ marginLeft: 8, fontSize: 12 }}>
                Sign in first — credentials are stored encrypted server-side.
              </span>
            )}
          </div>
        </form>
      )}

      {accounts && accounts.length > 1 && !connected && (
        <div style={{ display: "grid", gap: 6, marginTop: 10 }}>
          <p className="app-subtle" style={{ margin: 0, fontSize: 13 }}>Pick the account to use:</p>
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
        <p style={{ margin: "8px 0 0", fontSize: 13, color: "var(--destructive, #e5484d)" }}>{error}</p>
      )}
      {notice && !error && (
        <p className="app-subtle" style={{ margin: "8px 0 0", fontSize: 13 }}>{notice}</p>
      )}

      <div className="connection-status-row">
        <span className={`status-pill ${connected ? "green" : "grey"}`}>
          {connected
            ? `Connected${serverRow.account_name ? ` — ${serverRow.account_name}` : ""}`
            : "Not connected"}
        </span>
        {connected && (
          <Button type="button" variant="outline" size="sm" onClick={() => onRemove?.(type)}>
            Disconnect
          </Button>
        )}
      </div>
    </article>
  );
}
