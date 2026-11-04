"use client";

// The Connections catalogue: a search, the filters, and the sources arranged
// for whatever is typed and chosen. Native connectors and MCP servers are one
// list here, the way they are one list to the person setting Duct up.
//
// Nothing here decides what goes where: `arrangeCatalog` (lib/connectorCatalog.js)
// does, from plain entries, so the page holds at nineteen sources and at two
// hundred, and the scenes in `/preview` render it at both. Each entry brings
// its own `render()`, which keeps every connector's card and dialog with the
// code that owns it.
//
// Filters, in the order people reach for them: whether it is connected (the
// tabs, in the page header, the way Documents and Activity filter), what they
// type, what the source is for (the chips, because the categories are the
// map of the list), and who stands behind it, in a menu. The tabs replaced a
// Connected section above a More sources one: two sections of one list, the
// second reachable only by scrolling past the first. A chip or an option that
// would leave nothing is not offered, unless it is the one chosen.
//
// Controlled: the page holds the filters, because the tabs live in its header.

import { useMemo, useRef } from "react";
import { Search } from "lucide-react";
import { plural } from "@lingui/core/macro";
import { Trans, useLingui } from "@lingui/react/macro";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Section, TileGrid } from "@/components/ui/page";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  ALL,
  CATEGORY_LABELS,
  CATEGORY_ORDER,
  ConnectionStatus,
  Origin,
  arrangeCatalog,
  facetCounts,
  showStatusTabs,
} from "@/lib/connectorCatalog";
import { useShortcut } from "@/lib/shortcuts";
import { cn } from "@/lib/utils";
import ConnectorDot from "./ConnectorDot";

export const NO_FILTERS = Object.freeze({ query: "", category: ALL, status: ALL, origin: ALL });

function useLabelOf() {
  const { i18n } = useLingui();
  return (category) => (CATEGORY_LABELS[category] ? i18n._(CATEGORY_LABELS[category]) : "");
}

/**
 * All · Connected · Not connected, for the page header's actions. Each count
 * is what the tab would show with the search and the other filters as they
 * are. A dot on Connected when something there needs attention, the one
 * thing on the page that is broken; those sources sort first in it. Nothing
 * on the first day, when every tab would say what All says.
 */
export function StatusTabs({ entries, filters, onFiltersChange }) {
  const { t } = useLingui();
  const labelOf = useLabelOf();
  if (!showStatusTabs(entries, filters.status)) return null;
  const { status } = facetCounts(entries, filters, { labelOf });
  const attention = status[ConnectionStatus.ATTENTION] > 0;
  const tabs = [
    { value: ALL, label: t`All` },
    { value: ConnectionStatus.CONNECTED, label: t`Connected` },
    { value: ConnectionStatus.AVAILABLE, label: t`Not connected` },
  ];
  return (
    <Tabs value={filters.status} onValueChange={(value) => onFiltersChange({ ...filters, status: value })}>
      <TabsList aria-label={t`Status`}>
        {tabs.map((tab) => (
          <TabsTrigger key={tab.value} value={tab.value} className="gap-1.5">
            {tab.label}
            <span className="tabular-nums text-muted-foreground">{status[tab.value]}</span>
            {/* The tiles' own amber, so the tab and the card say it the same way. */}
            {tab.value === ConnectionStatus.CONNECTED && attention && (
              <ConnectorDot tone="partial" label={t`Something needs attention`} />
            )}
          </TabsTrigger>
        ))}
      </TabsList>
    </Tabs>
  );
}

/**
 * @param entries   catalogue entries (lib/connectorCatalog.js), each with
 *                  `render()` for its tile
 * @param filters   `{ query, category, status, origin }`
 * @param onFiltersChange  (next filters) => void
 * @param featured  ids of the first sources worth connecting, lifted out of
 *                  the list while browsing
 * @param renderFeatured  (id) => the large tile for one of `featured`
 * @param trailing  what ends the list: the "Any MCP server" tile, or the tiles
 *                  standing in while MCP servers load
 * @param moreResults  what a search finds outside this catalogue (the MCP
 *                  Registry's section), under the results and never mixed
 *                  into them: those sources are not ours to file or rank
 */
