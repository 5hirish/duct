---
title: "Keyword Gap Analysis Without a Spreadsheet"
seoTitle: "Keyword Gap Analysis Without a Spreadsheet: A Real Example"
date: Mar 10 2026
updated: Oct 28 2026
author: Shirish Kadam
category: Growth
tags: keyword research, content strategy, search console, seo
excerpt: "The keyword gap analysis I ran for this blog on October 27: what Search Console showed, which searches were worth chasing, and why I skipped a 22,200-search term."
description: "A keyword gap analysis worked end to end on a real site: what Search Console already shows, how to judge difficulty and fit, and how to pick one topic to own."
hero: assets/keyword-gap-analysis-without-a-spreadsheet/hero.webp
heroAlt: "A Roman mosaic of a colonnade with a roof gutter and five spouts: four pour into stone basins, and the fifth has no basin, so its water splashes into a puddle on orange paving"
madeWith: "First written in March 2026 with an AI assistant and no real data. Rewritten in October with Claude Code around the keyword research behind this blog's guides, using getduct.ai's own Search Console. Shirish checked every number before publishing."
readTime: 6
---

**A keyword gap analysis lists the searches your site should be found for and isn't, ranked by how likely you are to win them and what a win is worth.** It takes three inputs: what you already rank for (Search Console), how hard the neighboring searches are (a keyword tool), and what kind of page wins for a comparable site. The output is not a list of fifty keywords. It is one topic to own.

The first version of this post, in March, described that process in the abstract, with example numbers I made up. This version is the one I actually ran, for this blog, on October 27, 2026. Every number below came out of a tool that day. It took an afternoon and no spreadsheet.

## Where do you start a keyword gap analysis?

**With what Search Console already shows, because the cheapest wins are pages that rank and don't get clicked.** getduct.ai is a young site, and the baseline was humbling: in the three months to October 25 it earned 34 clicks from 5,523 impressions, and 21 of those clicks were people typing the brand.

