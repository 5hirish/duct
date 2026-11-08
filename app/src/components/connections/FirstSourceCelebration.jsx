"use client";

// The first source connected: the one moment on this page worth celebrating.
//
// It is the step that turns Duct from a form into something that reads your
// numbers, and it happens once, which is exactly where delight belongs
// (DESIGN.md north star 5: delight where use is rare). The tesserae are the
// onboarding burst's, so the two arrivals feel like one product, and the card
// ends on the next thing worth doing rather than on congratulations.
//
// Shown once per browser, and only when exactly one source is connected: an
// account that already had several when this shipped is not on its first.

import { useEffect, useState } from "react";
import Link from "next/link";
import { X } from "lucide-react";
import { Trans, useLingui } from "@lingui/react/macro";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import TesseraBurst from "@/components/onboarding/TesseraBurst";
import { CONNECTOR_NAMES, LOGOS } from "./logos";

const SEEN_KEY = "duct_first_source_celebrated";

function seen() {
  try {
    return window.localStorage.getItem(SEEN_KEY) === "1";
  } catch {
    return true; // no storage, no way to show it only once: do not show it
  }
}

function markSeen() {
  try {
    window.localStorage.setItem(SEEN_KEY, "1");
  } catch {
    // Nothing to do: the card simply will not come back after a reload.
  }
}

/** @param connectedTypes connector types connected right now, settled. */
export default function FirstSourceCelebration({ connectedTypes, ready }) {
  const { t, i18n } = useLingui();
  const [type, setType] = useState("");
  const [burst, setBurst] = useState(true);

  useEffect(() => {
    if (!ready || type || seen()) return;
    if (connectedTypes.length === 1) setType(connectedTypes[0]);
    if (connectedTypes.length >= 1) markSeen();
  }, [ready, type, connectedTypes]);

  if (!type) return null;
  const name = CONNECTOR_NAMES[type] ? i18n._(CONNECTOR_NAMES[type]) : type;

  return (
    <Card variant="hero" size="lg" className="relative gap-5 overflow-visible pr-14 @xl:flex-row @xl:items-center" role="status">
      {burst && <TesseraBurst onDone={() => setBurst(false)} />}
      <span
        className="flex size-12 shrink-0 items-center justify-center rounded-xl border bg-background [&_img]:size-7 [&_svg]:size-7"
        aria-hidden
      >
        {LOGOS[type]}
      </span>
      <div className="flex min-w-0 flex-1 flex-col gap-1">
        <p className="text-sm font-semibold">
          <Trans>{name} is connected.</Trans>
        </p>
        <p className="text-sm text-muted-foreground">
          <Trans>Duct is reading it now. Ask your first question while it does.</Trans>
        </p>
      </div>
      <Button asChild className="shrink-0 self-start @xl:self-center">
        <Link href="/insights/organic-growth">
          <Trans>Ask a question</Trans>
        </Link>
      </Button>
      <Button
        type="button"
        variant="ghost"
        size="icon-sm"
        className="absolute right-3 top-3 text-muted-foreground"
        aria-label={t`Dismiss`}
        onClick={() => setType("")}
      >
        <X />
      </Button>
    </Card>
  );
}
