"use client";

// Connecting one MCP server: a preset by name, a server found in the MCP
// Registry (its address filled in, and where it runs said plainly), or any
// server by its address. A connected one says whether it works, and why not
// when it doesn't, with a check that tries it again on the spot.
//
// One click is the default and the key is the fallback, the order every
// connector here follows: Connect asks the server what it needs, and the
// answer decides what happens next — a vendor sign-in (this window leaves, or
// on the desktop shell the system browser opens and this dialog waits), a
// save on the spot, or a request for a key. The key field is revealed in
// place for that last one, with the reason, so the person learns why they are
// pasting something rather than meeting a form they did not ask for.

import { useId, useState } from "react";
import { ExternalLink, Globe, MessageSquare, ShieldCheck, TriangleAlert } from "lucide-react";
import { plural } from "@lingui/core/macro";
import { Trans, useLingui } from "@lingui/react/macro";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Spinner } from "@/components/ui/spinner";
import { MCP_GUIDE_URL, PROBLEM_DETAIL, serverProblem } from "@/lib/mcpServers";
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
 * @param listing  A server found in the MCP Registry (`{ url, title, host,
 *   runs_host, auth, key_hint, website }`), connected by its address with no
 *   address field to fill.
 * @param onCheck  `(server) => Promise<{ server, tools }>`: list its tools
 *   with what is saved; `tools` is null when that failed.
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
  listing = null,
  initialUrl = "",
  initialName = "",
  initialNeedsKey = false,
  initialKeyOpen = false,
  onConnect,
  onCheck,
  onDisconnect,
}) {
  const { t, i18n } = useLingui();
  const formId = useId();
  const [url, setUrl] = useState(initialUrl);
  const [name, setName] = useState(initialName);
  const [key, setKey] = useState("");
  const [needsKey, setNeedsKey] = useState(initialNeedsKey);
  const [keyOpen, setKeyOpen] = useState(initialNeedsKey || initialKeyOpen);
  const [phase, setPhase] = useState("");
  const [error, setError] = useState("");
  // The last check's outcome, `{ ok, text }`, which replaces the recorded
  // reason: it is newer.
  const [checking, setChecking] = useState(false);
  const [checked, setChecked] = useState(null);

  const label = preset?.label || server?.name || listing?.title || initialName || "";
  const title = preset || server || listing ? label : t`Add an MCP server`;
  // A registry publisher's site is the nearest thing to a key page it names.
  const keyUrl = preset?.key_url || listing?.website || "";
  // A preset offers the key path only where its vendor issues keys; a server
  // added by address might take one, and only its owner knows.
  const offersKey = preset ? Boolean(keyUrl) : true;
  const showKey = keyOpen || needsKey;
  const problem = serverProblem(server);
  const tone = !server ? "off" : problem ? "partial" : "on";
  const statusWords = !server ? t`Not connected` : problem ? t`Needs attention` : t`Connected`;
  // Typing an address belongs to a server nobody named for us.
  const byAddress = !preset && !listing;

  async function submit(event) {
    event?.preventDefault();
    if (phase === PHASE_STARTING) return;
    setError("");
    const apiKey = showKey ? key.trim() : "";
    if (byAddress && !url.trim()) {
      setError(t`Paste the server's address to connect it.`);
      return;
    }
    if (showKey && !apiKey) {
      setError(t`Paste an API key to connect with one.`);
      return;
    }
    setPhase(PHASE_STARTING);
    try {
      const target = preset
        ? { preset: preset.id, apiKey }
        : listing
          ? { url: listing.url, name: listing.title, apiKey }
          : { url: url.trim(), name: name.trim(), apiKey };
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

  async function check() {
    if (!server || checking) return;
    setChecking(true);
    setChecked(null);
    try {
      const res = await onCheck?.(server);
      const after = serverProblem(res?.server);
      setChecked(
        res?.tools == null
          ? { ok: false, text: after ? i18n._(PROBLEM_DETAIL[after]) : t`It didn't answer. Try again in a moment.` }
          : {
              ok: true,
              text: plural(res.tools, {
                one: "Working. # tool is ready for the insights chat.",
                other: "Working. # tools are ready for the insights chat.",
              }),
            },
      );
    } catch (err) {
      setChecked({ ok: false, text: err?.message || t`Couldn't check it. Try again in a moment.` });
    } finally {
      setChecking(false);
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
        {/* Why it needs attention, from the server's own record, until a
            check says otherwise. */}
        {problem && !checked && <p className="conn-hint">{i18n._(PROBLEM_DETAIL[problem])}</p>}
        {server && (
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
            {checked && (
              <p role="status" className={checked.ok ? "conn-hint" : "conn-hint conn-hint--alert"}>
                {checked.text}
              </p>
            )}
            <Button
              type="button"
              variant="link"
              size="sm"
              className="h-auto px-0"
              disabled={checking}
              onClick={check}
            >
              {checking && <Spinner className="size-3.5" />}
              {checking ? <Trans>Checking…</Trans> : <Trans>Check connection</Trans>}
            </Button>
          </div>
        )}

        {listing && !server && (
          <p className="mcp-listing-host">
            {listing.runs_host ? (
              <Globe className="mcp-note-icon" aria-hidden="true" />
            ) : (
              <TriangleAlert className="mcp-note-icon mcp-note-icon--warn" aria-hidden="true" />
            )}
            <span>
              {listing.runs_host ? (
                <Trans>
                  Runs at <strong className="font-medium text-foreground">{listing.host}</strong>, an address
                  its publisher proved to the MCP Registry they own.
                </Trans>
              ) : (
                <Trans>
                  Runs at <strong className="font-medium text-foreground">{listing.host}</strong>, which its
                  publisher hasn&rsquo;t shown they run. What Duct sends it, your sign-in included, goes to
                  whoever does.
                </Trans>
              )}
            </span>
          </p>
        )}

        {byAddress && (
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
        {listing && !server && !showKey && phase !== PHASE_BROWSER && (
          <p className="conn-hint">
            <Trans>If it asks you to sign in, that happens in your browser and you come straight back here.</Trans>
          </p>
        )}

        {/* Why, before what: a sibling of the field rather than inside it, so
            it sits a section's distance from the label, not a label's. */}
        {needsKey && (
          <p className="conn-hint">
            {listing ? (
              <Trans>This server signs in with an API key rather than a one-click sign-in.</Trans>
            ) : preset ? (
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
              {/* The publisher's own words about its key, quoted as theirs. */}
              {listing?.key_hint && <p className="conn-hint">{listing.key_hint}</p>}
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
              {preset?.trust_read_only ? (
                <Trans>
                  A tool {label} marks read-only runs straight away. Anything else asks you first, every time.
                </Trans>
              ) : preset ? (
                <Trans>
                  {label} can reach your account&rsquo;s secrets, so Duct asks you before every call to it.
                </Trans>
              ) : listing ? (
                <Trans>Duct asks you before every call to a server from the MCP Registry.</Trans>
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
