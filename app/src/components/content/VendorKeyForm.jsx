"use client";

import { useId, useState } from "react";
import { ExternalLink, KeyRound, Users } from "lucide-react";
import { Trans, useLingui } from "@lingui/react/macro";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Spinner } from "@/components/ui/spinner";
import { cn } from "@/lib/utils";

/**
 * Connecting a vendor Duct uses through the user's own account — PostBridge
 * to publish, Apify to search TikTok. Hosted Duct never spends a key of its
 * own on someone's request, so the first step is theirs: the API key.
 *
 * A project uses its owner's key, so anyone else is told who connects it
 * rather than offered a form whose key would never be used here.
 *
 * `vendor` is the display name; `description` says what Duct does with the
 * account (a <Trans> from the caller, since it differs per vendor);
 * `onConnect(apiKey)` saves and resolves once the vendor accepted the key, and
 * a rejection's message is shown under the field.
 *
 * `layout`:
 *   - "card"   : the whole surface — a tab that has nothing to show until the
 *                key is in (Accounts, Discover). Carries its own heading.
 *   - "inline" : the field alone, for a row that already says what the
 *                vendor is for (the Plan tab's checklist). No heading, no
 *                description; the caller's row is both.
 */
export default function VendorKeyForm({ vendor, homeUrl, description, isOwner = true, onConnect, layout = "card" }) {
  const inline = layout === "inline";

  if (!isOwner) {
    return inline ? (
      <p className="text-xs leading-relaxed text-muted-foreground">
        <Trans>This project uses its owner&apos;s {vendor} account. Ask them to connect it.</Trans>
      </p>
    ) : (
      <Card icon={Users}>
        <h3 className="text-sm font-semibold"><Trans>{vendor} isn&apos;t set up yet</Trans></h3>
        <p className="mt-1 text-sm text-muted-foreground">
          <Trans>
            This project uses its owner&apos;s {vendor} account. Ask them to connect it here, and
            it will work for you too.
          </Trans>
        </p>
      </Card>
    );
  }

  if (inline) {
    return (
      <div className="space-y-1.5">
        <KeyField vendor={vendor} onConnect={onConnect} compact />
        <p className="text-2xs text-muted-foreground">
          <a href={homeUrl} target="_blank" rel="noreferrer" className="inline-flex items-center gap-0.5 underline-offset-2 hover:text-foreground hover:underline">
            <Trans>Get your key from {vendor}</Trans>
            <ExternalLink className="size-2.5" aria-hidden />
          </a>
          <span aria-hidden> · </span>
          <Trans>Stored encrypted.</Trans>
        </p>
      </div>
    );
  }

  return (
    <Card icon={KeyRound}>
      <h3 className="text-sm font-semibold"><Trans>Connect your {vendor} account</Trans></h3>
      <p className="mt-1 text-sm text-muted-foreground">{description}</p>
      <div className="mt-4">
        <KeyField vendor={vendor} onConnect={onConnect} />
      </div>
      <div className="mt-4 flex flex-col items-center gap-1">
        <Button variant="link" size="sm" className="h-auto p-0" asChild>
          <a href={homeUrl} target="_blank" rel="noreferrer">
            <Trans>Open {vendor}</Trans>
            <ExternalLink className="size-3.5" aria-hidden />
          </a>
        </Button>
        <p className="text-xs text-muted-foreground">
          <Trans>Stored encrypted, and used only for projects you own.</Trans>
        </p>
      </div>
    </Card>
  );
}

// The field, the button and the vendor's refusal: the part both layouts
// share, so a key is checked and an error is announced the same way in each.
function KeyField({ vendor, onConnect, compact = false }) {
  const { t } = useLingui();
  const [key, setKey] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const errorId = useId();

  async function submit(e) {
    e.preventDefault();
    const value = key.trim();
    if (!value || saving) return;
    setSaving(true);
    setError("");
    try {
      await onConnect(value);
    } catch (err) {
      setError(err?.message || t`That didn't connect. Check the key and try again.`);
      setSaving(false);
    }
  }

  return (
    <>
      <form onSubmit={submit} className={cn("flex gap-2 text-left", compact ? "flex-row" : "flex-col @md:flex-row")}>
        <Input
          type="password"
          autoComplete="off"
          spellCheck={false}
          value={key}
          onChange={(e) => setKey(e.target.value)}
          placeholder={t`Paste your API key`}
          aria-label={t`${vendor} API key`}
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? errorId : undefined}
          className={cn("min-w-0 flex-1", compact && "h-8")}
        />
        {/* Inline, the field sits under the page's own primary action, so it
            stays a secondary button rather than a second call to act. */}
        <Button type="submit" size={compact ? "sm" : "default"} variant={compact ? "secondary" : "default"} disabled={!key.trim() || saving}>
          {saving && <Spinner className="size-4" />}
          <Trans>Connect</Trans>
        </Button>
      </form>
      {error && (
        <p id={errorId} role="alert" className="mt-2 text-left text-xs text-destructive">
          {error}
        </p>
      )}
    </>
  );
}

function Card({ icon: Icon, children }) {
  return (
    <div className="mx-auto max-w-md rounded-2xl border border-dashed border-border/70 p-8 text-center">
      <div className="mx-auto mb-4 flex size-12 items-center justify-center rounded-full bg-muted text-muted-foreground">
        <Icon className="size-5" aria-hidden />
      </div>
      {children}
    </div>
  );
}
