"use client";

import { ArrowRight, Globe } from "lucide-react";
import { Trans, useLingui } from "@lingui/react/macro";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

// The wordmark is a name, not copy: the literal-string check lets "Duct"
// through by name and this is the same word set in the logo's lowercase.
const WORDMARK = "duct";

/**
 * The signed-out page's wide half: the offer, the one field, and nothing else.
 *
 * Its whole job is to get an address typed, so everything that is not that is
 * either cut or pushed below it. Two things were cut on purpose and should not
 * come back without a better reason than "it is true":
 *
 * The **connector pills** ("Reads from Google Ads · GA4 · Search Console · Meta
 * Ads") sat directly under the field, which put a list of ad and analytics
 * accounts between a stranger and their first click. Read in order it does not
 * say "Duct is well connected", it says *give me a URL and I will read your
 * accounts* — and it is not even what this step does, which is fetch one public
 * web page. It survives below the fold as a sentence with a "when you're ready"
 * clause, which is where it is both reassuring and true.
 *
 * The **aqueduct strip**, rendered dry with all three steps ahead, was a
 * progress bar with no progress: a landing page that opens by showing three
 * chores. `/start` still has it, where the water actually moves, and holding it
 * back until then makes the hand-off a reveal rather than a repeat.
 *
 * What carries the continuity instead is the ground — the same travertine
 * `--start-ground`, so submitting the field does not change the floor under
 * the visitor.
 *
 * The `FONS` mosaic used to sit in this half, in a second grid column. It is
 * in the sign-in panel now, because a 280px picture beside the copy only fits
 * above 1280px and the rule that hid it below that blanked it for the whole
 * width band the desktop window lives in — a 1200px default and a 900px
 * minimum, so the desktop app never once showed it. The navy half has room at
 * every width. `FONS` is the spring; `SALVE` greets you once you are through
 * the door at `/start`.
 */
export default function FrontDoor({ url, onUrlChange, error, onSubmit }) {
  const { t } = useLingui();
  return (
    <div className="landing-start-inner">
      <div className="landing-start-copy">
        <div className="signin-logo">
          <span className="signin-logo-text">{WORDMARK}</span>
          <span className="logo-mark" aria-hidden="true" />
        </div>

        <h1 className="landing-start-headline">
          <Trans>
            Your site has a problem list.
            <em>Duct finds it in about three minutes.</em>
          </Trans>
        </h1>

        {/* One line. It was two sentences over two lines, the first narrating
            the field directly below it ("Type your address — that's the whole
            setup") and the second re-promising what the headline already
            promises. What is left is the only thing here the headline does not
            say: *how*. Copy that describes a visible control is believed less
            than the control and costs a line of the thing it points at. */}
        <p className="landing-start-sub">
          <Trans>Duct reads it the way a search engine does.</Trans>
        </p>

        <form onSubmit={onSubmit} className="landing-start-form">
          <Label htmlFor="landing-site-url" className="sr-only">
            <Trans>Your website</Trans>
          </Label>
          <div className="start-url">
            <Globe className="start-url-icon size-4" aria-hidden />
            <Input
              id="landing-site-url"
              inputMode="url"
              autoComplete="url"
              placeholder={t`acme.com`}
              value={url}
              onChange={(e) => onUrlChange(e.target.value)}
              aria-invalid={error ? true : undefined}
              aria-describedby={error ? "landing-site-url-error" : "landing-site-url-hint"}
              className="start-url-input"
            />
          </div>
          <Button type="submit" size="lg">
            <Trans>Audit my site</Trans> <ArrowRight className="size-4" aria-hidden />
          </Button>
        </form>

        <p
          id={error ? "landing-site-url-error" : "landing-site-url-hint"}
          className={`landing-start-hint${error ? " landing-start-hint-error" : ""}`}
          role={error ? "alert" : undefined}
        >
          {error || t`Free, and no account needed.`}
        </p>

        <p className="landing-connect">
          <Trans>
            Google Ads, GA4, Search Console and Meta Ads connect later &mdash;
            read-only, only the ones you pick.
          </Trans>
        </p>
      </div>

    </div>
  );
}
