# Launch check: the checklist

Every check has an id, the area it scores in, where to look (`live`, `repo` or
`both`) and what makes it FAIL or WARN. Anything else that holds is PASS.
Anything you could not see is UNVERIFIED and costs nothing.

Severity follows one rule: **FAIL blocks the launch from being found, shared or
measured. WARN makes it worse. Polish is not a finding**; mention it under
"Everything else" without a severity if at all.

Never FAIL or WARN on: a title or description within 10 characters of a
limit, missing structured data, keyword density, word count on a landing page,
or page speed you did not measure.

## Measurement (25)

The area only a repository can settle. A launch that is not measured cannot be
learned from, even when it works.

| id | where | FAIL | WARN |
|---|---|---|---|
| M1 tag present | both | No analytics on the homepage, live or in the repo, and the action happens on the site (signup, purchase, a download served from the site) | No analytics, but the action happens off the site and has a public counter (npm, PyPI or crates downloads, GitHub release `download_count`, stars): installs are counted, not attributed to any page or post. The repo or privacy policy saying "no analytics, deliberately": UNVERIFIED, and name the counter |
| M2 tag everywhere | both | | Tag loads on some sampled pages and not others (a second layout, the docs, the blog) |
| M3 tag ships to production | repo | Tag is rendered only when an env variable is set and nothing you can see sets it for production, or it is gated on `NODE_ENV === "development"` | Variable is set only in a dashboard you cannot see: say so, UNVERIFIED unless the live page also lacks the tag |
| M4 not blocked | repo | A Content-Security-Policy in the repo (`_headers`, `vercel.json`, `next.config.*`, a meta tag) omits the analytics host, so the browser refuses the script The conversion event waits for a consent choice and is dropped when none is made, so some launch visitors go uncounted. The gate is often the law; the fix is a cookieless second count (release `download_count`, server-side signups), never removing the gate |
| M5 conversion event | repo | The one action sends no event anywhere: no client call on the button or form, no server-side capture on the route that creates the account, order or download | The event fires on click but not on success (form submitted, account created), so failures count as conversions |
| M6 outbound conversion | repo | The action is a link off the site (GitHub Releases, App Store, Gumroad, Stripe Checkout) with no click event and no UTM or referral parameter | |
| M7 event name is stable | repo | | Event name is built from page text or differs between buttons for the same action (`Download`, `download_click`, `dl`), so the count is split |
| M8 search console | live | | No `google-site-verification` meta, no verification file in the repo, and no DNS method mentioned in the repo docs: UNVERIFIED rather than WARN when DNS verification is plausible |

Patterns to search for (case-insensitive) when looking for a tag or an event:

```
gtag(  googletagmanager.com  GTM-  G-[A-Z0-9]{6,}  dataLayer.push
posthog.init  posthog.capture  usePostHog  capture(
plausible.io/js  plausible(  data-domain=
umami  data-website-id  umami.track  data-umami-event
fathom  trackEvent(  trackGoal(
@vercel/analytics  <Analytics  va.track  track(
mixpanel.init  mixpanel.track  amplitude  segment  analytics.track
static.cloudflareinsights.com  data-cf-beacon
matomo  _paq.push  simpleanalytics  pirsch  openpanel  rybbit
```

Where events hide: the button component (`onClick`), the form `onSubmit`, a
`/api/*` or server action that creates the user, a Stripe webhook handler, a
`useEffect` on the success page, a `data-*` attribute read by a delegated
listener in one shared script.

## Claims (20)

The area a launch audience scores for you, in the comments. Every concrete
promise on the homepage, in its demo and in the latest release notes, checked
against the code. Found by `both` at best: the page states it, the repository
settles it.

| id | where | FAIL | WARN |
|---|---|---|---|
| K1 the demo works | both | The homepage's own example question, demo or screenshot shows a capability the shipped product lacks (a data source the feature cannot read, a step the code does not do) | The demo shows it, but only another surface does it (a scheduled job, a paid tier, a self-hosted build) and the page does not say so |
| K2 the price and sign-in | both | The first screen promises a price, free tier or sign-in method the code does not implement, or implements against the provider's published terms | The promise holds but depends on a flag, beta or region the page does not mention |
| K3 counts and lists | both | | A number on the page (integrations, languages, users) disagrees with the code, the docs or another page of the same site |
| K4 release notes | both | The latest release notes say something was added or removed that the live site or the code contradicts (a tracker "removed" that still loads) | Release notes describe a change the page has not caught up with |

Read only the claims you can settle in a few searches; the rest are
UNVERIFIED. Never FAIL a claim on a guess about intent: quote the page, cite
the `path:line` that contradicts it.

## Search (20)

From the audit agent's technical and on-page rules, cut to what a launch needs.

