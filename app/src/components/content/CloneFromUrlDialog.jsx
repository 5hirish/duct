"use client";

import { useState } from "react";
import { msg } from "@lingui/core/macro";
import { Trans, useLingui } from "@lingui/react/macro";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { TikTokUrlError, parseTikTokPostUrl } from "@/lib/tiktokUrl";

// What to do about each way a paste is not a post link. The check itself is
// lib/tiktokUrl.js; the server makes the same call again.
const ERROR_COPY = {
  [TikTokUrlError.EMPTY]:      msg`Paste the link to one TikTok post.`,
  [TikTokUrlError.NOT_A_LINK]: msg`That doesn't look like a link.`,
  [TikTokUrlError.NOT_TIKTOK]: msg`That link isn't on tiktok.com.`,
  [TikTokUrlError.SHARE_LINK]: msg`That's a share link. Open it, then copy the full address from your browser.`,
  [TikTokUrlError.NOT_A_POST]: msg`That link isn't a single post. It should look like tiktok.com/@creator/video/123…`,
};

/**
 * Paste a TikTok that worked; get a carousel for this brand modelled on it.
 *
 * Presentational: validates the paste and hands the canonical URL to
 * `onClone`, which navigates to the drafting workspace. Nothing is fetched
 * here — the scrape, the reading and the draft all happen in that session.
 *
 * Props: `open`, `onOpenChange`, `onClone(url)`, and `initialValue` for a
 * prefilled link (/preview uses it: it has no clipboard to paste from).
 */
export default function CloneFromUrlDialog({ open, onOpenChange, onClone, initialValue = "" }) {
  const { t, i18n } = useLingui();
  const [value, setValue] = useState(initialValue);
  // A prefilled value is checked up front: whoever filled it is not the
  // person who will be surprised by the error after pressing the button.
  const [error, setError] = useState(() => (initialValue ? parseTikTokPostUrl(initialValue).error || null : null));

  function handleSubmit(event) {
    event.preventDefault();
    const parsed = parseTikTokPostUrl(value);
    if (parsed.error) {
      setError(parsed.error);
      return;
    }
    onClone?.(parsed.url);
  }

  function handleOpenChange(next) {
    if (!next) setError(null);
    onOpenChange?.(next);
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent>
        <form onSubmit={handleSubmit} className="flex flex-col gap-5" noValidate>
          <DialogHeader>
            <DialogTitle><Trans>Clone a TikTok</Trans></DialogTitle>
            <DialogDescription>
              <Trans>
                Paste a post that worked. Duct reads why it worked, then drafts a carousel for your
                brand on the same structure, and tells you what it kept.
              </Trans>
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-1.5">
            <Label htmlFor="clone-url"><Trans>TikTok link</Trans></Label>
            <Input
              id="clone-url"
              type="url"
              inputMode="url"
              autoComplete="off"
              spellCheck={false}
              autoFocus
              value={value}
              onChange={(e) => { setValue(e.target.value); setError(null); }}
              placeholder={t`https://www.tiktok.com/@creator/video/…`}
              aria-invalid={error ? true : undefined}
              aria-describedby={error ? "clone-url-error" : "clone-url-hint"}
            />
            {error ? (
              <p id="clone-url-error" role="alert" className="text-xs text-destructive">
                {i18n._(ERROR_COPY[error])}
              </p>
            ) : (
              <p id="clone-url-hint" className="text-xs text-muted-foreground">
                <Trans>Photo carousels and videos both work. The clone is always a carousel.</Trans>
              </p>
            )}
          </div>

          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => handleOpenChange(false)}>
              <Trans>Cancel</Trans>
            </Button>
            <Button type="submit"><Trans>Draft a clone</Trans></Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
