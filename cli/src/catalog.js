// Every check the launch-check skill defines, in one place.
//
// The ids, areas and weights are the skill's (skills/launch-check/references/
// checklist.md); test/catalog.test.js fails when the two disagree, so a check
// added to the checklist cannot be silently missing here. `impact` and
// `effort` are the checklist's "Impact guide for ranking", as [FAIL, WARN]:
// they rank fixes when the CLI runs alone. With the skill, the agent re-ranks
// with what it learned from the repository.

export const SCHEMA_ID = 'getduct/launch-check@1';

export const AREAS = [
  { key: 'measurement', name: 'Measurement', weight: 25, prefix: 'M' },
  { key: 'claims', name: 'Claims', weight: 20, prefix: 'K' },
  { key: 'search', name: 'Search', weight: 20, prefix: 'S' },
  { key: 'social', name: 'Social card', weight: 15, prefix: 'C' },
  { key: 'answer', name: 'Answer engines', weight: 10, prefix: 'A' },
  { key: 'first', name: 'First impression', weight: 10, prefix: 'F' },
];

export const STATUSES = ['PASS', 'WARN', 'FAIL', 'UNVERIFIED'];
export const FOUND_BY = ['live site', 'repository', 'both'];

export const PENALTY = { FAIL: 25, WARN: 10 };

export const BANDS = [
  { min: 85, name: 'Ready' },
  { min: 70, name: 'Ready after fixes' },
  { min: 55, name: 'Needs work' },
  { min: 0, name: 'Not ready' },
];

// where: what can settle the check. `repo` checks are never run by the CLI;
// they come back UNVERIFIED for the agent to settle.
export const CHECKS = {
  M1: { where: 'both', name: 'tag present', fix: 'Add an analytics tag', impact: [3, 2], effort: [1, 1] },
  M2: { where: 'both', name: 'tag everywhere', fix: 'Load the analytics tag on every page', impact: [2, 2], effort: [1, 1] },
  M3: { where: 'repo', name: 'tag ships to production', fix: 'Ship the analytics tag to production', impact: [3, 2], effort: [1, 1] },
  M4: { where: 'repo', name: 'not blocked', fix: 'Let the analytics script through', impact: [3, 2], effort: [2, 1] },
  M5: { where: 'repo', name: 'conversion event', fix: 'Send an event for the one action', impact: [3, 2], effort: [1, 1] },
  M6: { where: 'repo', name: 'outbound conversion', fix: 'Count the click before it leaves the site', impact: [3, 2], effort: [1, 1] },
  M7: { where: 'repo', name: 'event name is stable', fix: 'Use one event name for the action', impact: [2, 1], effort: [1, 1] },
  M8: { where: 'live', name: 'search console', fix: 'Verify the site in Search Console', impact: [1, 1], effort: [1, 1] },
  K1: { where: 'both', name: 'the demo works', fix: 'Make the demo match the product', impact: [3, 2], effort: [2, 2] },
  K2: { where: 'both', name: 'the price and sign-in', fix: 'Make the first-screen promise true', impact: [3, 2], effort: [2, 1] },
  K3: { where: 'both', name: 'counts and lists', fix: 'Make the numbers agree', impact: [1, 1], effort: [1, 1] },
  K4: { where: 'both', name: 'release notes', fix: 'Bring the release notes and the site in line', impact: [2, 2], effort: [1, 1] },
  S1: { where: 'live', name: 'indexable', fix: 'Let search engines index the page', impact: [3, 2], effort: [1, 1] },
  S2: { where: 'live', name: 'title', fix: 'Give every key page its own title', impact: [2, 1], effort: [1, 1] },
  S3: { where: 'both', name: 'description', fix: 'Write a description for the homepage', impact: [2, 1], effort: [1, 1] },
  S4: { where: 'both', name: 'canonical', fix: 'Point canonicals at the live domain', impact: [3, 1], effort: [1, 1] },
  S5: { where: 'live', name: 'one H1', fix: 'Give each page one H1 that says what it is', impact: [1, 1], effort: [1, 1] },
  S6: { where: 'both', name: 'sitemap', fix: 'Fix the sitemap', impact: [3, 1], effort: [2, 1] },
  S7: { where: 'live', name: 'HTTPS and redirects', fix: 'Redirect HTTP to HTTPS in one hop', impact: [3, 1], effort: [1, 1] },
  S8: { where: 'live', name: 'rendered HTML', fix: 'Render the page text into the HTML', impact: [2, 2], effort: [3, 3] },
  S9: { where: 'repo', name: 'base-URL source', fix: 'Set the site URL to the live domain', impact: [3, 3], effort: [1, 1] },
  S10: { where: 'both', name: 'review markup', fix: 'Remove review markup the page does not show', impact: [2, 2], effort: [1, 1] },
  C1: { where: 'both', name: 'image exists', fix: 'Give the social card an image that loads', impact: [3, 2], effort: [1, 1] },
  C2: { where: 'repo', name: 'image source', fix: 'Serve the social card image from a built folder', impact: [3, 3], effort: [1, 1] },
  C3: { where: 'live', name: 'image size', fix: 'Export the social image at 1200x630', impact: [1, 1], effort: [1, 1] },
  C4: { where: 'live', name: 'title and description', fix: 'Add og:title and og:description', impact: [2, 2], effort: [1, 1] },
  C5: { where: 'live', name: 'twitter card', fix: 'Use the large card on X', impact: [2, 2], effort: [1, 1] },
  C6: { where: 'live', name: 'one card per page', fix: 'Give shared pages their own card', impact: [1, 1], effort: [2, 2] },
  A1: { where: 'both', name: 'AI crawlers allowed', fix: 'Let AI crawlers read the site', impact: [2, 2], effort: [1, 1] },
  A2: { where: 'live', name: 'llms.txt', fix: 'Publish an llms.txt', impact: [1, 1], effort: [1, 1] },
  A3: { where: 'live', name: 'structured data', fix: 'Match the homepage JSON-LD to the page', impact: [1, 1], effort: [1, 1] },
  A4: { where: 'live', name: 'answer first', fix: 'Say what it is in the first sentence', impact: [2, 2], effort: [1, 1] },
  A5: { where: 'live', name: 'facts are text', fix: 'Put the key facts in text', impact: [1, 1], effort: [1, 1] },
  F1: { where: 'live', name: 'who and what', fix: 'Say who it is for in the headline', impact: [2, 2], effort: [2, 2] },
  F2: { where: 'live', name: 'one primary action', fix: 'Fix the main call to action', impact: [3, 2], effort: [1, 1] },
  F3: { where: 'live', name: 'action copy', fix: 'Name the outcome on the main button', impact: [2, 2], effort: [1, 1] },
  F4: { where: 'live', name: 'proof', fix: 'Show one piece of proof on the homepage', impact: [1, 1], effort: [1, 1] },
  F5: { where: 'live', name: 'dead links', fix: 'Fix the dead links', impact: [2, 1], effort: [1, 1] },
};

export function areaOf(id) {
  return AREAS.find((a) => a.prefix === id[0]);
}