export default function ConnectorBrowser({
  entries,
  filters,
  onFiltersChange,
  featured = [],
  renderFeatured,
  trailing = null,
  moreResults = null,
}) {
  const { t, i18n } = useLingui();
  const labelOf = useLabelOf();
  const searchRef = useRef(null);
  const set = (patch) => onFiltersChange({ ...filters, ...patch });
  // Clear keeps the tab: it is where the person stands, not part of the question.
  const clear = () => onFiltersChange({ ...NO_FILTERS, status: filters.status });

  // "/" finds the search from anywhere on the page, as on most catalogues.
  useShortcut("/", () => searchRef.current?.focus());

  const view = useMemo(
    () => arrangeCatalog(entries, filters, { featured, labelOf }),
    // labelOf follows the locale
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [entries, filters, featured, i18n.locale],
  );
  const { counts } = view;

  const originOptions = [
    { value: ALL, label: t`Built by anyone` },
    { value: Origin.DUCT, label: t`Built by Duct` },
    { value: Origin.VENDOR, label: t`The vendor's MCP server` },
    { value: Origin.YOURS, label: t`Added by you` },
  ].filter((o) => o.value === ALL || o.value === filters.origin || counts.origin[o.value] > 0);

  const categories = CATEGORY_ORDER.filter((c) => c === filters.category || counts.category[c] > 0);

  return (
    <>
      <div role="search" className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <div className="relative min-w-0 flex-1 basis-64">
            <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
            <Input
              ref={searchRef}
              type="search"
              value={filters.query}
              onChange={(e) => set({ query: e.target.value })}
              onKeyDown={(e) => {
                if (e.key === "Escape" && filters.query) set({ query: "" });
              }}
              placeholder={plural(view.total, { one: "Search # source", other: "Search # sources" })}
              aria-label={t`Search sources`}
              className="pl-9 pr-9"
            />
            {!filters.query && (
              <kbd className="pointer-events-none absolute right-3 top-1/2 hidden -translate-y-1/2 rounded border border-border bg-background px-1.5 text-2xs text-muted-foreground @lg:inline">
                /
              </kbd>
            )}
          </div>
          {originOptions.length > 1 && (
            <FacetSelect
              label={t`Built by`}
              value={filters.origin}
              options={originOptions}
              onChange={(origin) => set({ origin })}
            />
          )}
        </div>
        {categories.length > 1 && (
          <div role="group" aria-label={t`Category`} className="flex flex-wrap gap-1.5">
            <Chip active={filters.category === ALL} count={counts.category[ALL]} onClick={() => set({ category: ALL })}>
              <Trans>All</Trans>
            </Chip>
            {categories.map((c) => (
              <Chip
                key={c}
                active={filters.category === c}
                count={counts.category[c] || 0}
                onClick={() => set({ category: filters.category === c ? ALL : c })}
              >
                {labelOf(c)}
              </Chip>
            ))}
          </div>
        )}
      </div>

      {view.mode === "results" ? (
        <>
          <Results view={view} filters={filters} trailing={trailing} onClear={clear} />
          {moreResults}
        </>
      ) : (
        <Browse view={view} filters={filters} renderFeatured={renderFeatured} trailing={trailing} labelOf={labelOf} set={set} />
      )}
    </>
  );
}

