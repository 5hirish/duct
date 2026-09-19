"use client";

// Usage — what Duct spent on your provider key.
//
// Under bring-your-own-key every figure here is a charge on the user's own
// account, which is why this exists at all: Duct was computing the number per
// model call and throwing it away, so the one person actually paying could not
// see it.
//
// The view itself is `components/models/UsagePanel`, shared with the Usage tab
// on Models & providers. This route is the sidebar's destination and supplies
// the heading; the tab supplies its own. Nothing renders twice — there is one
// implementation, and the tab reads the same six-field shape this does.

import { Gauge } from "lucide-react";
import { Trans } from "@lingui/react/macro";
import UsagePanel from "@/components/models/UsagePanel";

export default function UsagePage() {
  return (
    <>
      <h1 className="app-title">
        <Gauge size={20} strokeWidth={1.75} aria-hidden="true" />
        <Trans>Usage</Trans>
      </h1>
      <UsagePanel standalone />
    </>
  );
}
