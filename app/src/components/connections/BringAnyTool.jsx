"use client";

// The way in for any tool Duct doesn't list. It used to be the last tile of
// the catalogue, where only someone who had read the whole list and given up
// would find it, so it sits beside the sources worth adding next instead.
//
// Most people who need this have never heard of an MCP server, so it opens on
// what they get, and the picture says the rest before the sentence is read:
// tools they recognise, running into Duct, with a place left for theirs. The
// tiles are the picture and the controls both, because a blank search box asks
// people to know the feature works before trying it, and one click on a tool
// they use shows it does.
//
// A drawing rather than a mosaic panel: a panel marks a rare arrival and starts
// at 240px, which here would push the catalogue off the first screen. It keeps
// the panels' stones and their rule that blue is water, so it reads as one set.

import { useId, useState } from "react";
import { Plus } from "lucide-react";
import { Trans, useLingui } from "@lingui/react/macro";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";

// Product names, so not translated. Each returned its vendor's own server,
// tagged Official, on 2026-11-04, and none is in the catalogue already: a
// click here must land on the registry's best answer, never on an empty one.
// The marks are Simple Icons', like the catalogue's (logos.jsx).
const EXAMPLE_TOOLS = [
  { name: "Figma", mark: "/icons/figma.svg" },
  { name: "Canva", mark: "/icons/canva.svg" },
  { name: "Webflow", mark: "/icons/webflow.svg" },
  { name: "Airtable", mark: "/icons/airtable.svg" },
  { name: "Sentry", mark: "/icons/sentry.svg" },
];
const ON_THE_LEFT = EXAMPLE_TOOLS.slice(0, 3);
const ON_THE_RIGHT = EXAMPLE_TOOLS.slice(3);
const YOURS = "yours";
const LEFT_CHANNELS = ON_THE_LEFT.map(({ name }) => name);
const RIGHT_CHANNELS = [...ON_THE_RIGHT.map(({ name }) => name), YOURS];

// Where the three rows' middles fall in a column, in percent. Rows and gap are
// both in rem, so these hold at any text size.
const ROW_MIDDLES = [14.5, 50, 85.5];

const GROUND_TILE = 12;
const GROUND_SHADES = ["bring-ground-a", "bring-ground-b", "bring-ground-c"];
// Tiles along a side before the pattern repeats. Prime, so its rows don't line
// up into stripes. A fixed scatter: the same floor on every render.
const GROUND_SPAN = 7;
const GROUND_SIZE = GROUND_TILE * GROUND_SPAN;
const GROUND_TILES = Array.from({ length: GROUND_SPAN ** 2 }, (_, i) => {
  const [x, y] = [i % GROUND_SPAN, Math.floor(i / GROUND_SPAN)];
  return {
    x: x * GROUND_TILE,
    y: y * GROUND_TILE,
    shade: GROUND_SHADES[(x * x + y * 3 + x * y) % GROUND_SHADES.length],
  };
});

/** Fine and low contrast, as a panel's ground is: texture, never information. */
function Ground() {
  const id = useId();
  return (
    <svg className="bring-ground" aria-hidden="true">
      <defs>
        <pattern id={id} width={GROUND_SIZE} height={GROUND_SIZE} patternUnits="userSpaceOnUse">
          {GROUND_TILES.map(({ x, y, shade }) => (
            <rect
              key={`${x}-${y}`}
              x={x + 1}
              y={y + 1}
              width={GROUND_TILE - 2}
              height={GROUND_TILE - 2}
              rx="1.5"
              className={shade}
            />
          ))}
        </pattern>
      </defs>
      <rect width="100%" height="100%" fill={`url(#${id})`} />
    </svg>
  );
}

/**
 * One side's three channels, each a stone conduit with water running in it. All
 * the stone first: drawn channel by channel, each conduit would cover the water
 * of the one before it where they meet at the hub.
 */