function Browse({ view, filters, renderFeatured, trailing, labelOf, set }) {
  const { featured, groups, counts } = view;
  // The way in for anything unlisted ends every tab but Connected.
  const tail = filters.status === ConnectionStatus.CONNECTED ? null : trailing;
  const sections = groups.length ? groups : tail ? [{ category: ALL, items: [], more: 0 }] : [];
  const anyConnected = counts.status[ConnectionStatus.CONNECTED] > 0;
  return (
    <>
      {featured.length > 0 && (
        <Section title={anyConnected ? <Trans>Worth adding next</Trans> : <Trans>Start with these</Trans>}>
          {/* Two across at most: a starter tile carries a sentence and a
              button, and four across cut the sentence to an ellipsis. */}
          <TileGrid cols={2}>{featured.map((e) => renderFeatured?.(e.id) ?? e.render())}</TileGrid>
        </Section>
      )}

      {sections.map((group, i) => {
        const last = i === sections.length - 1;
        const whole = group.category === ALL;
        return (
          <Section
            key={group.category}
            // One grid needs no name of its own, the tab says what it holds,
            // unless the starters sit above it. Many grids are named for
            // their category.
            title={whole ? (featured.length > 0 ? <Trans>Everything else</Trans> : undefined) : labelOf(group.category)}
            // The number is the chip's, because Show all is the chip: what it
            // says is what clicking gives.
            actions={
              group.more > 0 && (
                <ShowAll count={counts.category[group.category]} onClick={() => set({ category: group.category })} />
              )
            }
          >
            <TileGrid>
              {group.items.map((e) => e.render())}
              {last && tail}
            </TileGrid>
          </Section>
        );
      })}

      {!sections.length && (
        <p className="text-sm text-muted-foreground">
          <Trans>Nothing connected yet.</Trans>
        </p>
      )}
    </>
  );
}

function Results({ view, filters, trailing, onClear }) {
  const { results } = view;
  const query = filters.query.trim();
  // The way in for anything the list does not have, unless the tab asks
  // only for what is already connected.
  const offerAdd = filters.status !== ConnectionStatus.CONNECTED;
  const clearButton = (
    <Button variant="ghost" size="sm" onClick={onClear}>
      <Trans>Clear filters</Trans>
    </Button>
  );

  if (!results.length) {
    return (
      <Section>
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
          <p className="text-sm text-muted-foreground">
            {query ? <Trans>Nothing matches “{query}”.</Trans> : <Trans>Nothing here with these filters.</Trans>}
          </p>
          {clearButton}
        </div>
        {offerAdd && trailing && (
          <>
            <p className="text-sm text-muted-foreground">
              <Trans>Not listed? Any remote MCP server connects by its address.</Trans>
            </p>
            <TileGrid>{trailing}</TileGrid>
          </>
        )}
      </Section>
    );
  }

  return (
    <Section title={plural(results.length, { one: "# source", other: "# sources" })} actions={clearButton}>
      <TileGrid>
        {results.map((e) => e.render())}
        {offerAdd && trailing}
      </TileGrid>
    </Section>
  );
}

function ShowAll({ count, onClick }) {
  return (
    <Button variant="ghost" size="sm" onClick={onClick}>
      <Trans>Show all {count}</Trans>
    </Button>
  );
}

/** A category to filter by. Neutral when chosen: orange is the page's one
 *  primary action, and a filter is not that. */
function Chip({ active, count, onClick, children }) {
  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={onClick}
      className={cn(
        "rounded-full px-3 py-1 text-xs font-medium transition-colors",
        active ? "bg-foreground text-background" : "bg-muted text-muted-foreground hover:text-foreground"
      )}
    >
      {children} <span className="tabular-nums opacity-70">{count}</span>
    </button>
  );
}

/** A narrower filter, in a menu: the trigger names the choice, the label
 *  names the question for a screen reader. */
function FacetSelect({ label, value, options, onChange }) {
  return (
    <Select value={value} onValueChange={onChange}>
      <SelectTrigger aria-label={label} className={cn("min-w-0", value !== ALL && "text-foreground")}>
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {options.map((o) => (
          <SelectItem key={o.value} value={o.value}>
            {o.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