| id | where | FAIL | WARN |
|---|---|---|---|
| S1 indexable | live | `noindex` (meta or `X-Robots-Tag`) on the homepage or the action's page, or `robots.txt` disallows `/` | `noindex` on a docs or blog page that should rank (fine on /privacy, /terms, thank-you pages) |
| S2 title | live | `<title>` missing on a key page, or the same title on two or more sampled pages | Under 30 or over 60 characters; or only the brand name |
| S3 description | both | | Missing or over 160 characters on the homepage or the action's page (elsewhere, list it under "Everything else"). Many at once usually means a template fallback; find it |
| S4 canonical | both | Canonical points at another domain (a `*.vercel.app` preview, an old domain, `localhost`) | Missing; or points at a different path than the page itself |
| S5 one H1 | live | | No `<h1>`, or the H1 does not say what the page is (only the logo) |
| S6 sitemap | both | One file over 50,000 URLs or 50 MB uncompressed: search engines can reject the whole file (split it with a sitemap index) | No sitemap at `robots.txt`'s `Sitemap:` or `/sitemap.xml`; it lists URLs that redirect or 404; or every `lastmod` is today because the generator stamps the clock |
| S7 HTTPS and redirects | live | Homepage over plain HTTP with no redirect | More than one redirect hop to reach the homepage |
| S8 rendered HTML | live | | The raw HTML body is an empty app shell: crawlers that skip JavaScript see no text |
| S9 base-URL source | repo | The site config that builds canonicals, sitemap and `og:url` (`metadataBase`, `site`, `url`, `site_url`, `baseURL`, `siteUrl`) names a domain that is not the live one | |
| S10 review markup | both | | `Review` or `AggregateRating` JSON-LD that is copied from another site (Trustpilot, G2, the App Store), hardcoded, or not visible on the page. Google's review snippet rules forbid all three and a manual action removes rich results site-wide |

## Social card (15)

The audit agent weighs this at 1% because it does not move rankings. For a
launch it is the first thing anyone sees: the link is shared before it is
searched.

| id | where | FAIL | WARN |
|---|---|---|---|
| C1 image exists | both | `og:image` on the homepage missing, relative, or not returning 200 with an `image/*` type | Same on another key page |
| C2 image source | repo | The file `og:image` names is not in a folder the build serves (for example in `src/` or `assets/` rather than `public/`), or is built by a script nothing runs | |
| C3 image size | live | | Smaller than 600x315, or not about 1.91:1 (1200x630 is the target). Read the size from the file header or the repo file |
| C4 title and description | live | | `og:title` or `og:description` missing on the homepage |
| C5 twitter card | live | | No `twitter:card`, or `summary` (small) on the homepage where `summary_large_image` fits |
| C6 one card per page | live | | Every sampled page shares the homepage's exact card, including posts that would be shared on their own |

## Answer engines (10)

What ChatGPT, Perplexity, Google AI Overviews and Claude can read and cite.

| id | where | FAIL | WARN |
|---|---|---|---|
| A1 AI crawlers allowed | both | `robots.txt` disallows `/` for GPTBot, OAI-SearchBot, ChatGPT-User, ClaudeBot, Claude-SearchBot, PerplexityBot or Google-Extended | A CDN or host setting in the repo blocks AI bots (for example a bot-fight rule in config) |
| A2 llms.txt | live | | `/llms.txt` missing, or under 200 characters, or it names no pages |
| A3 structured data | live | | The homepage JSON-LD has a type that does not match the page (a `BlogPosting` on a product home); absence is not a finding |
| A4 answer first | live | | The first 200 characters of the homepage's main content (after the navigation) never say what the product is and who it is for in plain words |
| A5 facts are text | live | | Pricing, install command or key claims exist only inside images or a video |

## First impression (10)

From the readiness audit's copy rules. One screen, a cold visitor, five seconds.

| id | where | FAIL | WARN |
|---|---|---|---|
| F1 who and what | live | | The first screen's headline and subhead do not say who it is for and what they get |
| F2 one primary action | live | The action's link or form is broken (404, `href="#"`, points to localhost) | Two or more competing primary buttons; or the action is not on the first screen |
| F3 action copy | live | | The button says "Learn more", "Get started" or "Submit" where the outcome could be named ("Download for macOS", "Start free") |
| F4 proof | live | | No proof anywhere on the homepage (users, stars, logos, a quote, a demo) |
| F5 dead links | live | A link in the main navigation returns 404 | A footer or docs link returns 404 |

## Impact guide for ranking

| Finding type | Typical impact | Typical effort |
|---|---:|---:|
| Conversion event missing (M5, M6) | 3 | 1 |
| Homepage demo or first-screen promise the product breaks (K1, K2) | 3 | 1-3 |
| Release notes contradict the site (K4) | 2 | 1 |
| A count that disagrees (K3) | 1 | 1 |
| Tag not shipping or blocked (M1, M3, M4) | 3 | 1-2 |
| Homepage noindex or robots block (S1) | 3 | 1 |
| Canonical or base URL on the wrong domain (S4, S9) | 3 | 1 |
| Social image missing or 404 (C1, C2) | 3 | 1 |
| Sitemap over the size limit (S6) | 3 | 2 |
| Copied or hidden review markup (S10) | 2 | 1 |
| AI crawlers blocked (A1) | 2 | 1 |
| Duplicate or missing titles (S2) | 2 | 1-2 |
| Weak first screen (F1, F3) | 2 | 2 |
| llms.txt missing (A2) | 1 | 1 |
