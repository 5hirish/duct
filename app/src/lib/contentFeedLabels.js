/**
 * The words for lib/contentFeed.js's values, as message descriptors rendered
 * with `i18n._(…)` in the component that shows them. Kept apart so the
 * values module stays importable under plain Node.
 */

import { msg } from "@lingui/core/macro";
import { Disclosure, FeedSource } from "./contentFeed.js";

export const SOURCE_LABELS = {
  [FeedSource.GITHUB]: msg`GitHub`,
  [FeedSource.DUCT]: msg`What Duct did`,
  [FeedSource.LINEAR]: msg`Linear`,
  [FeedSource.NOTION]: msg`Notion`,
  [FeedSource.RSS]: msg`Your feeds`,
  [FeedSource.MILESTONES]: msg`Milestones`,
};

export const DISCLOSURE_LABELS = {
  [Disclosure.RELEASES]: msg`Releases only`,
  [Disclosure.SHIPPED]: msg`What shipped`,
  [Disclosure.EVERYTHING]: msg`Everything`,
};

export const DISCLOSURE_HINTS = {
  [Disclosure.RELEASES]: msg`Releases and their notes.`,
  [Disclosure.SHIPPED]: msg`Releases, merged pull requests, commits to your main branch, README and changelog edits.`,
  [Disclosure.EVERYTHING]: msg`Also closed issues and changes under docs/.`,
};

// Mirror of backend LeftOut. Plural-free on purpose: the count is drawn
// beside the label, so "Bots: 2" reads in every language.
export const LEFT_OUT_LABELS = {
  bot: msg`Bots`,
  dependency: msg`Dependency bumps`,
  chore: msg`Chores, CI and tests`,
  squashed: msg`Commits already in a pull request`,
  issue: msg`Issues`,
  prerelease: msg`Pre-releases`,
  internal_docs: msg`Internal docs`,
  disclosure: msg`Kept back by your setting`,
  already_planned: msg`Already on a plan`,
  over_cap: msg`Over the limit`,
};
