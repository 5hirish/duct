"use client";

import { ArrowRight, Globe } from "lucide-react";
import MosaicPanel, { MOSAIC } from "@/components/MosaicPanel";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

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
 * What carries the continuity instead is the ground and the art — the same
 * travertine `--start-ground`, and a mosaic panel one step upstream of the one
 * `/start` opens with. `FONS` is the spring; `SALVE` greets you once you are
 * through the door.
 */
export default function FrontDoor({ url, onUrlChange, error, onSubmit }) {
  return (
    <div className="landing-start-inner">
      <div className="landing-start-copy">
        <div className="signin-logo">
          <span className="signin-logo-text">duct</span>
          <span className="logo-mark" aria-hidden="true" />
        </div>

        <h1 className="landing-start-headline">
          Your site has a problem list.
          <em>Duct finds it in about three minutes.</em>
        </h1>

        <p className="landing-start-sub">
          Type your address &mdash; that&rsquo;s the whole setup. Duct reads your
          site the way a search engine does, then tells you what to fix first.
        </p>

        <form onSubmit={onSubmit} className="landing-start-form">
          <Label htmlFor="landing-site-url" className="sr-only">
            Your website
          </Label>
          <div className="start-url">
            <Globe className="start-url-icon size-4" aria-hidden />
            <Input
              id="landing-site-url"
              inputMode="url"
              autoComplete="url"
              placeholder="acme.com"
              value={url}
              onChange={(e) => onUrlChange(e.target.value)}
              aria-invalid={error ? true : undefined}
              aria-describedby={error ? "landing-site-url-error" : "landing-site-url-hint"}
              className="start-url-input"
            />
          </div>
          <Button type="submit" size="lg">
            Audit my site <ArrowRight className="size-4" aria-hidden />
          </Button>
        </form>

        <p
          id={error ? "landing-site-url-error" : "landing-site-url-hint"}
          className={`landing-start-hint${error ? " landing-start-hint-error" : ""}`}
          role={error ? "alert" : undefined}
        >
          {error || "Free, no account, and nothing else connected."}
        </p>

        <p className="landing-connect">
          When you&rsquo;re ready, Duct connects Google Ads, GA4, Search Console
          and Meta Ads &mdash; read-only, and only the ones you pick.
        </p>
      </div>

      {/* Last in the DOM so a phone gets the field before the picture, and
          placed into the second column by the grid on a wide screen. */}
      <MosaicPanel name={MOSAIC.fons} size={280} className="landing-mosaic" />
    </div>
  );
}
