"use client";

// Bring-your-own model provider key — same tile, same dialog as the data
// sources, so "where do my keys live" and "where do my connectors live" look
// and behave like one page.

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { clearProviderKey, getProviderKey, setProviderKey } from "../../lib/providerKeys";
import ConnectorDialog from "./ConnectorDialog";
import ConnectorTile from "./ConnectorTile";

export default function ProviderCard({ provider, logo }) {
  const [open, setOpen] = useState(false);
  const [value, setValue] = useState("");
  const [saved, setSaved] = useState(false);
  const [revealed, setRevealed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let alive = true;
    getProviderKey(provider.id).then((stored) => {
      if (!alive) return;
      setValue(stored || "");
      setSaved(Boolean(stored));
    });
    return () => {
      alive = false;
    };
  }, [provider.id]);

  const trimmed = value.trim();
  const looksValid = !provider.prefix || trimmed.startsWith(provider.prefix);

  // The desktop keychain can genuinely refuse a write — most often on Linux,
  // where the Secret Service daemon that backs it may not be running at all.
  // Reporting that matters more than usual here: the value is a secret the user
  // pasted, and a silent failure looks exactly like success until the next
  // agent run fails for no visible reason.
  async function save() {
    setBusy(true);
    setError("");
    try {
      await setProviderKey(provider.id, trimmed);
      setSaved(Boolean(trimmed));
    } catch (err) {
      setError(String(err?.message || err));
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    setBusy(true);
    setError("");
    try {
      await clearProviderKey(provider.id);
      setValue("");
      setSaved(false);
      setRevealed(false);
    } catch (err) {
      setError(String(err?.message || err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <ConnectorTile
        logo={logo}
        title={provider.label}
        description={provider.description}
        tone={saved ? "on" : "off"}
        status={saved ? "Key saved" : "No key set"}
        onClick={() => setOpen(true)}
      />

      <ConnectorDialog
        open={open}
        onOpenChange={setOpen}
        logo={logo}
        title={provider.label}
        description={provider.description}
      >
        <div className="conn-dialog-section">
          <div className="conn-field">
            <Label htmlFor={`provider-${provider.id}`}>API key</Label>
            <div style={{ display: "flex", gap: 8 }}>
              <Input
                id={`provider-${provider.id}`}
                type={revealed ? "text" : "password"}
                value={value}
                placeholder={provider.placeholder}
                onChange={(event) => setValue(event.target.value)}
                autoComplete="off"
                autoCapitalize="off"
                autoCorrect="off"
                spellCheck={false}
              />
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => setRevealed((shown) => !shown)}
                disabled={!value}
              >
                {revealed ? "Hide" : "Show"}
              </Button>
            </div>
            <p className="conn-hint">
              {trimmed && !looksValid
                ? `Keys usually start with "${provider.prefix}".`
                : "Stored in this browser session and sent with each request — never on our servers."}
            </p>
            <p className="conn-hint">
              <a className="app-link" href={provider.consoleUrl} target="_blank" rel="noreferrer">
                Get a key from {provider.label}
              </a>
            </p>
          </div>

          {error && (
            <p role="alert" className="text-destructive" style={{ margin: 0, fontSize: 12 }}>
              {error}
            </p>
          )}

          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10 }}>
            <span className={`status-pill ${saved ? "green" : "grey"}`}>
              {saved ? "Saved" : "Not set"}
            </span>
            <div style={{ display: "flex", gap: 8 }}>
              {saved && (
                <Button type="button" variant="outline" size="sm" onClick={remove} disabled={busy}>
                  Remove
                </Button>
              )}
              <Button type="button" size="sm" onClick={save} disabled={busy || !trimmed || !looksValid}>
                Save
              </Button>
            </div>
          </div>
        </div>
      </ConnectorDialog>
    </>
  );
}
