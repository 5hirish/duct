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
import { Eye, EyeOff } from "lucide-react";
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
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  STORAGE_CLOUD,
  STORAGE_KEYCHAIN,
  STORAGE_LOCAL,
  STORAGE_NONE,
  STORAGE_SESSION,
  serverStorage,
} from "../../lib/credentialStorage";
import { isLocalBackendActive } from "../../lib/localBackend";
import { clearProviderKey, getProviderKey, setProviderKey } from "../../lib/providerKeys";
import { forgetProviderKey, rememberProviderKey } from "../../lib/providerKeysRemote";
import { Checkbox } from "@/components/ui/checkbox";
import { DESKTOP_DOWNLOAD_URL, isDesktopShell } from "../../lib/shell";
import {
  chatgptAuthAvailable,
  chatgptLogin,
  chatgptLoginCancel,
  chatgptLogout,
  chatgptStatus,
  isChatgptCancelled,
  planLabel,
} from "../../lib/chatgpt";
import { SOURCE_DETAIL, SOURCE_LABELS, SOURCE_TONE } from "../../lib/modelTiers";
import ConnectorDialog from "./ConnectorDialog";
import ConnectorDot from "./ConnectorDot";
import ConnectorTile from "./ConnectorTile";
import StorageBadge from "./StorageBadge";

/**
 * `SOURCE_TONE`'s vocabulary → `ConnectorTile`'s.
 *
 * Two scales that were never going to be the same words: one grades a
 * credential ("is this yours"), the other grades a connection ("is this
 * working"). They used to be bridged by an inline ternary that named `cloud`
 * as its one special case, which is how `env` went on reading green for the
 * release after the backend split the two apart — a new source had to be
 * remembered in a conditional rather than declared in a table.
 *
 * `info` is the pair that matters: Duct's key, or this machine's. Blue, not
 * amber — the run will succeed, it is simply not funded by anything the reader
 * did on this page.
 */
const TILE_TONE = { ok: "on", info: "info", warn: "off" };

/**
 * @param planEnabled  The backend's kill switch for "Continue with ChatGPT"
 *   (`chatgpt_auth_enabled` on `/providers/status`). Off hides the plan
 *   everywhere on this card — the tag, the section, the button — because the
 *   Codex endpoint is undocumented and "advertised but broken" is the one
 *   state worse than absent. Only OpenAI reads it; the others have no plan.
 */
/**
 * How the confirm names what it is about to drop, completing "Duct forgets the
 * key …".
 *
 * Not a reuse of `STORAGE_LABELS`: those name a resting place ("In your
 * keychain") and read as a fragment mid-sentence. `STORAGE_NONE` is reachable
 * here — a key the server rejects offers Remove while this card holds nothing
 * of its own — so it gets a phrase rather than a blank.
 */
const REMOVAL_SCOPE = {
  [STORAGE_KEYCHAIN]: "held in this machine\u2019s keychain",
  [STORAGE_SESSION]: "held for this browser session",
  [STORAGE_CLOUD]: "saved to your Duct account",
  [STORAGE_LOCAL]: "saved on this device",
  [STORAGE_NONE]: "stored for this provider",
};

