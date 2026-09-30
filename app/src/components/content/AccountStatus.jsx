"use client";

import { Trans } from "@lingui/react/macro";
import { Badge } from "@/components/ui/badge";

// Where an account's owner fixes a paused login. PostBridge has no deep link
// to one account, so this opens its dashboard.
export const POSTBRIDGE_DASHBOARD_URL = "https://app.post-bridge.com";

/**
 * What PostBridge says about one social account, as badges: X Premium (the
 * 25,000-character limit) and a paused login. PostBridge skips every post to
 * a paused account without failing it, so a publish there would say "done"
 * and put nothing on the feed; the badge says so before anyone tries.
 */
export function AccountBadges({ account }) {
  if (!account?.needs_reconnect && !account?.has_x_premium) return null;
  return (
    <span className="inline-flex flex-wrap items-center gap-1">
      {account.has_x_premium && (
        <Badge variant="secondary" className="px-1.5 py-0 text-2xs font-normal">
          <Trans>X Premium</Trans>
        </Badge>
      )}
      {account.needs_reconnect && (
        <Badge variant="warning" className="px-1.5 py-0 text-2xs font-normal">
          <Trans>Needs reconnecting</Trans>
        </Badge>
      )}
    </span>
  );
}

/** The line under a paused account: why nothing will post, and where to fix it. */
export function ReconnectNote({ account }) {
  if (!account?.needs_reconnect) return null;
  return (
    <p className="text-2xs text-muted-foreground">
      <Trans>
        Its login stopped working, so posts to it are skipped.{" "}
        <a
          href={POSTBRIDGE_DASHBOARD_URL}
          target="_blank"
          rel="noreferrer"
          className="font-medium text-foreground underline underline-offset-2"
        >
          Reconnect it in PostBridge
        </a>
      </Trans>
    </p>
  );
}
