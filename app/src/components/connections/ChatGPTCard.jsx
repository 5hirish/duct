"use client";

// The user's ChatGPT plan as a model provider — the tile beside the API keys.
//
// Desktop only, and only when the shell can run the sign-in and the backend
// allows the path. It renders nothing otherwise rather than a disabled tile:
// a control that explains why it cannot be used is still a control the page
// has to fit, and in a browser there is nothing the user could do about it.
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

  if (!available || !enabled) return null;

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