export default function ProviderCard({ provider, logo, status, planEnabled = true }) {
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

  // The user's ChatGPT plan, for the one provider that has one. It lived on a
  // separate "ChatGPT plan" tile, and this dialog's setup steps sent people
  // off to find it — a second card for the same company, which is exactly
  // the OpenAI-vs-ChatGPT confusion the tile exists to remove. The sign-in
  // itself stays in the shell (`lib/chatgpt.js`): this only asks and shows.
  const planOffered = Boolean(provider.hasPlan && planEnabled);
  const [plan, setPlan] = useState({ available: false, status: { connected: false } });
  // *Why* the plan is busy, not just that it is. One boolean made the
  // Reconnect button read "Waiting for your browser…" while a disconnect was
  // in flight — a sentence about a browser that was never opened.
  const [planBusy, setPlanBusy] = useState("");
  const signingIn = planBusy === "login";
  const [planError, setPlanError] = useState("");
  // Both destructive actions ask first, the way every other connection in the
  // app does. Dropping a key is not undoable from here — whether it can be
  // recovered at all depends on whether the user still has it somewhere else,
  // which is exactly the case DESIGN.md reserves the confirm for.
  const [confirmingRemove, setConfirmingRemove] = useState(false);
  const [confirmingDisconnect, setConfirmingDisconnect] = useState(false);
  const planConnected = planOffered && plan.available && Boolean(plan.status?.connected);

  useEffect(() => {
    if (!planOffered) return undefined;
    let alive = true;
    chatgptAuthAvailable().then(async (available) => {
      if (!alive) return;
      const current = available ? await chatgptStatus() : { connected: false };
      if (alive) setPlan({ available, status: current });
    });
    return () => {
      alive = false;
    };
  }, [planOffered]);

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
  // Something in this provider's slot that it could never accept. The server
  // is the authority here and `saved` must not override it: `saved` only means
  // "this browser is holding a string for this provider", which is exactly
  // what is wrong. Gating the warning on `!saved` — as this first did — hid it
  // in the one case it exists for, and let `source` below report the junk as
  // "Your key", green, while the backend was refusing to spend it.
  const mismatched = Boolean(status?.key_mismatch);

  // Same order the backend spends them in (`resolve_provider_key`): the
  // request header first — a pasted key, else the plan's access token that
  // `providerKeyHeaders` puts in the same slot — then a stored key, then the
  // server's. A stored key does not outrank the plan, because it never gets
  // the chance to: the header is already there.
  const source = mismatched
    ? "none"
    : saved
      ? "user"
      : planConnected
        ? "subscription"
        : remembered
          ? "stored"
          : status?.source || "none";

  // Where it physically sits, which `source` above does not say. Desktop wins
  // outright: the shell writes to the OS keychain and never offers the
  // remember-on-Duct choice, so a key held there is held there.
  // Two answers, because the field and the tile ask different questions. The
  // notes under the key field describe *the key* — where the next save lands,
  // or where the saved one is — and must not mention the plan, which is not a
  // key and is not in that field. The tile and header describe the credential
  // that will actually be spent, which on a plan sign-in is the keychain
  // bundle. Using one value for both painted "Held by your keychain" under an
  // empty field the moment the plan connected.
  const keyStorage = desktop
    ? saved
      ? STORAGE_KEYCHAIN
      : STORAGE_NONE
    : remembered
      ? serverStorage({ localSidecar: isLocalBackendActive() })
      : saved
        ? STORAGE_SESSION
        : STORAGE_NONE;
  const storage = keyStorage === STORAGE_NONE && planConnected ? STORAGE_KEYCHAIN : keyStorage;
  const storageSentence = REMOVAL_SCOPE[keyStorage] || REMOVAL_SCOPE[STORAGE_NONE];
  const tile = mismatched
    ? {
        tone: "off",
        label: "Not a key we can use",
        detail: `What's stored for ${provider.label} isn't a key it accepts, so runs skip it. Choose Remove key, then paste a new one.`,
      }
    : {
        tone: TILE_TONE[SOURCE_TONE[source]] || "on",
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

  async function signInPlan() {
    setPlanBusy("login");
    setPlanError("");
    try {
      const next = await chatgptLogin();
      setPlan((current) => ({ ...current, status: next || { connected: false } }));
    } catch (err) {
      // Cancelled is the user's own doing — the button below, or a second
      // click that replaced a tab they had closed. Nothing to explain.
      if (!isChatgptCancelled(err)) setPlanError(String(err?.message || err));
    } finally {
      setPlanBusy("");
    }
  }

  // The button resets when the shell answers the pending login with
  // "cancelled"; a shell too old to know the command leaves it to its timeout.
  function cancelPlan() {
    chatgptLoginCancel();
  }

  async function signOutPlan() {
    setPlanBusy("logout");
    setPlanError("");
    try {
      await chatgptLogout();
      setPlan((current) => ({ ...current, status: { connected: false } }));
    } catch (err) {
      setPlanError(String(err?.message || err));
    } finally {
      setPlanBusy("");
    }
  }

  return (
    <>
      <ConnectorTile
        logo={logo}
        title={provider.label}
        tag={planOffered ? "Works with ChatGPT" : undefined}
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
        // Where the key stands, said once, beside the title — the same place
        // every other connector says it. It used to be a `status-pill` down in
        // the action row, which is both a second answer to a question the
        // header already answers and the pill DESIGN.md lists to retire.
        status={
          <span className="conn-state">
            <span className="conn-state-glyph" title={tile.detail}>
              <ConnectorDot tone={tile.tone} label={tile.label} />
            </span>
            <StorageBadge storage={storage} />
          </span>
        }
        footer={
          <>
            {/* "Remove key", not "Remove": this dialog can hold two
                credentials at once, and a bare verb in the footer does not say
                which of them it drops. */}
            {(saved || remembered || mismatched) && (
              <Button
                type="button"
                variant="destructive"
                size="sm"
                onClick={() => setConfirmingRemove(true)}
                disabled={busy}
              >
                Remove key
              </Button>
            )}
            <Button type="button" size="sm" onClick={save} disabled={busy || !trimmed || !looksValid}>
              Save
            </Button>
          </>
        }
      >
        <div className="conn-dialog-section">
          <div className="conn-field">
            <Label htmlFor={`provider-${provider.id}`}>API key</Label>
            {/* The toggle sits inside the field rather than beside it. As a
                sibling button it was a second control competing with Save for
                the row, and it pushed the input narrower than the secret it
                holds — an eye inside the box is the convention every password
                field on the web already uses. */}
            <div className="conn-key-input">
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
              <button
                type="button"
                className="conn-reveal"
                onClick={() => setRevealed((shown) => !shown)}
                disabled={!value}
                aria-label={revealed ? "Hide key" : "Show key"}
                aria-pressed={revealed}
                aria-controls={`provider-${provider.id}`}
              >
                {revealed ? <EyeOff size={15} aria-hidden="true" /> : <Eye size={15} aria-hidden="true" />}
              </button>
            </div>
            {/* Everything about the key that is not the key. Its own stack, at
                its own rhythm: at the field's 5px gap these ran together into
                one grey paragraph, and the checkbox — the only control among
                them — read as another line of small print. */}
            <div className="conn-field-notes">
              {trimmed && !looksValid ? (
                <p className="conn-hint">Keys usually start with &ldquo;{provider.prefix}&rdquo;.</p>
              ) : keyStorage !== STORAGE_NONE ? (
                <StorageBadge storage={keyStorage} detail />
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
              {mismatched && (
                <p className="conn-hint conn-hint--alert" role="alert">
                  {tile.detail}
                </p>
              )}
              {remembered && (
                <p className="conn-hint">
                  A saved key is already in use. Paste a new one to replace it, or
                  choose Remove key to forget it.
                </p>
              )}
              {!desktop && (
                <label className="conn-check">
                  <Checkbox
                    checked={remember}
                    onCheckedChange={(next) => setRemember(next === true)}
                    disabled={busy}
                  />
                  <span>Remember this key on Duct</span>
                </label>
              )}
              <p className="conn-hint">
                <a className="app-link" href={provider.consoleUrl} target="_blank" rel="noreferrer">
                  Get a key from {provider.label} &rarr;
                </a>
              </p>
            </div>
          </div>

          {error && (
            <p role="alert" className="conn-hint conn-hint--alert">
              {error}
            </p>
          )}

        </div>

        {/* The other way to pay for this provider. Under the key field, not
            above it: someone who already has a key should not have to read
            past a plan they may not want. */}
        {planOffered && (
          <div className="conn-dialog-section">
            <h3 className="conn-dialog-heading">Or use your ChatGPT plan</h3>
            <p className="conn-hint">
              A ChatGPT Plus or Pro plan runs GPT models with no API key and nothing
              extra to pay. Signing in opens your normal browser; Duct never sees your
              password or your chat history, and the sign-in stays in this
              machine&rsquo;s keychain.
            </p>

            {plan.available ? (
              planConnected ? (
                <div className="conn-account-row">
                  <span className="conn-account-text">
                    Signed in as <b>{plan.status.email || "your ChatGPT account"}</b>
                    {plan.status.plan_type ? ` · ${planLabel(plan.status.plan_type)}` : ""}
                  </span>
                  {/* Disconnect + Reconnect, in that order and those variants,
                      because that is what every OAuth connection in this app
                      offers (`OAuthConnectorCard`). This said "Sign out",
                      which is a third word for the same idea and reads like
                      signing out of Duct itself. Reconnect is how you switch
                      ChatGPT accounts, and how you recover from a token the
                      user revoked at OpenAI. */}
                  <span className="conn-account-actions">
                    <Button
                      type="button"
                      variant="destructive"
                      size="sm"
                      onClick={() => setConfirmingDisconnect(true)}
                      disabled={Boolean(planBusy)}
                    >
                      Disconnect
                    </Button>
                    <Button
                      type="button"
                      variant="secondary"
                      size="sm"
                      onClick={signInPlan}
                      disabled={Boolean(planBusy)}
                    >
                      {signingIn ? "Waiting for your browser\u2026" : "Reconnect"}
                    </Button>
                    {signingIn && (
                      <Button type="button" variant="ghost" size="sm" onClick={cancelPlan}>
                        Cancel
                      </Button>
                    )}
                  </span>
                </div>
              ) : (
                <div className="flex flex-wrap items-center gap-2">
                  <Button type="button" size="sm" onClick={signInPlan} disabled={Boolean(planBusy)}>
                    {signingIn ? "Waiting for your browser\u2026" : "Continue with ChatGPT"}
                  </Button>
                  {/* A closed tab tells the shell nothing, so this is the only
                      way back short of the five-minute timeout. */}
                  {signingIn && (
                    <Button type="button" variant="ghost" size="sm" onClick={cancelPlan}>
                      Cancel
                    </Button>
                  )}
                </div>
              )
            ) : (
              // Not this surface: the OAuth redirect lands on a loopback port,
              // and only a program on the user's machine can be listening.
              <ol className="conn-steps">
                <li>
                  {desktop
                    ? "Update the desktop app \u2014 this version can\u2019t run the sign-in."
                    : "Install the desktop app. Signing in hands the result back to a program on your computer, which a web page cannot receive."}
                </li>
                <li>
                  {/* No "&rarr; Providers" step any more: the page's own name
                      carries the word, and repeating it read as two hops. */}
                  Open <b>Settings &rarr; Models &amp; providers &rarr; OpenAI</b> and choose{" "}
                  <b>Continue with ChatGPT</b>.
                </li>
              </ol>
            )}

            {planError && (
              <p className="conn-hint conn-hint--alert" role="alert">
                {planError}
              </p>
            )}
            <p className="conn-hint">
              {saved
                ? "Your pasted key takes precedence over the plan. "
                : "A key pasted above always wins over the plan. "}
              Scheduled runs happen with no app open, so those still need a key.
            </p>
            {!desktop && (
              <p className="conn-hint">
                <a className="app-link" href={DESKTOP_DOWNLOAD_URL} target="_blank" rel="noreferrer">
                  Get the desktop app &rarr;
                </a>
              </p>
            )}
          </div>
        )}
      </ConnectorDialog>

      {/* Canon: the title quotes the object, the body states scope and
          irreversibility, and the action is verb + noun. */}
      <AlertDialog open={confirmingRemove} onOpenChange={setConfirmingRemove}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Remove your {provider.label} key?</AlertDialogTitle>
            <AlertDialogDescription>
              Duct forgets the key {storageSentence}. Runs that need {provider.label}
              {planConnected
                ? " fall back to your ChatGPT plan."
                : " stop working until you paste a new one."}{" "}
              Duct cannot show you this key again, so make sure you have it
              somewhere else if you still need it.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel type="button">Keep it</AlertDialogCancel>
            <AlertDialogAction
              type="button"
              className={buttonVariants({ variant: "destructive" })}
              onClick={() => {
                setConfirmingRemove(false);
                remove();
              }}
            >
              Remove key
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <AlertDialog open={confirmingDisconnect} onOpenChange={setConfirmingDisconnect}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Disconnect your ChatGPT plan?</AlertDialogTitle>
            <AlertDialogDescription>
              Duct forgets the sign-in held in this machine&rsquo;s keychain, and
              stops running {provider.label} models on your plan. Your ChatGPT
              account is untouched &mdash; reconnecting takes one sign-in. To
              revoke Duct&rsquo;s access at OpenAI as well, do that in your ChatGPT
              settings.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel type="button">Stay connected</AlertDialogCancel>
            <AlertDialogAction
              type="button"
              className={buttonVariants({ variant: "destructive" })}
              onClick={() => {
                setConfirmingDisconnect(false);
                signOutPlan();
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
