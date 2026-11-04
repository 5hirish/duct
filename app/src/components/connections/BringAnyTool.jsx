"use client";

// The way in for any tool Duct doesn't list. It used to be the last tile of
// the catalogue, where only someone who had read the whole list and given up
// would find it, so it sits beside the sources worth adding next instead.
//
// Most people who need this have never heard of an MCP server, so it opens on
// what they get. The names are there because a blank search box asks them to
// know the feature works before trying it, and one click on a tool they use
// shows it does.

import { Plug, Plus } from "lucide-react";
import { Trans, useLingui } from "@lingui/react/macro";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";

// Product names, so not translated. Each returned its vendor's own server,
// tagged Official, on 2026-11-04, and none is in the catalogue already: a
// click here must land on the registry's best answer, never on an empty one.
const EXAMPLE_TOOLS = ["Figma", "Canva", "Webflow", "Airtable", "Sentry"];

/**
 * @param onAdd  Opens the add-by-address dialog.
 * @param onSearch  (name) => searches for it. Leave it out where search can't
 *   reach the registry (a Duct that turned it off): the names would find nothing.
 */
export default function BringAnyTool({ onAdd, onSearch = null }) {
  const { t } = useLingui();
  return (
    <Card variant="hero" className="@container">
      <div className="flex flex-col gap-4 @2xl:flex-row @2xl:items-center">
        <div className="flex min-w-0 flex-1 items-start gap-3">
          <span
            className="flex size-12 shrink-0 items-center justify-center rounded-lg border bg-background [&_svg]:size-6"
            aria-hidden="true"
          >
            <Plug className="text-brand" />
          </span>
          <div className="min-w-0 flex-1">
            <h3 className="text-sm font-semibold">
              <Trans>Bring any tool</Trans>
            </h3>
            <p className="mt-1 text-pretty text-sm text-muted-foreground">
              <Trans>
                Thousands of tools have an MCP server, and Duct&rsquo;s chat can use any of them. Find yours by
                name, or paste its address.
              </Trans>
            </p>
          </div>
        </div>
        <Button className="shrink-0 self-start @2xl:self-center" onClick={onAdd}>
          <Plus aria-hidden="true" />
          <Trans>Add an MCP server</Trans>
        </Button>
      </div>
      {onSearch && (
        <div role="group" aria-label={t`Search for a tool`} className="flex flex-wrap items-center gap-1.5">
          <span className="mr-1 text-xs text-muted-foreground" aria-hidden="true">
            <Trans>Try</Trans>
          </span>
          {EXAMPLE_TOOLS.map((tool) => (
            <button
              key={tool}
              type="button"
              onClick={() => onSearch(tool)}
              className="rounded-full border bg-background px-3 py-1 text-xs font-medium text-foreground transition-colors hover:bg-accent"
            >
              {tool}
            </button>
          ))}
        </div>
      )}
    </Card>
  );
}
