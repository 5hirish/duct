"use client";

// The user's ChatGPT plan as a model provider — the tile beside the API keys.
//
// The sign-in is desktop-only for a structural reason, not a missing feature:
// OpenAI's flow redirects to `http://localhost:1455/auth/callback`, and only a
// process on the user's machine can be listening there. A web page cannot
// complete it however much we want it to.
//
// This used to render nothing at all in a browser, reasoning that a control
// you cannot use is still a control the page has to fit. That was wrong about
// which question the tile answers. "Can I run Duct on the ChatGPT plan I
// already pay for?" is a *purchasing* question, and the page answered it by
// showing nothing — so the honest answer ("yes, in the desktop app") was
// indistinguishable from "no, Duct can't do that". The unavailable state below
// is not a disabled button; it is the answer, plus the one link that acts on
// it.
//
// `enabled` is still a hard off switch. That one is the backend saying the
// path is broken for everybody (the Codex endpoint is undocumented and can
// change without notice), and there is no version of that worth advertising.
//
// What the tile can say is exactly what the shell tells it — connected, plan,
// email — and never a token. Signing out forgets the keychain bundle; the app
// registration at OpenAI stays theirs to revoke.

import { useEffect, useState } from "react";
import { LogOut } from "lucide-react";
import { Button } from "@/components/ui/button";
import { STORAGE_KEYCHAIN, STORAGE_NONE } from "../../lib/credentialStorage";
import { chatgptAuthAvailable, chatgptLogin, chatgptLogout, chatgptStatus } from "../../lib/chatgpt";
import { OpenAiMark } from "./logos";
import ConnectorDialog from "./ConnectorDialog";
import ConnectorTile from "./ConnectorTile";

const PLAN_LABELS = { plus: "ChatGPT Plus", pro: "ChatGPT Pro", team: "ChatGPT Team", free: "ChatGPT Free" };

const DOWNLOAD_URL = "https://getduct.ai/download";

// Said the same way in the tile and in the dialog, because they are the same
// sentence at two lengths and a reader who opens the dialog is checking they
// read the tile right.
const DESKTOP_ONLY = "Signing in opens your browser and hands the result back to Duct on this computer, so it needs the desktop app.";

export function planLabel(planType) {
  return PLAN_LABELS[String(planType || "").toLowerCase()] || (planType ? `ChatGPT ${planType}` : "ChatGPT");
}

export default function ChatGPTCard({ enabled = true }) {
  const [available, setAvailable] = useState(false);
  const [status, setStatus] = useState({ connected: false });
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let alive = true;
    chatgptAuthAvailable().then(async (ok) => {
      if (!alive) return;
      setAvailable(ok);
      if (ok) setStatus(await chatgptStatus());
    });
    return () => {
      alive = false;
    };
  }, []);

  if (!enabled) return null;

  // In a browser: what the plan is worth, why it is not here, and the way to
  // get it. Deliberately `tone="off"` and not `disabled` — the tile is live,
  // it just leads to the download rather than to a sign-in.
  if (!available) {
    return (
      <>
        <ConnectorTile
          logo={OpenAiMark}
          title="ChatGPT plan"
          description="Run GPT models on the ChatGPT plan you already pay for. No API key, no extra bill."
          tone="off"
          status="In the desktop app"
          storage={STORAGE_NONE}
          onClick={() => setOpen(true)}
        />
        <ConnectorDialog
          open={open}
          onOpenChange={setOpen}
          logo={OpenAiMark}
          title="ChatGPT plan"
          description={DESKTOP_ONLY}
          footer={
            <Button type="button" size="sm" asChild>
              <a href={DOWNLOAD_URL} target="_blank" rel="noreferrer">
                Get the desktop app
              </a>
            </Button>
          }
        >
          <div className="grid gap-3">
            <p className="text-sm">
              A ChatGPT Plus or Pro plan can run most of what Duct does, with no API key and
              nothing extra to pay. The sign-in stays in your OS keychain on that machine.
            </p>
            <p className="text-sm text-muted-foreground">
              You can keep using an API key here either way — and you&rsquo;ll still want one for
              scheduled runs, which happen with no app open and so cannot use a plan.
            </p>
          </div>
        </ConnectorDialog>
      </>
    );
  }

  async function signIn() {
    setBusy(true);
    setError("");
    try {
      setStatus(await chatgptLogin());
    } catch (err) {
      setError(String(err?.message || err));
    } finally {
      setBusy(false);
    }
  }

  async function signOut() {
    setBusy(true);
    setError("");
    try {
      await chatgptLogout();
      setStatus({ connected: false });
    } catch (err) {
      setError(String(err?.message || err));
    } finally {
      setBusy(false);
    }
  }

  const who = status.email ? ` — ${status.email}` : "";

  return (
    <>
      <ConnectorTile
        logo={OpenAiMark}
        title="ChatGPT plan"
        description="Run GPT models on the ChatGPT plan you already pay for. No API key, no extra bill."
        tone={status.connected ? "on" : "off"}
        status={status.connected ? `${planLabel(status.plan_type)}${who}` : "Not signed in"}
        storage={status.connected ? STORAGE_KEYCHAIN : STORAGE_NONE}
        onClick={() => setOpen(true)}
      />
      <ConnectorDialog
        open={open}
        onOpenChange={setOpen}
        logo={OpenAiMark}
        title="ChatGPT plan"
        description="Signs in through your browser. Duct keeps the sign-in in your OS keychain and sends a one-hour token with each request — it never sees your ChatGPT password or history, and a pasted OpenAI API key always takes precedence."
      >
        <div className="grid gap-4">
          {status.connected ? (
            <p className="text-sm">
              Signed in as <span className="font-medium">{status.email || "your ChatGPT account"}</span>
              {status.plan_type ? ` on ${planLabel(status.plan_type)}` : ""}.
            </p>
          ) : (
            <p className="text-sm text-muted-foreground">
              Scheduled runs — a nightly check, memory consolidation — happen without the app open and
              cannot use a plan; they still need an API key.
            </p>
          )}
          {error && (
            <p className="text-sm text-destructive" role="alert">
              {error}
            </p>
          )}
          <div className="flex flex-wrap items-center gap-2">
            {status.connected ? (
              <Button type="button" variant="outline" onClick={signOut} disabled={busy}>
                <LogOut className="size-4" /> Sign out
              </Button>
            ) : (
              <Button type="button" onClick={signIn} disabled={busy}>
                {busy ? "Waiting for your browser…" : "Continue with ChatGPT"}
              </Button>
            )}
          </div>
        </div>
      </ConnectorDialog>
    </>
  );
}
