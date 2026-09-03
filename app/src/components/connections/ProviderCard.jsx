"use client";

// Bring-your-own model provider key — same tile, same dialog shape the data
// sources use, so one card vocabulary covers "what Duct can reach" wherever
// that question is asked.
//
// `status` is the server's answer from `/api/providers/status` and is the half
// this component cannot know: a provider with no key here may still be
// reachable through Duct's own key or, for Anthropic, an operator subscription
// on this machine. Reporting "No key set" in that case would be true about
// local storage and false about the product.
//
// Two places a key can live, and the difference is not cosmetic:
//
//   * this browser session — sent as a header, gone on refresh, and invisible
//     to anything that runs without a browser attached.
//   * remembered on Duct — encrypted at rest, and the only one that can fund a
//     scheduled brief or a memory-consolidation pass.
//
// So the choice is offered rather than made silently: remembering means the
// key is on our servers, which the old copy explicitly promised it never was.
// On desktop the question does not arise — the OS keychain is strictly better
// than the local sidecar's database, and "our servers" is your own machine.

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  STORAGE_KEYCHAIN,
  STORAGE_NONE,
  STORAGE_SESSION,
  serverStorage,
} from "../../lib/credentialStorage";
import { isLocalBackendActive } from "../../lib/localBackend";
import { clearProviderKey, getProviderKey, setProviderKey } from "../../lib/providerKeys";
import { forgetProviderKey, rememberProviderKey } from "../../lib/providerKeysRemote";
import { isDesktopShell } from "../../lib/shell";
import { SOURCE_DETAIL, SOURCE_LABELS, SOURCE_TONE } from "../../lib/modelTiers";
import ConnectorDialog from "./ConnectorDialog";
import ConnectorTile from "./ConnectorTile";
import StorageBadge from "./StorageBadge";

export default function ProviderCard({ provider, logo, status }) {
  const [open, setOpen] = useState(false);
  const [value, setValue] = useState("");
  const [saved, setSaved] = useState(false);
  const [revealed, setRevealed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const desktop = isDesktopShell();
  // `status.stored` is authoritative — the key itself never comes back, so a
  // saved key is knowable only by presence.
  const [remembered, setRemembered] = useState(Boolean(status?.stored));
  const [remember, setRemember] = useState(true);

  useEffect(() => {
    setRemembered(Boolean(status?.stored));
  }, [status?.stored]);

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

  // Precedence matches the backend's: a supplied key wins over the server's,
  // which wins over a subscription. Anything else is genuinely unreachable.
  //
  // The labels come from `modelTiers` rather than a copy kept here. There was
  // a copy, and it silently rotted the moment the backend split "server" into
  // `env` and `cloud`: every tile fell through to "No key set" while the tier
  // rows two tabs away correctly said "From env".
  const source = saved ? "user" : remembered ? "stored" : status?.source || "none";

  // Where it physically sits, which `source` above does not say. Desktop wins
  // outright: the shell writes to the OS keychain and never offers the
  // remember-on-Duct choice, so a key held there is held there.
  const storage = desktop
    ? saved
      ? STORAGE_KEYCHAIN
      : STORAGE_NONE
    : remembered
      ? serverStorage({ localSidecar: isLocalBackendActive() })
      : saved
        ? STORAGE_SESSION
        : STORAGE_NONE;
  const tile = {
    tone: SOURCE_TONE[source] === "warn" ? "off" : source === "cloud" ? "partial" : "on",
    label: SOURCE_LABELS[source] || SOURCE_LABELS.none,
    detail: SOURCE_DETAIL[source] || SOURCE_DETAIL.none,
  };

  // The desktop keychain can genuinely refuse a write — most often on Linux,
  // where the Secret Service daemon that backs it may not be running at all.
  // Reporting that matters more than usual here: the value is a secret the user
  // pasted, and a silent failure looks exactly like success until the next
  // agent run fails for no visible reason.
  async function save() {
    setBusy(true);
    setError("");
    try {
      if (!desktop && remember) {
        // Remembered keys are deliberately NOT also kept in sessionStorage.
        // Two copies of a secret means two places to revoke it, and the header
        // would only ever restate what the server already holds.
        await rememberProviderKey(provider.statusId, trimmed);
        await clearProviderKey(provider.id);
        setRemembered(true);
        setValue("");
        setSaved(false);
        setRevealed(false);
      } else {
        await setProviderKey(provider.id, trimmed);
        setSaved(Boolean(trimmed));
      }
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
      // Clear both homes regardless of which one this card thinks is in use —
      // "Remove" has to mean the key is gone, not gone from wherever the UI
      // last looked.
      await clearProviderKey(provider.id);
      if (remembered) await forgetProviderKey(provider.statusId);
      setValue("");
      setSaved(false);
      setRemembered(false);
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
        tone={tile.tone}
        status={tile.label}
        storage={storage}
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
            {trimmed && !looksValid ? (
              <p className="conn-hint">Keys usually start with &ldquo;{provider.prefix}&rdquo;.</p>
            ) : storage !== STORAGE_NONE ? (
              <StorageBadge storage={storage} detail />
            ) : (
              // Nothing saved yet, so this describes where the next save lands
              // rather than where anything currently is.
              <p className="conn-hint">
                {desktop
                  ? "Will be stored in your OS keychain on this machine."
                  : remember
                    ? "Will be encrypted and stored on Duct, so scheduled runs use your key too."
                    : "Will be kept in this browser session only — cleared when you close the tab, and unavailable to scheduled runs."}
              </p>
            )}
            {!desktop && (
              <label className="conn-hint" style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <input
                  type="checkbox"
                  checked={remember}
                  onChange={(event) => setRemember(event.target.checked)}
                  disabled={busy}
                />
                Remember this key on Duct
              </label>
            )}
            {remembered && (
              <p className="conn-hint">
                A saved key is already in use. Paste a new one to replace it, or
                Remove to forget it.
              </p>
            )}
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
            <span
              className={`status-pill ${tile.tone === "on" ? "green" : "grey"}`}
              title={tile.detail}
            >
              {tile.label}
            </span>
            <div style={{ display: "flex", gap: 8 }}>
              {(saved || remembered) && (
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