function Channels({ tools, lit, flip = false }) {
  const channels = tools.map((tool, row) => ({
    tool,
    path: `M0 ${ROW_MIDDLES[row]} C50 ${ROW_MIDDLES[row]} 50 50 100 50`,
  }));
  // The box sizes the drawing, not the other way round: an svg with a viewBox
  // asks for a square, which made the whole card as tall as a channel was wide.
  return (
    <div className={cn("bring-channels", flip && "-scale-x-100")}>
      <svg viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
        {channels.map(({ tool, path }) => (
          <path key={tool} className="bring-conduit" d={path} />
        ))}
        {channels.map(({ tool, path }) => (
          <path key={tool} className="bring-water" d={path} data-lit={lit === tool ? "" : undefined} />
        ))}
      </svg>
    </div>
  );
}

/**
 * @param onAdd  Opens the add-by-address dialog.
 * @param onSearch  (name) => searches for it. Leave it out where search can't
 *   reach the registry (a Duct that turned it off): the names would find
 *   nothing, so they stay in the picture and stop being buttons.
 */
export default function BringAnyTool({ onAdd, onSearch = null }) {
  const { t } = useLingui();
  const [lit, setLit] = useState(null);

  const light = (name) => ({
    onPointerEnter: () => setLit(name),
    onPointerLeave: () => setLit(null),
    onFocus: () => setLit(name),
    onBlur: () => setLit(null),
  });

  const tool = ({ name, mark }) => {
    const face = (
      <>
        <span className="bring-stone">
          {/* No alt: the name is right beside it. */}
          <img src={mark} alt="" width="20" height="20" decoding="async" />
        </span>
        {name}
      </>
    );
    const look = cn(buttonVariants({ variant: "outline" }), "bring-tile");
    return onSearch ? (
      <button key={name} type="button" className={look} onClick={() => onSearch(name)} {...light(name)}>
        {face}
      </button>
    ) : (
      <span key={name} className={cn(look, "bring-tile-still")}>
        {face}
      </span>
    );
  };

  return (
    <Card variant="hero" className="bring-any-tool @container gap-0 overflow-hidden p-0">
      <div className="flex flex-col @2xl:flex-row">
        <div className="flex min-w-0 flex-1 flex-col items-start justify-center gap-4 p-6">
          <div className="flex flex-col gap-1">
            <h3 className="text-sm font-semibold">
              <Trans>Bring any tool</Trans>
            </h3>
            <p className="max-w-(--measure) text-pretty text-sm leading-relaxed text-muted-foreground">
              <Trans>
                Thousands of tools have an MCP server, and Duct&rsquo;s chat can use any of them. Find yours by
                name, or paste its address.
              </Trans>
            </p>
          </div>
          <Button onClick={onAdd}>
            <Plus aria-hidden="true" />
            <Trans>Add an MCP server</Trans>
          </Button>
        </div>
        <div className="bring-floor">
          <Ground />
          <div
            className="bring-map"
            role={onSearch ? "group" : undefined}
            aria-label={onSearch ? t`Search for a tool` : undefined}
            data-any-lit={lit ? "" : undefined}
          >
            <div className="bring-tools">{ON_THE_LEFT.map(tool)}</div>
            <Channels tools={LEFT_CHANNELS} lit={lit} />
            <span className="bring-hub" aria-hidden="true">
              <img src="/icons/icon.svg" alt="" width="48" height="48" decoding="async" />
            </span>
            <Channels tools={RIGHT_CHANNELS} lit={lit} flip />
            <div className="bring-tools">
              {ON_THE_RIGHT.map(tool)}
              <button
                type="button"
                className={cn(buttonVariants({ variant: "outline" }), "bring-tile bring-tile-yours")}
                aria-label={t`Add yours`}
                onClick={onAdd}
                {...light(YOURS)}
              >
                <span className="bring-stone bring-stone-empty">
                  <Plus aria-hidden="true" />
                </span>
                <Trans>Yours</Trans>
              </button>
            </div>
          </div>
        </div>
      </div>
    </Card>
  );
}
