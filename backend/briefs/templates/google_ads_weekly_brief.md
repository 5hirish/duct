# Google Ads Weekly Brief Template

Use this template after the raw Google Ads data has already been normalized into
the `GoogleAdsBrief` schema contract.

## Job

Turn the structured Google Ads payload into a concise operator report.

The report must answer:

1. What changed?
2. Why does it matter?
3. What should the operator do next?

## Rules

- Use only the normalized payload provided.
- Do not invent platform data.
- Prefer concrete operator language over abstract marketing language.
- Make recommendations specific: scale, pause, monitor, refresh, tighten, or investigate.
- Focus on campaign-level decisions, not generic PPC advice.
- If evidence is weak, say so with lower confidence.

## Output Contract

Return:

- `narrative.verdict`
- `narrative.summary`
- `narrative.operator_takeaway`
- `highlights[]`
- `risks[]`
- `recommended_actions[]`

## Finding Style

Each finding should include:

- a short title
- 1-3 pieces of evidence from the data
- why it matters commercially
- a clear recommended action
- a confidence level

## Example Tone

Good:

- Brand search is carrying efficiency while two non-brand campaigns are burning spend without enough conversion value to justify their budget.
- Pause Campaign X this week unless conversion quality improves after targeting cleanup.
- CTR is falling, which points to likely creative fatigue rather than a bidding issue alone.

Bad:

- Performance was mixed overall.
- Consider optimizing campaigns.
- Some campaigns may need improvement.
