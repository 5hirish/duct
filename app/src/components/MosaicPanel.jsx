import { cn } from "@/lib/utils";

/**
 * A Roman mosaic threshold panel, for the surfaces someone *arrives* at —
 * first run, a break, a dead end. `app/DESIGN.md` holds the placement rules and
 * the `mosaic-panel` skill holds how a new one is made.
 *
 * Two things this component exists to stop call sites getting wrong:
 *
 * The panel is decorative and its Latin is not translatable, does not scale
 * with browser text settings, and reaches no screen reader — so it is always
 * hidden from the accessibility tree, and the surface must carry the real
 * heading in real markup beside it. `CDIV` in the tiles, "Page not found" in
 * the DOM.
 *
 * And it is never smaller than 240px. Below that the tesserae stop resolving as
 * tesserae and the panel is just a smudge; a small empty state takes a lucide
 * icon instead.
 */

// The panels that exist. A typo'd string would 404 silently into an alt-less
// broken image, which on an error page is a bleak thing to ship.
export const MOSAIC = {
  fons: "fons", // the front door — the spring, before anything has run
  salve: "salve", // first run, onboarding
  nihil: "nihil", // empty — nothing here yet
  fractum: "fractum", // something broke
  cdiv: "cdiv", // 404
  caveCanem: "cave-canem", // 403, no access
  otium: "otium", // all caught up
};

const MIN_SIZE = 240;

export default function MosaicPanel({ name, size = MIN_SIZE, className }) {
  const px = Math.max(size, MIN_SIZE);

  return (
    <img
      src={`/art/mosaic/${name}.webp`}
      alt=""
      aria-hidden
      width={px}
      height={px}
      // Eager, not lazy: on these surfaces the panel is the hero and sits above
      // the fold, so deferring it only delays the one thing that makes the page
      // feel handled rather than crashed.
      loading="eager"
      decoding="async"
      className={cn("rounded-xl", className)}
      style={{ width: px, height: px }}
    />
  );
}
