/**
 * A pill that encodes state, and only state.
 *
 * DESIGN.md's tell-list names "badge/pill confetti" as the scaffold smell this
 * page had the worst case of: the same "This computer's key" chip repeated on
 * all three tier cards, saying the same thing three times and answering no
 * question. Call sites now render one only where a tier *deviates* — see
 * TierSummary, which says it once for the whole page when they agree.
 */
export default function StateChip({ tone = "neutral", children, title }) {
  return (
    <span className={`mt-chip mt-chip--${tone}`} title={title}>
      {children}
    </span>
  );
}
