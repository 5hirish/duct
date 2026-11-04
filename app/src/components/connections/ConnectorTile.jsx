"use client";

// The one card shape on the Connections page, built on `ui/card`.
//
// Logo, name, one line of what it's for, and its live state. Setup happens in a
// dialog (`ConnectorDialog`), never inline, so the grid stays scannable no
// matter how many fields a connector needs.
//
// The card is a container, not a button: the storage glyph in the footer is a
// tooltip trigger (itself a button), and a button cannot hold a button. The
// title is the button and stretches over the card (`cardLinkClass`), so there
// is one tab stop with a readable name and the footer's own controls sit above
// it. The footer is the Card's, pinned to the bottom, so the state lines of a
// row of tiles share one baseline however long each description runs.
//
// `featured` is the large tile for the few sources worth connecting first: it
// says what the source will let Duct answer (`benefit`) and shows the action
// as a real button, because on day one the action is the point of the tile.

import { ChevronRight } from "lucide-react";
import { Trans, useLingui } from "@lingui/react/macro";
import { Button } from "@/components/ui/button";
import { Card, CardFooter, cardLinkClass } from "@/components/ui/card";
import { ConnectorKind } from "@/lib/connectorSource";
import { cn } from "@/lib/utils";
import ConnectorDot from "./ConnectorDot";
import StorageBadge from "./StorageBadge";

/**
 * @param tag  Optional short capability label beside the title ("Works with
 *   ChatGPT"). A fact about what the tile accepts, not a state.
 * @param source  `{ kind, publisher }` (lib/connectorSource.js). Only an MCP
 *   source is labelled: native is the default, and a "Native" badge on fourteen
 *   of fifteen tiles told nobody anything.
 * @param tone  "on" | "info" | "partial" | "off" — the status dot's colour.
 * @param status  Short state line, e.g. "Connected".
 * @param storage  STORAGE_* constant — where the credential lives.
 * @param featured  Large tile with `benefit` and a visible Connect button.
 */
export default function ConnectorTile({
  logo,
  title,
  description,
  benefit,
  tag,
  source,
  tone = "off",
  status,
  storage,
  onClick,
  disabled = false,
  featured = false,
}) {
  const { t } = useLingui();
  const mcp = source?.kind === ConnectorKind.MCP;
  // "Notion  MCP · Notion" says the name twice; the publisher is worth a word
  // only when it is not the product (a vendor's server for someone else's).
  const publisher =
    source?.publisher && source.publisher.toLowerCase() !== String(title || "").toLowerCase() ? source.publisher : "";
  const connected = tone === "on" || tone === "info" || tone === "partial";
  return (
    <Card
      variant={disabled ? "quiet" : "interactive"}
      size={featured ? "default" : "sm"}
      className={cn(disabled && "opacity-60")}
    >
      <div className="flex items-start gap-3">
        <span
          className={cn(
            "flex shrink-0 items-center justify-center rounded-lg border bg-background [&_img]:size-6 [&_svg]:size-6",
            featured ? "size-12 [&_img]:size-7 [&_svg]:size-7" : "size-10"
          )}
          aria-hidden="true"
        >
          {logo}
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            {disabled ? (
              <span className="truncate text-sm font-semibold">{title}</span>
            ) : (
              // The visible text is the title, so the accessible name contains
              // it verbatim (WCAG 2.5.3): "Configure X", not "Open settings".
              <button
                type="button"
                data-card-link
                onClick={onClick}
                aria-label={t`Configure ${title}`}
                className={cn("min-w-0 truncate text-left text-sm font-semibold", cardLinkClass)}
              >
                {title}
              </button>
            )}
            {/* Capped and truncating: a long publisher once took the whole row,
                pushed past the card and left the title no room at all. */}
            {mcp && (
              <span className="min-w-0 max-w-[50%] shrink truncate rounded-full border px-1.5 text-2xs font-medium leading-4 text-muted-foreground">
                {publisher ? <Trans>MCP · {publisher}</Trans> : t`MCP`}
              </span>
            )}
            {tag && (
              <span className="shrink-0 rounded-full bg-muted px-1.5 text-2xs font-medium leading-4 text-muted-foreground">
                {tag}
              </span>
            )}
          </div>
          <p className="mt-1 line-clamp-2 text-sm leading-snug text-muted-foreground">
            {featured && benefit ? benefit : description}
          </p>
        </div>
        {!disabled && !featured && (
          <ChevronRight className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
        )}
      </div>
      <CardFooter className="min-h-6 text-xs text-muted-foreground">
        <ConnectorDot tone={tone} />
        {/* The word stays beside the dot: colour is never the only channel
            (WCAG 1.4.1), and under deuteranopia green and amber converge. */}
        <span className={cn("truncate", tone === "on" && "font-medium text-foreground")}>{status}</span>
        <span className="ml-auto flex items-center gap-2">
          <StorageBadge storage={storage} />
          {featured && !disabled && !connected && (
            // Above the stretched title link, so it is its own target.
            <Button size="sm" className="relative z-10" onClick={onClick} tabIndex={-1}>
              <Trans>Connect</Trans>
            </Button>
          )}
        </span>
      </CardFooter>
    </Card>
  );
}
