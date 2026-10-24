"use client";

// Connecting one MCP server: a preset by name, or any server by its address.
//
// One click is the default and the key is the fallback, the order every
// connector here follows: Connect asks the server what it needs, and the
// answer decides what happens next — a vendor sign-in (this window leaves, or
// on the desktop shell the system browser opens and this dialog waits), a
// save on the spot, or a request for a key. The key field is revealed in
// place for that last one, with the reason, so the person learns why they are
// pasting something rather than meeting a form they did not ask for.

import { useId, useState } from "react";
import { ExternalLink, MessageSquare, ShieldCheck } from "lucide-react";
import { Trans, useLingui } from "@lingui/react/macro";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Spinner } from "@/components/ui/spinner";
import { McpServerStatus } from "@/lib/connectorsApi";
import { MCP_GUIDE_URL } from "@/lib/mcpServers";
import ConnectorDialog from "./ConnectorDialog";
import ConnectorDot from "./ConnectorDot";

/** "" | "starting" | "browser" — "browser" is the desktop shell waiting on the
 *  system browser, where this window stays put and only this says so. */
const PHASE_STARTING = "starting";
const PHASE_BROWSER = "browser";
// The shape of an address, not a sentence: the same in every language.
const EXAMPLE_SERVER_URL = "https://mcp.example.com/mcp";

/**
 * @param preset  `{ id, label, key_url }` for a server offered by name, or
 *   null for one added by its address.
 * @param server  The connected server this dialog is about, if any: the
 *   primary action becomes Reconnect and Disconnect joins the footer.
 * @param onConnect  `(target) => Promise<{ done } | { waiting } | { needsKey }>`,
 *   where `target` is `{ preset, apiKey }` or `{ url, name, apiKey }`; a
 *   rejection's message is shown as the reason it did not connect.
 * @param source  `{ kind, publisher }` for the line under the title: MCP, and
 *   who runs the server.
 * @param initialNeedsKey  Open as though the server had just asked for a key,
 *   reason and all. `/preview` uses it to reach the state with no server.
 * @param initialKeyOpen  Open with the key field showing and no reason given:
 *   a server that signs in with a key reconnects this way.
 */
