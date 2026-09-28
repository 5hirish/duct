# Answer engines: what gets a page cited

The evidence behind the skill's structure rules, with sources. Read once;
re-check the sources when a rule here starts to look wrong, and date what you
change. Last verified 2026-09-28.

## How an answer engine uses a page

ChatGPT search, Perplexity, Google's AI Overviews and AI Mode, and Claude with
search all do roughly the same thing: run a search, fetch a handful of pages,
and write an answer from passages of them, citing the pages. Two consequences
drive everything else:

- **A page has to be in the search index first.** Search visibility is the
  entry ticket, not a separate game. Classic SEO (crawlable, fast, linked,
  about one thing) still decides whether a page is a candidate at all.
- **The unit that gets quoted is a passage, not a page.** A section that
  answers a question on its own can be lifted; one that depends on the
  paragraph before it cannot.

## The measured evidence

**GEO: Generative Engine Optimization** (Aggarwal et al., KDD 2024,
[arXiv 2311.09735](https://arxiv.org/abs/2311.09735)) is the one controlled
study worth knowing. It rewrote pages with nine methods and measured how much
of each page made it into generative-engine answers:

- The top three methods were **Cite Sources, Quotation Addition and
  Statistics Addition**: "a relative improvement of 30-40% on the
  Position-Adjusted Word Count metric and 15-30% on the Subjective Impression
  metric". The abstract's headline: "GEO can boost visibility by up to 40%".
- **Keyword stuffing did not help**: "such methods offer little to no
  improvement on generative engine's responses", and in one setting it
  performed 10% worse than the unmodified page.
- **Lower-ranked sites gained the most**: "lower-ranked websites, which
  typically struggle for visibility, benefit significantly more from GEO".
  That is the case for a young domain like getduct.ai.

This is where the skill's rules come from: sourced numbers, verbatim quotes
from primary sources, citations inline, and no keyword padding.

**Google, [AI features and your website](https://developers.google.com/search/docs/appearance/ai-features)**
(Search Central, updated 2025-12-10) says the rest plainly: "There are no
additional requirements to appear in AI Overviews or AI Mode, nor other
special optimizations necessary." Its list is the classic one: crawlable,
internally linked, important content in text, good page experience,
supporting images, and **structured data that matches the visible page**. It
also says "You don't need to create new machine readable files, AI text files,
or markup to appear in these features", which is why `llms.txt` stays cheap
and low-priority here rather than a strategy.

## Access: the crawlers

A page an engine cannot fetch cannot be cited. Vendors split their crawlers by
purpose, which is why `site/robots.txt` names them one by one:

- **OpenAI** ([docs](https://developers.openai.com/api/docs/bots)):
  `OAI-SearchBot` decides ChatGPT search visibility ("Sites that are opted out
  of OAI-SearchBot will not be shown in ChatGPT search answers"); `GPTBot` is
  training; `ChatGPT-User` is a user-initiated fetch.
- **Anthropic**: `Claude-SearchBot` for search, `ClaudeBot` for training,
  `Claude-User` for user-initiated fetches.
- **Perplexity**: `PerplexityBot` for its index, `Perplexity-User` for fetches.

And the page has to be HTML the crawler can read without running JavaScript.
That is why posts are pre-rendered (`scripts/build_blog.py`): measured against
production, GPTBot used to receive 49 characters of a 6,000-word post.

## What the generator already does

Every post gets, without the author doing anything:

- static HTML with the nav and footer inlined (crawlable links)
- `BlogPosting` with `headline`, `description`, `datePublished`,
  `dateModified` (from `updated`), `author` with `sameAs`, `keywords` (the
  tags), `wordCount`, `image`, and a **`citation` list of every outside source
  linked in the body**
- `BreadcrumbList`, and `FAQPage` built from the `## FAQ` section's own text
- an anchor id on every heading, and a contents list on long posts, so an
  engine can cite a section and a reader lands on it
- `article:tag` and `article:section` meta for the category and tags

What it cannot do is make the passages worth quoting. That is Phases 1–3.

## Off the page: being mentioned

Engines choose among pages the search index already trusts, and trust comes
from other places linking and talking about a page. For a small site the
cheapest mentions are the ones where the post genuinely helps: a correction
PR to a list it found errors in, an answer in a thread that asked its
question, an entry in an index that covers its topic. This is Phase 7, and
it is not optional: a page nobody links to is rarely a page anyone cites.

## Measuring it

Without a paid AI-visibility tool, measure three ways, at 30 and 90 days:

1. **Prompt panel.** The brief's primary and secondary questions, asked in the
   same engines each time. Record whether getduct.ai is cited, and which page.
2. **Referrals.** GA4 sessions from `chatgpt.com`, `perplexity.ai`,
   `gemini.google.com`, `claude.ai`, `copilot.microsoft.com`. Small numbers,
   but they are the ones that became visits.
3. **Search Console.** Queries and position for the post. An answer engine
   rarely cites a page that ranks nowhere.

Duct reads getduct.ai's own GA4 and Search Console, so ask it.
