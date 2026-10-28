---
title: "Why Your SEO Metrics Aren't Telling You the Full Story"
seoTitle: "Why Your SEO Metrics Aren't Telling You the Full Story"
date: Mar 15 2026
updated: Oct 28 2026
author: Shirish Kadam
category: Growth
tags: seo, search console, ga4, organic growth
excerpt: "5,523 impressions, 34 clicks, 21 of them for the brand. This site's own Search Console read beside GA4: five checks that tell visibility from growth."
description: "Search Console, GA4 and backlink tools each tell one true part of the story. Five checks, on a real site's numbers, that tell visibility from real growth."
hero: assets/why-your-seo-metrics-arent-telling-you-the-full-story/hero.webp
heroAlt: "A Roman mosaic of an aqueduct: a tall gauge post marks the channel full at the left, water leaks through two orange-marked cracks along the arches, and only a thin stream reaches a round fountain basin at the right"
madeWith: "First written in March 2026 with an AI assistant, with an invented example and a false claim about Duct. Rewritten in October with Claude Code from getduct.ai's own Search Console and GA4. Shirish checked every number before publishing."
readTime: 5
---

**Each SEO tool is right about one layer and misleading about the rest.** Search Console measures whether people saw you, a backlink tool measures whether other sites vouch for you, and GA4 measures what visitors did once they arrived. Impressions can climb while clicks stay flat, and clicks can climb while nobody converts. The full story comes from reading them in order, with brand searches taken out first.

The March version of this post told that story with an invented example and ended by saying Duct reads Ahrefs. Duct has no Ahrefs connector, and the example wasn't real. Here is a real one: this site, getduct.ai, over the three months to late October 2026.

## The three layers, measured on one site

**Each layer has a headline number that looks like progress and a detail that says otherwise.**

| Layer | Tool | The headline | The detail |
|---|---|---|---|
| Visibility | Search Console | 5,523 impressions and 34 clicks, July 25 to October 25 | 21 of the 34 clicks were people searching the brand; most impressions sit on page three or later |
| Authority | a backlink tool (OpenSEO here) | 30 referring domains on October 27, up from 2 at the end of July | nothing about whether those links point at pages people search for |
| Conversion | GA4 | 50 organic-search sessions on getduct.ai, July 28 to October 27 | one key event among them, on the home page |

None of these numbers is wrong. Read alone, each one supports a different story: growing visibility, growing authority, a site that converts its visitors. Read together they say something plainer. Almost nobody finds this site through search unless they already know its name, and the pages that are seen are seen too deep to be clicked.

## What do the gaps between the layers mean?

**Five patterns, each with a real example from the same three months.**

**1. Many impressions, deep position.** The CPM calculator had 1,143 impressions, the most of any page, at an average position of 28 and one click. Google records an impression only when a result is seen, and its help page notes that a result on page three gets no impression for a user who never goes past page one ([Search Console Help](https://support.google.com/webmasters/answer/7042828)). Impressions at position 28 are a few people paging far, not visibility. Read position before you read impressions.

**2. Good position, no clicks.** "ga link builder" sent 83 impressions to the UTM builder at position 4.6 and not one click. The ranking is fine. The intent is not: those searchers want Google's own [Campaign URL Builder](https://ga-dev-tools.google/campaign-url-builder/), and they click it. The fix is a title that says plainly what the page is, or accepting that the query belongs to someone else.

**3. The wrong meaning.** "counts per minute calculator" sent the CPM calculator 119 impressions at position 45. Those people are measuring radiation, not ad costs. There is nothing to fix; there is something to filter out before you read a trend, or it will flatter you.

**4. Clicks that are really the brand.** "duct ai" and "duct.ai" account for 21 of the 34 clicks. That is people who already heard of the product and used Google as an address bar. It is worth having, and it is not organic growth. Take brand queries out before you judge whether search is working.

**5. Sessions without key events.** The home page drew 30 organic sessions in GA4 and one key event. Visitors came and left. That is a page problem, not a search problem, and no amount of ranking work fixes it.

## Why does GA4 show more organic sessions than Search Console shows clicks?

**Because they count different things, and both are right.** GA4 reported 50 organic sessions on getduct.ai while Search Console reported 34 clicks over almost the same window. GA4's organic search channel counts sessions from every search engine, Bing and DuckDuckGo included, and a returning visitor can start more than one session. Search Console counts clicks from Google only. Expect the two to disagree, and compare trends within each tool rather than numbers across them.

## How do you read Search Console, GA4 and backlinks together?

**In a fixed order, so each step removes a way to fool yourself.**

1. **Take brand queries out.** What remains is the search you earned.
2. **Read position before impressions.** Impressions beyond page two say little about visibility.
3. **On page one, compare clicks to position.** Zero clicks at positions four to eight is a title problem or an intent problem, and you can tell which by reading the query.
4. **Join landing pages to key events in GA4.** A page that converts is worth more than a page that ranks.
5. **Only then decide what to do:** rewrite a title, write a page, or earn links. The first is cheapest, so check for it first.

I run the first three steps every week. Duct reads Search Console and GA4 together and asks the third question in its briefs through its ranking-without-clicks check in [checks.py](https://github.com/5hirish/duct/blob/main/backend/agents/insights/checks.py). It does not read backlinks, so the authority layer still comes from a separate tool. Choosing which searches to go after is the other half of the job, and [keyword gap analysis without a spreadsheet](/blog/keyword-gap-analysis-without-a-spreadsheet) is how I did it for this blog.

## FAQ

### Why are my impressions up but my clicks flat?

Usually because the new impressions are on page two or deeper, where a few people see a result and almost nobody clicks it. Read average position next to impressions. If the page is on page one and still gets no clicks, the title or snippet does not match what the searcher wants.

### Why does GA4 show different numbers from Search Console?

They measure different things. Search Console counts clicks from Google search results. GA4's organic channel counts sessions from every search engine, and one visitor can start several sessions. The two will not match; compare trends within each tool, not totals across them.

### Should I count branded searches as SEO growth?

Count them separately. A search for your brand name means the person already knew you, so it measures awareness built elsewhere. Organic growth is the non-branded search you earn. On a young site branded clicks can be most of the total, which makes a flat non-branded trend easy to miss.

### Do backlinks matter for a small site?

They decide which searches are winnable. A site with a few dozen referring domains can rank for low-difficulty searches that match its product, but not for broad, contested terms. Use your link count to choose targets, and spend the early effort on pages that answer a narrow question better than anything ranking now.