export default function McpConnectDialog({
  open,
  onOpenChange,
  logo,
  description,
  source,
  preset = null,
  server = null,
  initialUrl = "",
  initialName = "",
  initialNeedsKey = false,
  initialKeyOpen = false,
  onConnect,
  onDisconnect,
}) {
  const { t } = useLingui();
  const formId = useId();
  const [url, setUrl] = useState(initialUrl);
  const [name, setName] = useState(initialName);
  const [key, setKey] = useState("");
  const [needsKey, setNeedsKey] = useState(initialNeedsKey);
  const [keyOpen, setKeyOpen] = useState(initialNeedsKey || initialKeyOpen);
  const [phase, setPhase] = useState("");
  const [error, setError] = useState("");

  const label = preset?.label || server?.name || initialName || "";
  const title = preset ? label : server ? label : t`Add an MCP server`;
  const keyUrl = preset?.key_url || "";
  // A preset offers the key path only where its vendor issues keys; a server
  // added by address might take one, and only its owner knows.
  const offersKey = preset ? Boolean(keyUrl) : true;
  const showKey = keyOpen || needsKey;
  const needsReauth = server?.status === McpServerStatus.NEEDS_REAUTH;
  const tone = !server ? "off" : needsReauth ? "partial" : "on";
  const statusWords = !server ? t`Not connected` : needsReauth ? t`Needs reconnecting` : t`Connected`;

  async function submit(event) {
    event?.preventDefault();
    if (phase === PHASE_STARTING) return;
    setError("");
    const apiKey = showKey ? key.trim() : "";
    if (!preset && !url.trim()) {
      setError(t`Paste the server's address to connect it.`);
      return;
    }
    if (showKey && !apiKey) {
      setError(t`Paste an API key to connect with one.`);
      return;
    }
    setPhase(PHASE_STARTING);
    try {
      const target = preset ? { preset: preset.id, apiKey } : { url: url.trim(), name: name.trim(), apiKey };
      const result = (await onConnect(target)) || {};
      if (result.needsKey) {
        setNeedsKey(true);
        setKeyOpen(true);
        setPhase("");
      } else if (result.waiting) {
        setPhase(PHASE_BROWSER);
      } else if (result.done) {
        setPhase("");
        onOpenChange(false);
      }
      // Otherwise this window is on its way to the vendor; nothing to undo.
    } catch (err) {
      setPhase("");
      // A 401 here is the Duct session, not the server: the request kept the
      // session so a vendor's refusal could never sign anyone out, which
      // means this one has to be said in words.
      setError(
        err?.status === 401
          ? t`Your Duct session has ended. Sign in again, then connect.`
          : err?.message || t`That didn't connect. Try again in a moment.`,
      );
    }
  }

  const primaryLabel =
    phase === PHASE_STARTING ? (
      <Trans>Connecting…</Trans>
    ) : phase === PHASE_BROWSER ? (
      <Trans>Waiting for your browser…</Trans>
    ) : server ? (
      <Trans>Reconnect</Trans>
    ) : (
      <Trans>Connect</Trans>
    );

  return (
    <ConnectorDialog
      open={open}
      onOpenChange={onOpenChange}
      logo={logo}
      title={title}
      description={description}
      source={source}
      status={
        <span className="conn-state">
          <span className="conn-state-glyph" title={statusWords}>
            <ConnectorDot tone={tone} label={statusWords} />
          </span>
        </span>
      }
      footer={
        <>
          {server && (
            <Button type="button" size="sm" variant="destructive" onClick={() => onDisconnect?.(server)}>
              <Trans>Disconnect</Trans>
            </Button>
          )}
          <Button type="submit" form={formId} size="sm" disabled={phase === PHASE_STARTING}>
            {phase === PHASE_STARTING && <Spinner className="size-3.5" />}
            {primaryLabel}
          </Button>
        </>
      }
    >
      <form id={formId} onSubmit={submit} className="conn-dialog-section" noValidate>
        {needsReauth && (
          <p className="conn-hint">
            <Trans>Its sign-in stopped working, so Duct can&rsquo;t use it until you reconnect.</Trans>
          </p>
        )}

        {!preset && (
          <>
            <div className="conn-field">
              <Label htmlFor={`${formId}-url`}><Trans>Server address</Trans></Label>
              <Input
                id={`${formId}-url`}
                type="url"
                inputMode="url"
                autoComplete="off"
                spellCheck={false}
                placeholder={EXAMPLE_SERVER_URL}
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                disabled={Boolean(server)}
              />
              <p className="conn-hint">
                <Trans>Copy it from the server&rsquo;s docs. Duct connects over HTTPS only.</Trans>
              </p>
            </div>
            <div className="conn-field">
              <Label htmlFor={`${formId}-name`}><Trans>Name (optional)</Trans></Label>
              <Input
                id={`${formId}-name`}
                autoComplete="off"
                placeholder={t`e.g. Acme CRM`}
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            </div>
          </>
        )}

        {preset && !showKey && phase !== PHASE_BROWSER && (
          <p className="conn-hint">
            <Trans>You&rsquo;ll sign in at {label} in your browser, then come straight back here.</Trans>
          </p>
        )}

        {/* Why, before what: a sibling of the field rather than inside it, so
            it sits a section's distance from the label, not a label's. */}
        {needsKey && (
          <p className="conn-hint">
            {preset ? (
              <Trans>{label} doesn&rsquo;t offer one-click sign-in to Duct, so it needs an API key instead.</Trans>
            ) : (
              <Trans>This server doesn&rsquo;t offer one-click sign-in to Duct, so it needs an API key instead.</Trans>
            )}
          </p>
        )}
        {showKey && (
          <div className="conn-field">
            <Label htmlFor={`${formId}-key`}><Trans>API key</Trans></Label>
            <Input
              id={`${formId}-key`}
              type="password"
              autoComplete="off"
              spellCheck={false}
              value={key}
              onChange={(e) => setKey(e.target.value)}
              autoFocus={needsKey}
            />
            <div className="conn-field-notes">
              {keyUrl && (
                <a className="app-link mcp-key-link" href={keyUrl} target="_blank" rel="noreferrer">
                  <Trans>Get a key from {label}</Trans>
                  <ExternalLink className="size-3" aria-hidden="true" />
                </a>
              )}
              <p className="conn-hint">
                <Trans>Saved encrypted to your account and sent only to this server.</Trans>
              </p>
            </div>
          </div>
        )}

        {offersKey && !needsKey && (
          <div>
            <Button
              type="button"
              variant="link"
              size="sm"
              className="h-auto px-0"
              aria-expanded={keyOpen}
              onClick={() => {
                setKeyOpen((v) => !v);
                setError("");
              }}
            >
              {keyOpen ? (
                preset ? <Trans>Sign in instead</Trans> : <Trans>Connect without a key</Trans>
              ) : preset ? (
                <Trans>Use an API key instead</Trans>
              ) : (
                <Trans>I have an API key</Trans>
              )}
            </Button>
          </div>
        )}

        {phase === PHASE_BROWSER && (
          <p role="status" className="conn-hint">
            <Trans>Finish signing in in your browser. The server shows up here when you&rsquo;re done.</Trans>
          </p>
        )}
        {error && (
          <p role="alert" className="conn-hint conn-hint--alert">
            {error}
          </p>
        )}

        {/* What an MCP connector is, here rather than on the page: it is the
            moment someone decides whether to connect one. */}
        <ul className="mcp-notes">
          <li>
            <ShieldCheck className="mcp-note-icon" aria-hidden="true" />
            <span>
              {preset ? (
                <Trans>
                  A tool {label} marks read-only runs straight away. Anything else asks you first, every time.
                </Trans>
              ) : (
                <Trans>Duct asks you before every call to a server added by address.</Trans>
              )}
            </span>
          </li>
          <li>
            <MessageSquare className="mcp-note-icon" aria-hidden="true" />
            <span>
              <Trans>
                Only your own insights chats use it, in any project. Scheduled briefs don&rsquo;t call MCP
                connectors yet.
              </Trans>{" "}
              <a className="app-link underline underline-offset-2" href={MCP_GUIDE_URL} target="_blank" rel="noreferrer">
                <Trans>How MCP connectors work</Trans>
              </a>
            </span>
          </li>
        </ul>
      </form>
    </ConnectorDialog>
  );
}
