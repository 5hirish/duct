/**
 * The status dot — the one place a tone becomes a colour.
 *
 * It was three places: the tile, the dialog header, and the tone the provider
 * card derived for both. Each was an inline ternary over `on`/`partial`, so
 * adding `info` (a key that works but is not yours) lit the tile blue and left
 * the dialog's dot grey — the same connection, two answers, one screen apart.
 * A map fails loudly on a tone nobody handled; a ternary silently returns "".
 */

const DOT_CLASS = {
  on: "conn-dot--on",
  info: "conn-dot--info",
  partial: "conn-dot--partial",
  // Not a state, the absence of one: nothing has been asked yet. Grey alone
  // would be indistinguishable from "off", which is a claim.
  loading: "conn-dot--loading",
  off: "",
};

/**
 * @param tone  "on" | "info" | "partial" | "loading" | "off"
 * @param label  The state in words, when the dot is the only thing saying it.
 *   Omit where the state is already spelled out next to it — a second reading
 *   of "Connected" is noise to a screen reader, and colour is not the only
 *   channel there (WCAG 1.4.1) because the words are right beside it.
 */
export default function ConnectorDot({ tone = "off", label }) {
  const className = `conn-dot${DOT_CLASS[tone] ? ` ${DOT_CLASS[tone]}` : ""}`;
  if (!label) return <span className={className} aria-hidden="true" />;
  return <span className={className} role="img" aria-label={label} />;
}
