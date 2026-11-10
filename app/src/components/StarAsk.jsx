"use client";

// "Is Duct earning its keep?" The GitHub star ask (#539), the way iOS asks
// for an App Store rating: after something went well, in the corner, rarely.
//
// The rules (which moment, how often, how long between) are lib/starAsk.js,
// plain functions with a test per rule. This file is the words and the wait:
// a run that made something ends, the ask waits SETTLE_MS so the person reads
// the first lines of it, then shows if nothing forbids it. A run starting in
// that window cancels it. If the card would cover the message box (a phone,
// or a workspace in one pane), it waits for the next page instead of giving
// up; anything else that blocks it drops the moment, and the next good run
// brings another.
//
// It is the one notice that asks rather than tells, so it yields: never shown
// while another notice holds the corner, and it steps aside if one arrives
// (ui/corner-notice.jsx has the rule). Three things it never does, each by
// construction rather than by restraint: route unhappy people away from the
// star (both the star and "Something missing?" are on every showing), reward a
// star (GitHub's terms forbid it), or show a star count (not until the count
// is social proof).

import { useCallback, useEffect, useRef, useState } from "react";
import { usePathname } from "next/navigation";
import { Star } from "lucide-react";
import { Trans, useLingui } from "@lingui/react/macro";
import { Button } from "@/components/ui/button";
import { CornerNotice, isCornerTaken, useCornerTaken } from "@/components/ui/corner-notice";
import { AnalyticsEvent, AnalyticsParam, trackEvent } from "@/lib/analytics";
import { REPO_URL, SUGGEST_IDEA_URL } from "@/lib/feedbackLinks";
import { listDetachedRuns } from "@/lib/liveRuns";
import {
  RUN_EVENT,
  RunMoment,
  SETTLE_MS,
  THANKS_MS,
  askBlocker,
  boxesOverlap,
  isTransient,
  noteDismissed,
  noteFirstSeen,
  noteShown,
  noteStarred,
  noticeBox,
  readStarAsk,
} from "@/lib/starAsk";

/** What the corner shows. */
export const StarAskView = Object.freeze({ ASK: "ask", THANKS: "thanks" });

/** Where a star came from, as the `method` on `star_ask_starred`. */
export const StarFrom = Object.freeze({ NOTICE: "notice", MENU: "menu" });

const DismissedBy = Object.freeze({ NOT_NOW: "not_now", CLOSE: "close" });

// After a route change the next page's message box is not in the DOM on the
// first frame; a workspace mounts its composer once its session hook runs.
const ROUTE_SETTLE_MS = 600;

/**
 * Someone went to star Duct: from the notice, or the account menu's
 * permanent row. Either way the notice never asks them again.
 */
export function recordStar(from) {
  noteStarred();
  trackEvent(AnalyticsEvent.StarAskStarred, { [AnalyticsParam.Method]: from });
}

/** Would the card sit over a message box on screen right now. */
function coversComposer() {
  if (typeof document === "undefined") return false;
  const remPx = parseFloat(getComputedStyle(document.documentElement).fontSize) || 16;
  const box = noticeBox({ width: window.innerWidth, height: window.innerHeight }, remPx);
  return Array.from(document.querySelectorAll("[data-composer]")).some((el) => {
    const rect = el.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0 && boxesOverlap(box, rect);
  });
}

/**
 * The card, given a view rather than deciding one, so `/preview` can show
 * both states without the rules.
 */
export function StarAskNotice({ view = StarAskView.ASK, onStar, onNotNow, onClose }) {
  const { t } = useLingui();

  if (view === StarAskView.THANKS) {
    return (
      <CornerNotice
        yields
        icon={Star}
        // The star the person just gave, filled, in the one accent: the
        // whole celebration, once, and gone under reduced motion.
        iconClassName="fill-current text-brand animate-in zoom-in-50 duration-300"
        title={t`Thank you`}
        onDismiss={onClose}
        dismissLabel={t`Close`}
      >
        <p className="mt-0.5 text-xs text-muted-foreground">
          {/* Thanks for the gesture, not a claim about GitHub: nothing here
              knows whether a star was given. */}
          <Trans>Every star helps the next team find Duct.</Trans>
        </p>
      </CornerNotice>
    );
  }

  return (
    <CornerNotice
      yields
      icon={Star}
      title={t`Is Duct earning its keep?`}
      onDismiss={onClose}
      dismissLabel={t`Dismiss the star request`}
      actions={
        <>
          {/* Side by side at equal width while both fit, one under the other
              when a language makes them too long: the rule iOS lays out an
              alert's two actions by, so German stacks deliberately rather than
              leaving Not now stranded under a ragged edge.
              A plain new-tab link: installExternalLinkHandler (lib/shell.js)
              sends target="_blank" to the system browser in the desktop shell. */}
          <Button size="sm" className="flex-1" asChild>
            <a href={REPO_URL} target="_blank" rel="noreferrer noopener" onClick={onStar}>
              <Trans>Star on GitHub</Trans>
            </a>
          </Button>
          <Button size="sm" variant="ghost" className="flex-1" onClick={onNotNow}>
            <Trans>Not now</Trans>
          </Button>
        </>
      }
      footer={
        // The other answer, offered to everyone at the same time as the star,
        // so a person who is not happy is heard rather than routed away.
        <a
          href={SUGGEST_IDEA_URL}
          target="_blank"
          rel="noreferrer noopener"
          className="-my-1 inline-block rounded py-1 text-xs text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <Trans>
            Something missing? <span className="underline underline-offset-2">Tell us</span>
          </Trans>
        </a>
      }
    >
      <p className="mt-0.5 text-xs text-muted-foreground">
        <Trans>If it’s saved you time, a star on GitHub helps the next team find it.</Trans>
      </p>
    </CornerNotice>
  );
}