Google defines an impression narrowly, which matters for what follows: "An impression means that a user has seen (or potentially seen) a link to your site in Search" ([Search Console Help](https://support.google.com/webmasters/answer/7042828)). A page that sits on page one and is seen without being clicked is telling you something specific.

| Page, and the search | Impressions | Average position | What it says |
|---|---|---|---|
| The harness engineering post, all searches | 81 | 7.6 | page one; the title is not earning the click |
| The open-source page, all searches | 76 | 6.3 | the same |
| The UTM builder, for "ga link builder" | 83 | 4.6 | wrong intent: these people want Google's own tool |
| The CPM calculator, for "counts per minute calculator" | 119 | 45.1 | wrong meaning altogether |

*Search Console for getduct.ai, July 25 to October 25, 2026. None of the four earned a click.*

The first two rows are the gap that costs nothing to close: a better title on a page that already ranks. The third is a lesson in intent. Someone searching "ga link builder" wants Google's [Campaign URL Builder](https://ga-dev-tools.google/campaign-url-builder/), and position 4.6 will not change their mind. The fourth is people looking for a radiation counter, and no title test will turn a Geiger counter into an ad budget.

Duct asks the first kind of question in its briefs whenever Search Console is connected. The check, `organic_ctr_gap` in [checks.py](https://github.com/5hirish/duct/blob/main/backend/agents/insights/checks.py), says why in its own words: "That is a title/snippet problem, not a ranking problem, and it is the cheapest fix in organic search."

## How do you find the searches you are missing?

**Write down the questions your buyers type, then look up volume and difficulty for each before writing anything.** I started from the product's category, AI agents, and asked what a marketer or product manager would search on the way to needing one. The volumes and difficulty scores below are US figures from OpenSEO's keyword data on October 27. Difficulty runs from 0 to 100; higher means harder to rank.

| Search | Monthly searches | Difficulty | Verdict |
|---|---|---|---|
| what is an ai agent | 22,200 | 49 | skip: too hard for a site this young |
| ai agent examples | 1,600 | 18 | take |
| human in the loop ai | 1,000 | 25 | take |
| what is agent harness | 590 | 21 | the harness post already covers it; improve that page |
| ai agents for marketing | 480 | 7 | the topic to own |
| ai agent vs chatbot | 320 | 12 | take |
| ai agents for product managers | 140 | 0 | too small on its own; covered by the others |
| agentic ai explained | 140 | 57 | skip |

The biggest number on the list was the easiest to say no to. A difficulty of 49 on a 22,200-search term is not winnable this year for a site with 30 referring domains, which is what getduct.ai had that day. "AI agents for marketing" has a forty-sixth of the volume and a difficulty of 7, and it is exactly what the product does. A page that ranks for it can end on a download without a stretch.

## What does a comparable site tell you?

**Which kind of page wins, not which keyword to copy.** I looked at the ranked keywords of ChatPRD's learning section, a hub on a site in a neighboring category. It ranked for 145 keywords, and the traffic estimates at the top of that list all pointed at a handful of pages about one term: what a PRD is, a PRD example, a spec template, a PRD for coding agents. That term is what the product makes.

The lesson was not "write about PRDs". It was that a narrow topic next to the product, covered thoroughly, beat a broad hub. That decided the format too: no separate learning hub with a glossary, just a cluster of guides inside the blog with one pillar page written last.

## How do you decide what to write first?

**Rank the gap by the chance of winning, then by fit, and only then by volume.** The rules I used, in the order I applied them:

1. **Difficulty under 30**, because a site with 30 referring domains does not win harder terms this year.
2. **The searcher's job matches the product's job.** A reader who searches "ai agents for marketing" can use Duct; one who searches "what is an ai agent" is often just curious.
3. **One topic, not a scatter.** Seven pieces on one subject build more trust than seven on seven subjects.
4. **Something only I can show.** Each guide needed first-hand evidence from Duct's own code or data; a page that only summarizes what already ranks has no reason to be chosen over it.

The result is a cluster of seven guides on AI agents for marketing, one a week, ending in a [pillar guide](/blog/ai-agents-for-marketing). The whole decision, with the numbers, lives on [a GitHub issue](https://github.com/5hirish/duct/issues/431), which is the only place a spreadsheet would have earned its keep.

## How often should you run a keyword gap analysis?

**The full analysis once a quarter; the Search Console half every week.** Volumes and difficulty move slowly. What moves weekly is which of your pages is climbing toward page one and which is ranking without being clicked, and that half is cheap to check every Monday.

Duct covers the weekly half: it reads Search Console and asks the ranking-without-clicks question in its briefs. It does not have keyword volumes or difficulty yet (that is [issue #216](https://github.com/5hirish/duct/issues/216)), so the quarterly half still needs a keyword tool. For this analysis I used OpenSEO's MCP server inside a Claude Code session: Search Console, keyword metrics and a competitor's ranked keywords, all as tool calls, with the decision written up as the last step.

## FAQ

### What is a keyword gap analysis?

A keyword gap analysis lists the searches your site should rank for and doesn't, then ranks them by how likely you are to win and what a win is worth. It combines your own Search Console data, volume and difficulty from a keyword tool, and what comparable sites rank for. The useful output is one topic to own, not a long list.

### Can I do a keyword gap analysis for free?

Partly. Search Console is free and gives you the most valuable half: pages that rank without clicks and queries climbing toward page one. Volumes and difficulty need a keyword tool. Google's Keyword Planner gives rough volume ranges inside a Google Ads account; paid tools add difficulty scores and competitors' rankings.

### What keyword difficulty should a new site target?

Low enough that your site's authority can win it this year. On a site with around 30 referring domains, I target difficulty under 30 and skip anything near 50, however large its volume. The threshold is a judgment, not a law: recheck it as links grow, and let fit with your product break ties.

### How is a keyword gap different from a content gap?

A keyword gap starts from searches and asks which ones you are missing. A content gap starts from topics and asks which ones you have not covered. They meet in the middle: each search you decide to win needs a page that answers it better than what ranks today, which is a content decision.
