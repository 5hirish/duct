"use client";

// A handful of tesserae thrown in the air, once, when a key verifies.
//
// The plan asked for confetti and the mosaic rule says what colour confetti
// is here: the six stones, blue for water only, terracotta under a tenth.
// Pure CSS, no library — the app has no confetti dependency and one moment
// does not earn one. Gone from the DOM when the animation ends, and never
// rendered at all under reduced motion.

import { useEffect, useMemo, useState } from "react";

const COUNT = 22;
// Travertine, grey limestone, ochre, basalt, glass paste, terracotta. Weighted
// so the burst reads as stone with one glint of water and a couple of orange.
const STONES = [
  "var(--tessera-cream)",
  "var(--tessera-cream)",
  "var(--tessera-grey)",
  "var(--tessera-ochre)",
  "var(--tessera-ochre)",
  "var(--tessera-basalt)",
  "var(--tessera-glass)",
  "var(--tessera-terracotta)",
];
const DURATION_MS = 1100;

function pieces() {
  return Array.from({ length: COUNT }, (_, i) => {
    const angle = (i / COUNT) * Math.PI * 2 + (Math.random() - 0.5) * 0.6;
    const distance = 60 + Math.random() * 90;
    return {
      id: i,
      x: Math.round(Math.cos(angle) * distance),
      y: Math.round(Math.sin(angle) * distance - 40),
      rotate: Math.round((Math.random() - 0.5) * 540),
      size: 6 + Math.round(Math.random() * 5),
      delay: Math.round(Math.random() * 120),
      stone: STONES[(i * 5 + Math.floor(Math.random() * 3)) % STONES.length],
    };
  });
}

export default function TesseraBurst({ onDone }) {
  const [reduced, setReduced] = useState(true);
  const items = useMemo(pieces, []);

  useEffect(() => {
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    setReduced(mq.matches);
    const timer = setTimeout(() => onDone?.(), DURATION_MS + 150);
    return () => clearTimeout(timer);
  }, [onDone]);

  if (reduced) return null;
  return (
    <div className="tessera-burst" aria-hidden="true">
      {items.map((t) => (
        <span
          key={t.id}
          className="tessera"
          style={{
            "--tx": `${t.x}px`,
            "--ty": `${t.y}px`,
            "--rot": `${t.rotate}deg`,
            "--size": `${t.size}px`,
            "--delay": `${t.delay}ms`,
            "--dur": `${DURATION_MS}ms`,
            background: t.stone,
          }}
        />
      ))}
    </div>
  );
}