export default function StarAsk() {
  const pathname = usePathname();
  const taken = useCornerTaken();
  const [view, setView] = useState(null);
  const viewRef = useRef(null);
  viewRef.current = view;
  // A good run ended and the ask has not been decided yet.
  const pending = useRef(false);
  const settle = useRef(0);

  useEffect(() => {
    noteFirstSeen();
  }, []);

  const tryAsk = useCallback(() => {
    if (!pending.current) return;
    // Nobody is looking: the visibility listener tries again on return,
    // which is when someone comes back to read what the run made.
    if (document.visibilityState === "hidden") return;
    const block = askBlocker(readStarAsk(), {
      now: Date.now(),
      live: listDetachedRuns().length > 0,
      cornerTaken: isCornerTaken(),
      coversComposer: coversComposer(),
    });
    if (block) {
      if (!isTransient(block)) pending.current = false;
      return;
    }
    pending.current = false;
    if (!noteShown()) return;
    trackEvent(AnalyticsEvent.StarAskShown);
    setView(StarAskView.ASK);
  }, []);

  useEffect(() => {
    function onRun(event) {
      const moment = event.detail?.moment;
      if (moment === RunMoment.WON) {
        pending.current = true;
        clearTimeout(settle.current);
        settle.current = setTimeout(tryAsk, SETTLE_MS);
      } else if (moment === RunMoment.STARTED) {
        pending.current = false;
        clearTimeout(settle.current);
      }
    }
    function onVisible() {
      if (document.visibilityState === "visible") tryAsk();
    }
    window.addEventListener(RUN_EVENT, onRun);
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      window.removeEventListener(RUN_EVENT, onRun);
      document.removeEventListener("visibilitychange", onVisible);
      clearTimeout(settle.current);
    };
  }, [tryAsk]);

  // A new page: an ask that was waiting for the message box to go away tries
  // again, and one already showing steps aside rather than follow someone
  // into a workspace and sit on its box.
  useEffect(() => {
    const timer = setTimeout(() => {
      if (viewRef.current === StarAskView.ASK && coversComposer()) setView(null);
      else tryAsk();
    }, ROUTE_SETTLE_MS);
    return () => clearTimeout(timer);
  }, [pathname, tryAsk]);

  // The thank-you counts down only while the person is in this window. The
  // star opens GitHub in front of it, and a thank-you that expired behind the
  // browser was said to nobody.
  useEffect(() => {
    if (view !== StarAskView.THANKS) return undefined;
    let timer = 0;
    const arm = () => {
      clearTimeout(timer);
      timer = setTimeout(() => setView(null), THANKS_MS);
    };
    const hold = () => clearTimeout(timer);
    window.addEventListener("focus", arm);
    window.addEventListener("blur", hold);
    if (document.hasFocus()) arm();
    return () => {
      clearTimeout(timer);
      window.removeEventListener("focus", arm);
      window.removeEventListener("blur", hold);
    };
  }, [view]);

  const onStar = useCallback(() => {
    recordStar(StarFrom.NOTICE);
    // After the click has finished with the link: swapping the card now
    // would take the anchor out of the page before the desktop shell's
    // document-level handler reads it (installExternalLinkHandler).
    setTimeout(() => setView(StarAskView.THANKS), 0);
  }, []);

  const dismissWith = useCallback((how) => {
    noteDismissed();
    trackEvent(AnalyticsEvent.StarAskDismissed, { [AnalyticsParam.Method]: how });
    setView(null);
  }, []);

  if (!view || taken) return null;

  return (
    <StarAskNotice
      view={view}
      onStar={onStar}
      onNotNow={() => dismissWith(DismissedBy.NOT_NOW)}
      onClose={view === StarAskView.THANKS ? () => setView(null) : () => dismissWith(DismissedBy.CLOSE)}
    />
  );
}
