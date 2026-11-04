"use client";

import { useEffect, useRef, useState } from "react";

/**
 * True once the element has come within `margin` of the viewport, and true
 * from then on.
 *
 * For lists whose items are expensive to fill (a fetch, a whole document in an
 * iframe): the ones far below the fold wait until someone scrolls toward
 * them. It latches rather than toggling, so an item never unmounts and loses
 * its state on the way back up. Where IntersectionObserver is missing it
 * answers true at once, which is the behaviour from before it existed.
 *
 * Returns `[ref, near]`; put `ref` on the item's outer element.
 */
export function useNearViewport(margin = "400px") {
  const ref = useRef(null);
  const [near, setNear] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el || near) return undefined;
    if (typeof IntersectionObserver === "undefined") {
      setNear(true);
      return undefined;
    }
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          setNear(true);
          observer.disconnect();
        }
      },
      { rootMargin: margin },
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, [margin, near]);

  return [ref, near];
}

export default useNearViewport;
