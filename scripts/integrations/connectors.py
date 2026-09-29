"""The hand-written half of the integrations pages (scripts/build_integrations.py).

Everything a page states about a connector's data or its changes is read from
the backend: the entity catalogues (what it reads), the executor registry and
the auto-apply allowlist (what it can change, and when a change waits), and
ConnectorMeta (how you sign in). What lives here is what code cannot say: the
questions a person asks, the rules from the knowledge pack in plain words, the
setup steps, and the FAQ.

Rules for editing:

- A claim about behaviour names code that does it. "Duct refuses to apply over
  a budget that moved" is here because google_ads_exec.py declares drift keys;
  a sentence nobody can point at does not go in.
- `joins` and `pairs` name connector ids from this file. The generator fails on
  an unknown one, so a question cannot promise a join Duct cannot make.
- `featured` makes a connector the hub's one wide card, first in its group,
  with that line under its name. One at a time: a page with two heavy
  elements has none (DESIGN.md, "Break the uniform grid").
- A connector without `page` is listed on the hub and gets no page of its own.
  Give it one when its copy is written, not before: a thin page is worse than
  a card.
- `reads` is only for connectors with no entity catalogue. Keep it to what the
  fetch module named in `source` actually pulls.
- `api` is how the API version reads on the page. `{api_version}` is filled
  from the catalogue, `{stripe_version}` from service/stripe/client.py and
  `{meta_version}` from service/meta/ads/client.py, so a version bump reaches
  the page without anyone editing it.
- `shot` is the session that connector answers, from CONNECTOR_SESSIONS in
  app/src/lib/__fixtures__/solo-story.mjs, shot by scripts/shots/shoot.mjs and
  copied into site/assets/media with its variants. The generator fails on a
  page without one, or one whose file is missing.
"""

#: Hub sections, in order.
GROUPS = [
    ("ads", "Ads"),
    ("analytics", "Analytics and search"),
    ("product", "Product and experiments"),
    ("revenue", "Revenue"),
]

#: The one answer the site gives about money (site/AGENTS.md, new-page skill).
FREE_ANSWER = (
    "Yes. Duct is free with your own model keys or the ChatGPT plan you already have, "
    "and the core is MIT licensed. A paid plan later bundles the models; nothing open "
    "today moves behind it. <a href=\"/open-source#pricing\">What will cost money</a>."
)

#: Where connector credentials live, true of the downloaded app (site/AGENTS.md).
CREDENTIALS = (
    "Keys and tokens are stored encrypted by Duct's hosted API, never in your browser, "
    "and you can remove a connection at any time. A self-host build keeps them on your own machine."
)

CONNECTORS = [
    # ── Ads ────────────────────────────────────────────────────────────────
    {
        "id": "google_ads", "slug": "google-ads", "name": "Google Ads", "group": "ads",
        "logo": "google-ads.svg", "meta": "backend/service/google/ads.py", "label": "Google Ads",
        "card": "Spend, clicks, conversions and ROAS, per campaign and search term.",
        "auth": "Sign in with Google", "pack": "backend/agents/knowledge/google_ads.md",
        "api": "Google Ads API {api_version}",
        "page": {
            "title": "Google Ads AI agent that waits for your Apply | Duct",
            "description": "Duct reads Google Ads beside GA4 and Stripe, finds the spend that never paid, and proposes the fix: negatives, budgets, bids. Nothing runs until you Apply.",
            "og_description": "Google Ads read next to GA4 and Stripe. Eight kinds of change, each proposed with what it touches and rolled back on request.",
            "twitter_description": "Find the Google Ads spend that never became revenue, then fix it with one click you control.",
            "experiment": "An evaluator from a 'google ads ai' search (320/mo, KD 35) or from the hub decides faster when the page names the eight real changes and the rule that none runs without them. Measured by download clicks per visit, split by landing page.",
            "h1": "Google Ads, <em>read next to your revenue.</em>",
            "sub": "Duct joins your campaigns and search terms with GA4 and Stripe, then proposes the change. Eight kinds of change, and each one waits for your Apply.",
            "shot": {"file": "paid-session", "alt": "A Duct session: asked where the ads budget is leaking, Duct reads Google Ads campaigns and search terms beside GA4 and Stripe, proposes a pause, two negatives and a budget raise, and writes the spend brief", "caption": "Ask where the budget leaks. Duct costs every campaign against your CPA target and proposes the pause, the negatives and the budget shift. The one over the guardrail waits for you."},
            "hero": {
                "joins": ["google_ads", "ga4", "stripe"],
                "answer": "Six search terms spent $2,140 this month. None of them became a paying customer.",
                "change": ("Add 6 negative keywords", "Touches 2 campaigns. Rollback ready."),
            },
            "questions": [
                ("Which search terms spend money and never become a paying customer?", ["google_ads", "stripe"]),
                ("Google Ads says 120 conversions. How many of them paid?", ["google_ads", "stripe"]),
                ("GA4 sees 60% of my Ads clicks. Is auto-tagging broken?", ["google_ads", "ga4"]),
                ("Which campaign can take more budget without raising cost per customer?", ["google_ads", "ga4", "stripe"]),
            ],
            "knows": [
                ("Removed is forever, so Duct pauses.",
                 "Google Ads cannot bring back a removed campaign, ad group or keyword. Duct only proposes a pause, which rolls back."),
                ("Shared budgets move together.",
                 "Change a shared budget and every campaign on it changes too. The preview says how many campaigns before you apply."),
                ("Your approval is for the number you saw.",
                 "If someone changes the budget, bid or status after you approved, Duct refuses to apply over it."),
                ("Every platform claims the same sale.",
                 "Google counts the last click, Meta counts a seven-day click and a one-day view, and both count the same purchase. Duct checks the total against Stripe."),
            ],
            "pairs": [
                ("stripe", "Which campaigns bring customers who actually pay?"),
                ("ga4", "Do your Ads clicks arrive as tagged sessions?"),
                ("meta_ads", "Which platform buys a customer for less?"),
            ],
            "setup": [
                "In Duct, open Connections and choose Google Ads.",
                "Sign in with Google and allow access.",
                "Pick the account this project reads. On a manager (MCC) account, add its ID and Duct reads the accounts under it.",
            ],
            "permissions": "Google Ads offers one API permission, and it includes making changes; there is no read-only option. Duct's limit is in its code instead: the agent has no tool that approves a change, so the most it can do is propose one.",
            "faq": [
                ("Can Duct change my Google Ads without asking?",
                 "Not by default. Every change is a proposal that shows what it touches, and it runs when you press Apply. If you switch a project to assisted mode, adding keywords and negative keywords can apply on their own; budgets, bids and statuses always wait for you."),
                ("Which changes can Duct make in Google Ads?", "{changes}"),
                ("Does it work with a manager (MCC) account?",
                 "Yes. Add the manager account's ID when you connect, and Duct reads the client accounts under it."),
                ("How is this different from the AI inside Google Ads?",
                 "Google's own tools see Google Ads. Duct reads Google Ads beside GA4 and Stripe, so it can say which campaigns bring customers who pay, and it reads Meta, Apple and ChatGPT ads the same way."),
                ("Is it free?", "{free}"),
            ],
        },
    },
    {
        "id": "meta_ads", "slug": "meta-ads", "name": "Meta Ads", "group": "ads",
        "logo": "meta.svg", "meta": "backend/service/meta/ads/fetch.py", "label": "Meta Ads",
        "card": "Facebook and Instagram spend, reach, conversions and CPA.",
        "auth": "System User token", "pack": "backend/agents/knowledge/meta.md",
        "source": "backend/service/meta/ads/fetch.py", "checked": "2026-09-29",
        "api": "Meta Marketing API {meta_version}",
        "reads": [
            ("Campaigns, every status", ["name", "status", "objective", "bid strategy", "daily budget", "lifetime budget", "spend cap"]),
            ("Ad sets and ads", ["name", "status", "daily budget", "optimization goal", "bid amount", "attribution setting"]),
            ("Performance", ["spend", "impressions", "clicks", "CTR", "CPC", "CPM", "purchases", "purchase value", "ROAS"]),
            ("Pixels and custom conversions", ["name", "last fired", "event type", "default value"]),
        ],
        "page": {
            "title": "Meta Ads AI analyst: purchases counted once | Duct",
            "description": "Duct reads Meta Ads with a System User token, counts each purchase once on the attribution window you choose, and checks it against Stripe. Read-only.",
            "og_description": "Meta's ROAS looks three times better than Google's. Duct recounts it the way Google counts, checks it against Stripe, and says which is right.",
            "twitter_description": "Meta can count one purchase three times. Duct counts it once, then checks Stripe.",
            "experiment": "Meta Ads has open search around AI tooling ('meta ads mcp' 880 a month, KD 8, OpenSEO Sep 2026), though Duct has no MCP server yet. Hypothesis: a buyer who already distrusts Meta's attribution converts on the recount, not on a feature list. Measured by download clicks per visit.",
            "h1": "Meta Ads, <em>counted once.</em>",
            "sub": "Meta credits itself with a week of clicks and a day of views, and can report one purchase three times. Duct reads Meta Ads, recounts on the window you choose, and checks the result against Stripe.",
            "shot": {"file": "session-meta-ads", "alt": "A Duct session: asked why Meta looks cheaper than Google, Duct reads Meta ad sets and insights on three attribution windows beside Google Ads, and recounts purchases on one-day click", "caption": "Ask why Meta looks three times cheaper. Duct recounts its purchases the way Google counts, one action type and a one-day click, and puts the two side by side."},
            "hero": {
                "joins": ["meta_ads", "google_ads", "stripe"],
                "answer": "Meta claims 41 purchases at €34. On one-day click it's 14, at €100. Google is at €105.",
            },
            "questions": [
                ("Is Meta really cheaper than Google, counted the same way?", ["meta_ads", "google_ads"]),
                ("Which ad sets bring customers who pay?", ["meta_ads", "stripe"]),
                ("How much of Meta's credit comes from views, not clicks?", ["meta_ads"]),
                ("Why did a campaign stop getting results?", ["meta_ads"]),
            ],
            "knows": [
                ("One purchase, three action types.",
                 "The same order can arrive as a pixel purchase, a purchase and an omni purchase. Summing them triples the count, so Duct picks one."),
                ("Attribution is a choice, not a fact.",
                 "Meta defaults to seven-day click and one-day view; Google counts the last click. Duct asks Meta for one-day click, seven-day click and one-day view separately, so the platforms can be compared on the same terms."),
                ("Paused history is hidden by default.",
                 "Without a status list Meta returns only active campaigns. Duct asks for every status, so what was switched off last month is still in the audit."),
                ("Budgets come back in cents.",
                 "Meta reports budgets in minor units and spend in whole currency. Read as euros, a €25 daily budget becomes €2,500."),
            ],
            "pairs": [
                ("stripe", "Does Meta's purchase count survive Stripe?"),
                ("google_ads", "Meta and Google, counted the same way."),
                ("ga4", "Do Meta clicks become sessions that stay?"),
            ],
            "setup": [
                "In Meta Business Settings, open Users, then System users, and give one access to the ad account.",
                "Generate a token for it with ads_read (and business_management, so Duct can list your accounts).",
                "In Duct, open Connections, choose Meta Ads and paste the token.",
            ],
            "permissions": "Read-only: the token needs ads_read, and Duct has no Meta change operation. A System User token does not expire the way a person's login does.",
            "faq": [
                ("Can Duct change my Meta campaigns?",
                 "No. Duct has no Meta change operation. It reads campaigns, ad sets, ads, pixels and results, and can recommend a change for you to make in Ads Manager."),
                ("Why doesn't Meta's purchase count match Stripe?",
                 "Meta credits itself with purchases up to seven days after a click and a day after a view, and can report one order under three action types. Stripe counts money that settled. Duct counts each purchase once, on the window you pick, and reconciles against Stripe."),
                ("Why a System User token and not my own login?",
                 "A token made from a person's login expires after about 60 days, and the connection stops without warning. A System User token does not expire, so the weekly brief keeps working."),
                ("My ad account runs ads for two products. Can Duct keep them apart?",
                 "Yes. Give it the part of the campaign names that marks this product, and Duct filters to those campaigns before Meta adds anything up, so the other product never reaches the totals."),
                ("Is it free?", "{free}"),
            ],
        },
    },
    {
        "id": "apple_ads", "slug": "apple-search-ads", "name": "Apple Search Ads", "group": "ads",
        "logo": "apple-search-ads.svg", "meta": "backend/service/apple/ads/fetch.py", "label": "Apple Search Ads",
        "card": "Spend, taps and installs, by campaign and search term.",
        "auth": "API key pair", "pack": "backend/agents/knowledge/apple_ads.md",
        "source": "backend/service/apple/ads/fetch.py", "checked": "2026-09-29",
        "api": "Apple Search Ads Campaign Management API v5",
        "reads": [
            ("Campaigns", ["name", "status"]),
            ("Campaign report, this period and the last", ["impressions", "taps", "tap-through installs", "total installs", "spend", "average cost per tap"]),
            ("Daily campaign report", ["impressions", "taps", "installs", "spend"]),
        ],
        "page": {
            "title": "Apple Search Ads AI analyst: installs to subscribers | Duct",
            "description": "Duct reads Apple Search Ads campaign reports, scoped to your app's campaigns, and checks the installs against RevenueCat and Stripe. Read-only, key pair.",
            "og_description": "Apple reports installs, never subscribers. Duct reads Apple Search Ads beside RevenueCat and says which campaigns bring people who pay.",
            "twitter_description": "Installs are Apple's number. Subscribers are yours. Duct reads both.",
            "experiment": "Per-tool integration searches run 10 to 50 a month (OpenSEO, Sep 2026), so this page is for the app marketer who reached Duct another way. Hypothesis: showing installs joined to subscribers converts better than a feature list. Measured by download clicks per visit.",
            "h1": "Apple Search Ads, <em>past the install.</em>",
            "sub": "Apple reports installs and stops there. Duct reads your campaigns beside RevenueCat and Stripe, and says which ones bring subscribers, not just downloads.",
            "shot": {"file": "session-apple-search-ads", "alt": "A Duct session: asked whether a bid raise paid off, Duct reads Solo's Apple Search Ads campaigns day by day beside RevenueCat and finds installs doubled while trials did not move", "caption": "Ask whether the bid raise paid. Apple reports installs, so Duct checks them against RevenueCat trials, scoped to your app's campaigns."},
            "hero": {
                "joins": ["apple_ads", "revenuecat"],
                "answer": "Discovery's installs doubled after the bid raise. Active trials in RevenueCat didn't move.",
            },
            "questions": [
                ("Did the bid raise buy subscribers, or only installs?", ["apple_ads", "revenuecat"]),
                ("Which campaigns should get next month's budget?", ["apple_ads", "revenuecat"]),
                ("What does an install cost this month against last?", ["apple_ads"]),
                ("How many installs came from a tap, and how many from a view?", ["apple_ads"]),
            ],
            "knows": [
                ("Apple counts installs, never money.",
                 "There is no revenue or subscriber metric in Apple Search Ads. Duct judges a campaign against RevenueCat or Stripe, not against its installs."),
                ("Reports cover the whole organisation.",
                 "Apple's campaign reports mix every app in the org. Duct filters them to your campaigns first, so another app's spend can't reach your totals."),
                ("Installs were renamed.",
                 "Version 5 of the API split installs into tap-through and total, which includes view-through. The old field reads as zero, so Duct reads both new ones."),
                ("Money arrives as text.",
                 "Apple returns every amount as a string with its currency. Duct parses each one before adding anything up."),
            ],
            "pairs": [
                ("revenuecat", "Installs in, subscribers out."),
                ("stripe", "Which campaigns bring customers who pay?"),
                ("google_ads", "One search budget, split between Google and Apple."),
            ],
            "setup": [
                "Generate an EC P-256 key pair, and upload the public key in Apple Search Ads under Account Settings, then API.",
                "Note the client ID, team ID and key ID Apple shows for it.",
                "In Duct, open Connections, choose Apple Search Ads and paste the three IDs and the private key.",
            ],
            "permissions": "Read-only: Duct has no Apple Search Ads change operation, and give the API user a read-only role so the key could not change a campaign either.",
            "faq": [
                ("Can Duct change bids or budgets in Apple Search Ads?",
                 "No. Duct has no Apple Search Ads change operation. It reads campaigns and their reports and can recommend a change for you to make in Apple's console."),
                ("Why does Duct need RevenueCat or Stripe for Apple?",
                 "Because Apple stops at the install. Whether those installs started a trial or paid is in your billing, so Duct reads it beside Apple before calling a campaign good or bad."),
                ("Our Apple Ads org runs more than one app. Will the numbers mix?",
                 "No. Duct conditions every report on the campaigns it lists for you, so another app's spend never reaches those totals."),
                ("Is it free?", "{free}"),
            ],
        },
    },
    {
        "id": "openai_ads", "slug": "chatgpt-ads", "name": "ChatGPT Ads", "alias": "OpenAI Ads", "group": "ads",
        "logo": "openai-ads.svg", "meta": "backend/service/openai/ads/fetch.py", "label": "OpenAI Ads",
        "card": "Impressions, clicks and spend. Conversions stay in Ads Manager.",
        "featured": "ChatGPT's ads report clicks and spend, not conversions. Duct measures the channel against what Stripe settled.",
        "auth": "Ads API key", "pack": "backend/agents/knowledge/openai_ads.md",
        "source": "backend/service/openai/ads/fetch.py", "checked": "2026-09-29",
        "api": "OpenAI Ads API v1",
        "reads": [
            ("Ad account", ["name", "currency"]),
            ("Campaigns", ["name"]),
            ("Campaign performance", ["impressions", "clicks", "spend", "ctr", "cpc", "cpm"]),
            ("Daily account totals", ["impressions", "clicks", "spend"]),
        ],
        "page": {
            "title": "ChatGPT Ads, measured against real revenue | Duct",
            "description": "Connect ChatGPT Ads (OpenAI Ads) to Duct and read its spend beside Stripe and GA4. The Ads API reports no conversions, so Duct judges the channel on revenue.",
            "og_description": "ChatGPT Ads reports clicks and spend, not conversions. Duct reads it beside Stripe and GA4, so you see what the clicks bought.",
            "twitter_description": "The OpenAI Ads API has no conversions. Duct measures ChatGPT Ads against the revenue Stripe settled.",
            "experiment": "'chatgpt ads' is 14,800 searches a month at KD 12, and its page one is OpenAI, Reddit and news. Hypothesis: advertisers testing the new channel want a way to measure it, and the gap the API leaves (no conversions) is the reason to install. Measured by download clicks per visit and GSC impressions for chatgpt ads queries.",
            "h1": "ChatGPT Ads, <em>judged on revenue.</em>",
            "sub": "The OpenAI Ads API reports impressions, clicks and spend. No conversions. Duct reads it beside Stripe and GA4, so you see what the clicks actually bought.",
            "shot": {"file": "session-chatgpt-ads", "alt": "A Duct session: asked what ChatGPT Ads is buying, Duct reads its spend and clicks, follows them through GA4 to Stripe, and writes a brief costing the channel per paying customer", "caption": "Ask what ChatGPT Ads is buying. Its own report ends at the click, so Duct follows the clicks through GA4 to Stripe and costs the channel per paying customer."},
            "hero": {
                "joins": ["openai_ads", "stripe", "ga4"],
                "answer": "312 clicks from ChatGPT this month. Nine became paying customers in Stripe: $204 each.",
            },
            "questions": [
                ("What did this month's ChatGPT Ads spend buy, in money Stripe settled?", ["openai_ads", "stripe"]),
                ("Do visitors from ChatGPT engage on the landing page, or leave?", ["openai_ads", "ga4"]),
                ("Cost per paying customer: ChatGPT Ads or Google Ads?", ["openai_ads", "google_ads", "stripe"]),
                ("Which ChatGPT campaign has earned next week's budget?", ["openai_ads", "stripe", "ga4"]),
            ],
            "knows": [
                ("The Ads API cannot see conversions.",
                 "Its metrics are impressions, clicks, spend, CTR, CPC and CPM. Pixel conversions show only in Ads Manager, so Duct never calls the channel good on CPC alone. It checks Stripe."),
                ("Two units from one vendor.",
                 "Insights report spend as a decimal (18.42); the pixel reports cents (1499). Mixing them is a 100× error, so Duct converts before it compares."),
                ("One key, one ad account.",
                 "An Ads API key reaches exactly one ad account. Duct reads which one first, so a key from the wrong account says so instead of looking empty."),
                ("Only the biller knows.",
                 "Every ad platform reports conversions it attributes to itself. Duct reconciles them against Stripe, never against each other."),
            ],
            "pairs": [
                ("stripe", "What did ChatGPT clicks turn into, in settled revenue?"),
                ("ga4", "Do ChatGPT visitors behave like search visitors?"),
                ("google_ads", "Which channel buys a paying customer for less?"),
            ],
            "setup": [
                "In OpenAI Ads Manager, create an Ads API key for the ad account you want read.",
                "In Duct, open Connections, choose OpenAI Ads and paste the key.",
                "Duct shows which ad account the key belongs to, then reads its campaigns and daily totals.",
            ],
            "permissions": "An Ads API key is scoped to one ad account, and OpenAI grants API access per account while the API is in beta. Duct uses the key only to read; it has no ChatGPT Ads change operation.",
            "faq": [
                ("Can Duct see ChatGPT Ads conversions?",
                 "No, because the OpenAI Ads API does not report them; pixel conversions show only in Ads Manager. Duct measures the channel against what Stripe settled and what GA4 saw, which is the number that decides the budget anyway."),
                ("Does Duct change my ChatGPT Ads campaigns?",
                 "No. The connector is read-only. Duct can recommend moving budget between campaigns or channels; you make the change in Ads Manager."),
                ("Are ChatGPT Ads and OpenAI Ads the same thing?",
                 "Yes. OpenAI sells the ads that run in ChatGPT through its Ads Manager and Ads API. The Duct app lists the connector as OpenAI Ads."),
                ("Is it free?", "{free}"),
            ],
        },
    },
    # ── Analytics and search ───────────────────────────────────────────────
    {
        "id": "ga4", "slug": "ga4", "name": "Google Analytics 4", "short": "GA4", "group": "analytics",
        "logo": "googleanalytics.svg", "meta": "backend/service/google/ga4.py", "label": "Google Analytics 4",
        "card": "Traffic, sessions, engagement and conversions, per page and channel.",
        "auth": "Sign in with Google", "pack": "backend/agents/knowledge/ga4.md",
        "api": "Google Analytics Data API ({api_version})",
        "page": {
            "title": "GA4 AI analyst: why the numbers moved | Duct",
            "description": "Duct reads GA4 beside Search Console, your ads and Stripe, and answers why the numbers moved. It can add key events and audiences too, with your approval.",
            "og_description": "Ask GA4 why signups dropped and get an answer that reads Search Console, your ads and Stripe too, with the fix one click away.",
            "twitter_description": "GA4 read beside Search Console, ads and Stripe: the cause, not another dashboard.",
            "experiment": "GA4 has little tool-intent search of its own ('ga4 ai' 20/mo), so this page is for the evaluator who reached Duct another way and checks GA4 first. Hypothesis: naming the GA4 traps Duct already handles (internal traffic, bot bursts, renamed events) converts better than a feature list. Measured by download clicks per visit.",
            "h1": "GA4, <em>with the rest of the story.</em>",
            "sub": "Duct reads Google Analytics 4 beside Search Console, your ads and Stripe, and answers why a number moved. When the fix is in GA4, it proposes it and waits for you.",
            "shot": {"file": "product-session", "alt": "A Duct session: asked why activation dropped after an Android release, Duct reads GA4, Clarity and Stripe, finds the permission dead end and proposes two GA4 key events", "caption": "Ask why activation dropped. Duct splits GA4 either side of the release, finds the dead end, and proposes the two key events that will prove the fix."},
            "hero": {
                "joins": ["ga4", "gsc", "stripe"],
                "answer": "Organic sessions up 40%, Search Console clicks flat. A bot burst, not growth.",
                "change": ("Register sign_up as a key event", "Touches 1 property. Rollback ready."),
            },
            "questions": [
                ("Why did signups drop last week?", ["ga4", "google_ads", "gsc"]),
                ("Which landing pages convert organic visitors, and which only bounce them?", ["ga4", "gsc"]),
                ("Are staff and QA sessions inflating my conversion rate?", ["ga4"]),
                ("Do the users GA4 counts as converted show up as revenue?", ["ga4", "stripe"]),
            ],
            "knows": [
                ("GA4 counts your team as customers.",
                 "Out of the box it filters no internal traffic, so staff and QA sessions land in production numbers. Before Duct trusts a conversion count, it looks for clusters of users that look like a QA team."),
                ("Organic is checked against Search Console.",
                 "Bot bursts can log 40 times more organic sessions than Search Console clicks. Duct compares the two before it calls a week a collapse or a win."),
                ("Event names are exact.",
                 "sign_up and signup are two different events, and a rename zeroes the old series without warning. Duct checks for it before comparing periods."),
                ("New audiences start empty.",
                 "A GA4 audience only collects members from the day it is created. Duct says so when it proposes one."),
            ],
            "pairs": [
                ("gsc", "Is organic growth real, or a bot burst?"),
                ("google_ads", "Is paid traffic tagged, and does it convert?"),
                ("stripe", "Do GA4 conversions turn into revenue?"),
            ],
            "setup": [
                "In Duct, open Connections and choose Google Analytics.",
                "Sign in with Google and allow access.",
                "Pick the GA4 property this project reads.",
            ],
            "permissions": "Duct asks for read access and edit access when you sign in. Reading uses read access; edit access is only for the changes below, and each of them still waits for your Apply.",
            "faq": [
                ("What can Duct change in GA4?", "{changes}"),
                ("Does Duct need edit access to GA4?",
                 "Only for changes. Answers and briefs use read access. Key events, audiences and the Google Ads link need edit access, which Duct asks for when you sign in; a connection made without it stays read-only."),
                ("Why does Duct compare GA4 with Search Console?",
                 "Because GA4 alone can be fooled. Bot traffic logged as organic search once ran 40 times higher than real Search Console clicks for weeks, then stopped, and any baseline across that window reads as a collapse. Two sources that should agree are the check."),
                ("Is it free?", "{free}"),
            ],
        },
    },
    {
        "id": "gsc", "slug": "google-search-console", "name": "Google Search Console", "short": "Search Console", "group": "analytics",
        "logo": "googlesearchconsole.svg", "meta": "backend/service/google/gsc.py", "label": "Google Search Console",
        "card": "Search queries, clicks, impressions and average position.",
        "auth": "Sign in with Google", "pack": "backend/agents/knowledge/gsc.md",
        "api": "Search Console API ({api_version})",
        "page": {
            "title": "Search Console AI analyst: queries that convert | Duct",
            "description": "Duct reads Search Console query by page, up to 50,000 rows, and joins it to GA4, so it can say which searches bring trials and which only bring impressions.",
            "og_description": "Impressions up, trials flat? Duct reads Search Console query by page beside GA4 and finds the queries you rank for and don't convert.",
            "twitter_description": "Search Console, read to the long tail and joined to GA4.",
            "experiment": "'google search console mcp' has search demand, but Duct has no MCP server yet (#197). Hypothesis: an SEO lead who has watched impressions rise without trials converts on a page that shows query-by-page cannibalisation. Measured by download clicks per visit.",
            "h1": "Search Console, <em>down to the query that converts.</em>",
            "sub": "Duct reads the queries and pages in Search Console, and which query lands on which page, then joins it to GA4. So it can say what organic search is worth, not just how much of it there is.",
            "shot": {"file": "session-search-console", "alt": "A Duct session: asked why organic trials are flat while impressions rise, Duct reads Search Console queries and query by page beside GA4 and finds two pages splitting the same queries", "caption": "Ask why impressions rose and trials didn't. Duct reads query by page, finds two of your pages splitting one query, and joins it to trials in GA4."},
            "hero": {
                "joins": ["gsc", "ga4"],
                "answer": "Impressions up 23%, on invoicing queries at position 11. The tax pages still earn 61% of trials.",
            },
            "questions": [
                ("Impressions are up. Why are trials flat?", ["gsc", "ga4"]),
                ("Which of my pages compete for the same query?", ["gsc"]),
                ("Which pages just off page one are worth pushing?", ["gsc", "ga4"]),
                ("Is organic growth real, or bots?", ["gsc", "ga4"]),
            ],
            "knows": [
                ("The long tail is where the work is.",
                 "Search Console sorts by clicks and returns 25,000 rows at a time. Read short, and the zero-click impressions, the list of what to write next, disappear. Duct reads two pages, up to 50,000 rows."),
                ("Most clicks come without a query.",
                 "Google hides rare queries, so the page table shows several times the clicks of the query table. Duct uses pages for how much, and queries for which terms."),
                ("The last three days aren't final.",
                 "Final data zeroes the newest days, which reads like a cliff. Duct asks for all data, so the week ends where it really ends."),
                ("Query by page is the only view of cannibalisation.",
                 "Two of your pages splitting one query shows up nowhere else. Duct reads query and page together."),
            ],
            "pairs": [
                ("ga4", "Which searches bring visitors who stay?"),
                ("google_ads", "Are you paying for clicks you already rank for?"),
                ("clarity", "Pages that rank, then lose people on arrival."),
            ],
            "setup": [
                "In Duct, open Connections and choose Google Search Console.",
                "Sign in with Google and allow read access.",
                "Pick the property this project reads.",
            ],
            "permissions": "Read-only: Duct asks Google for Search Console read access and has no Search Console change operation.",
            "faq": [
                ("Can Duct change anything in Search Console?",
                 "No. It asks for read access only and has no Search Console change operation. It reads queries, pages and positions and can tell you what to change on your site."),
                ("Why does Duct's organic number differ from GA4's?",
                 "Search Console counts clicks from Google; GA4 counts sessions from every search engine. A GA4 figure one to three and a half times the Search Console one is normal. Far outside that, Duct suspects bots or a tagging break before reporting either number."),
                ("How much of my property does it read?",
                 "Up to 50,000 rows a window, two of Search Console's pages. Past that the rows are too small to change an answer."),
                ("Is it free?", "{free}"),
            ],
        },
    },
    {
        "id": "gtm", "slug": "google-tag-manager", "name": "Google Tag Manager", "short": "Tag Manager", "group": "analytics",
        "logo": "google-tag-manager.svg", "meta": "backend/service/google/gtm.py", "label": "Google Tag Manager",
        "card": "Tags, variables and container versions, staged, with rollback.",
        "auth": "Sign in with Google", "pack": "backend/agents/knowledge/gtm.md",
        "source": "backend/service/execution/gtm_exec.py", "checked": "2026-09-29",
        "api": "Tag Manager API v2",
        "reads": [
            ("Accounts and containers", ["account", "container", "public ID"]),
            ("Workspace tags and variables", ["name", "type", "parameters"]),
            ("Live container version", ["version ID"]),
        ],
        "page": {
            "title": "Tag Manager AI agent: tracking fixes with rollback | Duct",
            "description": "Duct finds broken tracking by reading GA4 beside Mixpanel, stages the Tag Manager fix in a workspace, and publishes only when you approve, rollback ready.",
            "og_description": "A tag can fire on every page and still send the wrong event. Duct finds it, stages the fix in Tag Manager, and waits for you before it publishes.",
            "twitter_description": "Tracking broke on Tuesday. Duct finds the tag, stages the fix, and waits for your publish.",
            "experiment": "Per-tool integration searches run 10 to 50 a month (OpenSEO, Sep 2026). Hypothesis: the growth lead whose funnel went to zero overnight converts on a page that shows the fix staged with a rollback target, because the publish is the part that scares people. Measured by download clicks per visit.",
            "h1": "Tag Manager, <em>with the rollback named first.</em>",
            "sub": "Duct notices when a count goes to zero, finds the tag behind it, and stages the fix in a workspace. A publish replaces your live container, so that step always waits for you, with the version to roll back to named.",
            "shot": {"file": "session-tag-manager", "alt": "A Duct session: asked why GA4 stopped counting an event on the web, Duct finds the tag a container version renamed, and proposes a workspace fix and a publish that waits for approval", "caption": "Ask why an event stopped counting. Duct finds the tag version 14 changed, stages the fix in a workspace, and holds the publish for you with version 14 as the rollback."},
            "hero": {
                "joins": ["gtm", "ga4", "mixpanel"],
                "answer": "Version 14 renamed the event the Connect bank tag sends. GA4 has counted zero since 9 Sep.",
                "change": ("Publish container version 15", "Replaces version 14 for every visitor. Rollback ready."),
            },
            "questions": [
                ("Why did an event stop counting in GA4 overnight?", ["gtm", "ga4", "mixpanel"]),
                ("Is the tag firing, or firing the wrong thing?", ["gtm", "ga4"]),
                ("Do web and app still send the same event names?", ["gtm", "mixpanel"]),
                ("Can you fix the tag and let me approve the publish?", ["gtm"]),
            ],
            "knows": [
                ("Nothing is live until it's published.",
                 "Edits in a workspace change nothing on your site. Duct stages its changes there, and the publish, which replaces the live container for every visitor, always waits for you."),
                ("The rollback target is read first.",
                 "Before a publish Duct records the version that is live, so a rollback republishes exactly what was there."),
                ("A tag that fires can still be broken.",
                 "A tag can fire on every page and send nothing useful. Duct checks what arrived in GA4 or Mixpanel, not the fire status."),
                ("Renames don't follow references.",
                 "Renaming a variable through the API leaves every tag pointing at the old name. Duct patches the tags in the same change, or doesn't rename."),
            ],
            "pairs": [
                ("ga4", "Which tag broke the key event?"),
                ("mixpanel", "Web and app, one event name."),
                ("clarity", "Did the new tag break the page?"),
            ],
            "setup": [
                "In Duct, open Connections and choose Google Tag Manager.",
                "Sign in with Google and allow access to edit and publish containers.",
                "Pick the container this project uses.",
            ],
            "permissions": "Duct asks for edit and publish access when you sign in, because both are needed to fix a tag. Edits stay in a workspace, and a publish always waits for your Apply.",
            "faq": [
                ("What can Duct change in Tag Manager?", "{changes}"),
                ("Will Duct publish to my live site on its own?",
                 "No. A publish replaces the live container for every visitor, so it always waits for you, whatever the project's autonomy. Workspace edits can apply on their own in assisted mode, and they change nothing live until a publish."),
                ("How does rollback work?",
                 "Before it publishes, Duct records the version that is live. Rolling back republishes that version, and the activity log shows both."),
                ("Is it free?", "{free}"),
            ],
        },
    },
    # ── Product and experiments ────────────────────────────────────────────
    {
        "id": "mixpanel", "slug": "mixpanel", "name": "Mixpanel", "group": "product",
        "logo": "mixpanel.svg", "meta": "backend/service/mixpanel/fetch.py", "label": "Mixpanel",
        "card": "Signups, logins and upgrades, one name across web and app.",
        "auth": "Service account", "pack": "backend/agents/knowledge/mixpanel.md",
        "api": "Mixpanel Query API ({api_version})",
        "page": {
            "title": "Mixpanel AI analyst: clean counts, web and app | Duct",
            "description": "Duct reads Mixpanel's key events with staff and QA accounts taken out, checks them against Stripe, and can annotate the timeline or hide a typo event.",
            "og_description": "Mixpanel sees every platform under one name, and every QA account too. Duct takes them out, checks Stripe, and marks the timeline.",
            "twitter_description": "Your upgrade spike was the QA team. Duct takes them out and checks Stripe.",
            "experiment": "Per-tool integration searches run 10 to 50 a month (OpenSEO, Sep 2026). Hypothesis: a product lead who has chased a spike that turned out to be test accounts converts on a page that shows them removed and checked against Stripe. Measured by download clicks per visit.",
            "h1": "Mixpanel, <em>without the QA team in it.</em>",
            "sub": "Mixpanel is the one count that spans web and app. Duct reads it with internal accounts taken out, checks it against Stripe, and keeps the timeline honest with annotations and a tidy Lexicon.",
            "shot": {"file": "session-mixpanel", "alt": "A Duct session: asked whether a release lifted upgrades, Duct reads Mixpanel with QA accounts removed, checks Stripe, and proposes a timeline annotation and hiding a typo event", "caption": "Ask whether the release lifted upgrades. Duct takes the QA accounts out, checks Stripe, and proposes an annotation and a Lexicon clean-up."},
            "hero": {
                "joins": ["mixpanel", "stripe"],
                "answer": "Upgrades up 18%, until the QA accounts come out. Then 4.0% against 4.1%.",
                "change": ("Annotate 2 Sep: Android rebuild", "A dated note on the timeline. Rollback ready."),
            },
            "questions": [
                ("Did the release move upgrades, or only the test accounts?", ["mixpanel", "stripe"]),
                ("Why does GA4 count fewer signups than Mixpanel?", ["mixpanel", "ga4"]),
                ("Which events have a typo twin still firing?", ["mixpanel"]),
                ("How many signups carry no campaign at all?", ["mixpanel"]),
            ],
            "knows": [
                ("Mixpanel has no internal-traffic filter.",
                 "Staff and QA accounts sit inside every funnel. Duct removes the patterns you name before it quotes a number, and says which it removed."),
                ("It's the count the others are checked against.",
                 "Web and app send the same event name to Mixpanel, so when GA4 or an ad platform disagrees, Duct treats the gap as a measurement bug until shown otherwise."),
                ("Typo events live forever.",
                 "An old misspelt event keeps firing from old app versions. Duct hides it in Lexicon rather than filtering every query, and never adds it to its twin."),
                ("Untagged is not organic.",
                 "Most signups carry no campaign tag at all. Duct won't count a missing tag as organic search."),
            ],
            "pairs": [
                ("stripe", "Upgrades counted, upgrades paid."),
                ("ga4", "One signup count, not two."),
                ("growthbook", "Is the test's metric the event you think it is?"),
            ],
            "setup": [
                "In Mixpanel, open Organization settings, then Service Accounts, and create one with access to this project.",
                "Note its username and secret, the project ID, and whether the project lives in the US, EU or India.",
                "In Duct, open Connections, choose Mixpanel and paste them.",
            ],
            "permissions": "Reading needs a service account with access to the project. The two changes below also need it to edit annotations and Lexicon, and by default each waits for your Apply.",
            "faq": [
                ("What can Duct change in Mixpanel?", "{changes}"),
                ("Why not a project token or API secret?",
                 "Neither can read Mixpanel's Query API. A service account can, and it is scoped to the projects you grant it."),
                ("My project is in the EU. Does that work?",
                 "Yes. Pick the region when you connect and Duct reads from that region's host. A key that works but is refused usually means the region is wrong."),
                ("Is it free?", "{free}"),
            ],
        },
    },
    {
        "id": "clarity", "slug": "microsoft-clarity", "name": "Microsoft Clarity", "short": "Clarity", "group": "product",
        "logo": "clarity.svg", "meta": "backend/service/clarity/fetch.py", "label": "Microsoft Clarity",
        "card": "Rage clicks, dead clicks, quick-backs and script errors, per page.",
        "auth": "Export token", "pack": "backend/agents/knowledge/clarity.md",
        "api": "Clarity Data Export API ({api_version})",
        "page": {
            "title": "Microsoft Clarity AI analyst: after the click | Duct",
            "description": "Duct reads Clarity's rage clicks, dead clicks, quick-backs and script errors per page, beside GA4 and your ads, to find the page that wastes a paid click.",
            "og_description": "Your ads report the click. Clarity sees what came next. Duct reads both and names the page that wastes them.",
            "twitter_description": "Is it the ad or the page? Duct reads Clarity beside your campaigns.",
            "experiment": "Per-tool integration searches run 10 to 50 a month (OpenSEO, Sep 2026). Hypothesis: a paid marketer whose ads look fine and whose conversions don't converts on a page that puts the landing page's friction next to the campaign. Measured by download clicks per visit.",
            "h1": "Clarity, <em>what happened after the click.</em>",
            "sub": "Your ads report the click. Clarity sees what came next: rage clicks, dead clicks, people leaving in seconds, scripts failing. Duct reads it beside GA4 and your campaigns and names the page that is wasting them.",
            "shot": {"file": "session-clarity", "alt": "A Duct session: asked why a landing page loses paid visitors, Duct reads Clarity friction per page beside GA4 and finds a pricing toggle failing on Android Chrome", "caption": "Ask why a landing page loses paid visitors. Duct reads the last three days of Clarity, bots removed, beside GA4, and names the broken toggle."},
            "hero": {
                "joins": ["clarity", "ga4", "google_ads"],
                "answer": "The pricing toggle on /freelancers fails on Android Chrome. 71% of its visitors came from ads.",
            },
            "questions": [
                ("Which landing page is wasting paid clicks?", ["clarity", "ga4", "google_ads"]),
                ("Is the conversion drop the ads, or the page?", ["clarity", "google_ads"]),
                ("Did yesterday's release break something people use?", ["clarity"]),
                ("Where do people rage-click on the pricing page?", ["clarity"]),
            ],
            "knows": [
                ("Clarity keeps three days.",
                 "Its API returns only the last one to three days, so it is a health check, not history. Duct reads it for what is happening now, and daily when something needs watching."),
                ("Ten calls a day, hard.",
                 "Clarity allows ten API requests per project per day and a Duct read costs two, so Duct never polls. Hitting the limit means tomorrow, not a retry."),
                ("Bots are in the sessions.",
                 "Clarity counts bot sessions with the rest. Duct takes them out before it works out any rate."),
                ("Compare by share, not count.",
                 "A friction figure is the share of sessions that had at least one. Duct compares pages by that share, so a busy page doesn't look worse for being busy."),
            ],
            "pairs": [
                ("google_ads", "Is it the ad, or the page after it?"),
                ("ga4", "Which friction costs conversions?"),
                ("mixpanel", "Where in the funnel do people get stuck?"),
            ],
            "setup": [
                "In Clarity, open Settings, then Data Export, and generate an API token.",
                "Make it in the project Duct should read: the token is the project, with no ID beside it.",
                "In Duct, open Connections, choose Microsoft Clarity and paste the token.",
            ],
            "permissions": "Read-only: an export token can only read, and Duct has no Clarity change operation.",
            "faq": [
                ("Can Duct see session recordings?",
                 "No. It reads Clarity's exported numbers per page, not recordings or heatmaps."),
                ("Why only the last three days?",
                 "That is all Clarity's API returns. Duct treats it as a live health signal and, when a problem needs following, reads it daily."),
                ("Can Duct change anything in Clarity?",
                 "No. It has no Clarity change operation. It can tell you which page to fix."),
                ("Is it free?", "{free}"),
            ],
        },
    },
    {
        "id": "growthbook", "slug": "growthbook", "name": "GrowthBook", "group": "product",
        "logo": "growthbook.svg", "meta": "backend/service/growthbook/fetch.py", "label": "GrowthBook",
        "card": "Which tests are live, whether they still bucket, per-metric results.",
        "auth": "API key", "pack": "backend/agents/knowledge/growthbook.md",
        "api": "GrowthBook REST API ({api_version})",
        "page": {
            "title": "GrowthBook AI analyst: is the test still running? | Duct",
            "description": "Duct reads GrowthBook experiments and results, flags tests that stopped bucketing or never reached their sample, and checks the outcome in Stripe. Read-only.",
            "og_description": "A test can say running for weeks after it stopped bucketing anyone. Duct checks before you call it, and reads the outcome in Stripe.",
            "twitter_description": "94% chance to win, on 62 users. Duct checks before you call the test.",
            "experiment": "Per-tool integration searches run 10 to 50 a month (OpenSEO, Sep 2026). Hypothesis: a product team that has shipped a 'winner' that wasn't converts on a page that shows the stale-test check. Measured by download clicks per visit.",
            "h1": "GrowthBook, <em>before you call the test.</em>",
            "sub": "A test can say running for weeks after it stopped bucketing anyone. Duct reads your experiments and results, checks exposures are still arriving and the sample is big enough, and reads the outcome in Stripe.",
            "shot": {"file": "session-growthbook", "alt": "A Duct session: asked whether a pricing test is ready to call, Duct reads GrowthBook and Stripe and finds the test stopped bucketing with its control arm under the minimum sample", "caption": "Ask whether the test is ready to call. Duct finds it stopped bucketing on 1 Sep, under its minimum sample, and reads the real baseline in Stripe."},
            "hero": {
                "joins": ["growthbook", "stripe"],
                "answer": "It says running, 94% to win. It stopped bucketing on 1 Sep, with 62 users in control.",
            },
            "questions": [
                ("Is this experiment ready to call?", ["growthbook"]),
                ("Which running tests have stopped bucketing?", ["growthbook"]),
                ("Did the winning variant change revenue?", ["growthbook", "stripe"]),
                ("Does the test's metric match the event we track?", ["growthbook", "mixpanel"]),
            ],
            "knows": [
                ("Running is a setting, not a signal.",
                 "An experiment can show running while bucketing nobody. Duct flags a running test whose phase is over 45 days old and whose results stop short of the last week."),
                ("Under the minimum sample, it isn't a result.",
                 "A chance to win on an arm under the configured minimum is noise with a percentage sign. Duct says so instead of quoting it."),
                ("Both sides need the same identity.",
                 "If assignment hashes one ID and analysis joins on another, users are misattributed wherever the two differ. Duct asks which ID each side uses."),
                ("Duct doesn't touch your flags.",
                 "Flag flips and experiment stops are product decisions. Duct reads GrowthBook and never writes to it."),
            ],
            "pairs": [
                ("stripe", "Did the winner change revenue?"),
                ("mixpanel", "Is the metric the event you think it is?"),
                ("ga4", "Did the variant change what people do on the site?"),
            ],
            "setup": [
                "In GrowthBook, open Settings, then API Keys, and create a read-only key.",
                "Note the project ID if your organisation runs more than one product.",
                "In Duct, open Connections, choose GrowthBook and paste the key and the project ID.",
            ],
            "permissions": "Read-only: a read-only key is enough, Duct has no GrowthBook change operation, and it filters to your project so another product's experiments stay out.",
            "faq": [
                ("Will Duct stop or change an experiment?",
                 "No. Duct never writes to GrowthBook. It reads experiments and results and tells you what it found; stopping or restarting a test is yours."),
                ("How does Duct know a test stopped bucketing?",
                 "It flags a running experiment whose phase is older than 45 days and whose results don't reach the last week: the pattern of a test that looks alive and isn't."),
                ("Our GrowthBook organisation has several products. Will they mix?",
                 "Not if you give Duct the project ID. It filters experiments to that project."),
                ("Is it free?", "{free}"),
            ],
        },
    },
    # ── Revenue ────────────────────────────────────────────────────────────
    {
        "id": "stripe", "slug": "stripe", "name": "Stripe", "group": "revenue",
        "logo": "stripe.svg", "meta": "backend/service/stripe/fetch.py", "label": "Stripe",
        "card": "Settled revenue, subscriptions, refunds and payment outcomes.",
        "auth": "Restricted read key", "pack": "backend/agents/knowledge/stripe.md",
        "source": "backend/service/stripe/fetch.py", "checked": "2026-09-29",
        "api": "Stripe API {stripe_version}",
        "reads": [
            ("Subscriptions", ["status", "plan", "amount", "interval", "created", "canceled"]),
            ("Charges", ["status", "amount", "refunded amount", "failure code", "customer"]),
            ("Revenue summary", ["new paid subscriptions", "never-paid checkouts", "gross", "refunded", "net", "new MRR"]),
        ],
        "page": {
            "title": "Stripe AI analyst: revenue next to your ads | Duct",
            "description": "Duct reads Stripe with a restricted read key and checks every ad platform's conversions against the money that settled. It counts new customers, not renewals.",
            "og_description": "Ad platforms count their own conversions. Stripe counts money. Duct reads Stripe beside your ads and says which one is right.",
            "twitter_description": "Your ads claim the sale. Stripe knows if it paid. Duct reads both and tells you the difference.",
            "experiment": "'stripe ai' is 480 searches a month (KD 30, informational). Hypothesis: a founder or growth lead who already doubts their ad platforms' numbers converts on a page that shows the reconciliation, not on a feature list. Measured by download clicks per visit.",
            "h1": "Stripe, <em>the number your ads answer to.</em>",
            "sub": "Every ad platform reports conversions it credits to itself. Stripe reports money that settled. Duct reads both and tells you which campaigns brought customers who paid.",
            "shot": {"file": "session-stripe", "alt": "A Duct session: asked how many paying customers the ads brought, Duct reads Google Ads, Meta and Stripe and reconciles 64 claimed purchases against 23 first payments", "caption": "Ask how many customers the ads brought. The platforms claim 64; Stripe settled 23. Duct counts first payments, not upgrades or checkouts that never charged."},
            "hero": {
                "joins": ["stripe", "google_ads", "meta_ads"],
                "answer": "Your ads claimed 64 purchases in September. Stripe settled 23 new subscriptions.",
            },
            "questions": [
                ("How many paying customers did paid ads bring this month?", ["stripe", "google_ads", "meta_ads"]),
                ("What does a paying customer cost, by ad platform?", ["stripe", "google_ads", "meta_ads", "openai_ads"]),
                ("How many checkouts started and never charged?", ["stripe"]),
                ("Did the new pricing page move paid signups, or only trials?", ["stripe", "ga4"]),
            ],
            "knows": [
                ("Stripe is the money truth.",
                 "Ad platforms report conversions they attribute to themselves; Stripe reports money that settled. When they disagree, Duct sides with Stripe."),
                ("A checkout that never charged is not a sale.",
                 "Incomplete subscriptions are abandoned or failed checkouts. Counting them overstates acquisition two to three times, so Duct leaves them out."),
                ("Most charges are renewals.",
                 "Charge volume is mostly your existing customers paying again. Duct counts new paid subscriptions, not charges, when it measures acquisition."),
                ("Refunds come off, and no plan reads as zero.",
                 "Revenue is net of refunds, and prices come from subscription items, so a multi-item plan never shows as $0."),
            ],
            "pairs": [
                ("google_ads", "Which Google campaigns bring customers who pay?"),
                ("meta_ads", "Does Meta's purchase count survive Stripe?"),
                ("revenuecat", "Web and app revenue, read as one number."),
            ],
            "setup": [
                "In Stripe, open Developers, then API keys, and create a restricted key.",
                "Give it read access to Subscriptions, Charges, Invoices, Customers, Products and Prices. Nothing else.",
                "In Duct, open Connections, choose Stripe and paste the key. Duct checks each permission and names any that is missing.",
            ],
            "permissions": "Read-only by construction: a restricted key with read permissions cannot move money or edit a customer, and Duct has no Stripe change operation at all.",
            "faq": [
                ("Can Duct move money or edit customers in Stripe?",
                 "No. It connects with a restricted key that has read permissions only, and Duct has no Stripe change operation. It reads subscriptions and charges and reports on them."),
                ("Which Stripe permissions does Duct need?",
                 "Read access to Subscriptions, Charges, Invoices, Customers, Products and Prices. If one is missing, Duct names it when you connect instead of reporting a hole in the data as zero."),
                ("Why doesn't Stripe match what my ad platforms report?",
                 "Because each platform counts the purchases it credits to itself, with its own attribution window, and several of them claim the same sale. Expect the platforms' total to run 1.5 to 3 times what Stripe settled. Duct reconciles the platforms against Stripe, never the other way round."),
                ("Is it free?", "{free}"),
            ],
        },
    },
    {
        "id": "revenuecat", "slug": "revenuecat", "name": "RevenueCat", "group": "revenue",
        "logo": "revenuecat.svg", "meta": "backend/service/revenuecat/fetch.py", "label": "RevenueCat",
        "card": "Trials, renewals, refunds and MRR across the App Store and Play.",
        "auth": "Secret key (V2)", "pack": "backend/agents/knowledge/revenuecat.md",
        "source": "backend/service/revenuecat/fetch.py", "checked": "2026-09-29",
        "api": "RevenueCat API v2",
        "reads": [
            ("Overview metrics", ["active trials", "active subscriptions", "MRR", "revenue", "new customers", "active users"]),
            ("Apps, products, entitlements and offerings", ["name", "store", "identifier"]),
            ("Customers, a sample of 500", ["first seen", "last seen", "country", "platform", "active entitlements"]),
        ],
        "page": {
            "title": "RevenueCat AI analyst: app revenue beside the web | Duct",
            "description": "Duct reads RevenueCat's subscriptions, trials and MRR beside Stripe and your app ads, so web and app revenue read as one number. Read-only, customer IDs hashed.",
            "og_description": "Stripe sees the web. RevenueCat sees the App Store and Google Play. Duct reads both, so MRR is one number and app ads answer to it.",
            "twitter_description": "Web MRR plus app MRR, read as one number. Then the app ads, checked against it.",
            "experiment": "Per-tool integration searches run 10 to 50 a month (OpenSEO, Sep 2026). Hypothesis: a subscription app whose dashboards each show half the revenue converts on a page that adds the halves up. Measured by download clicks per visit.",
            "h1": "RevenueCat, <em>the app's half of the revenue.</em>",
            "sub": "Stripe sees the web. RevenueCat sees the App Store and Google Play. Duct reads both so MRR is one number, and checks app ad installs against the subscriptions they turned into.",
            "shot": {"file": "session-revenuecat", "alt": "A Duct session: asked what the app earns next to the web, Duct reads RevenueCat metrics and a hashed customer sample beside Stripe and adds app MRR to web MRR", "caption": "Ask what the app earns. Duct adds RevenueCat's app MRR to Stripe's web MRR and shows which platform pays."},
            "hero": {
                "joins": ["revenuecat", "stripe", "apple_ads"],
                "answer": "The app earns €6,900 MRR on top of Stripe's €18,400. Android pays at half the iOS rate.",
            },
            "questions": [
                ("What is our MRR across web and app together?", ["revenuecat", "stripe"]),
                ("Did the Apple Search Ads installs start trials?", ["revenuecat", "apple_ads"]),
                ("Do Android users pay like iOS users?", ["revenuecat"]),
                ("How many trials are active right now?", ["revenuecat"]),
            ],
            "knows": [
                ("RevenueCat is the app's money truth.",
                 "Installs and in-app events are signals. RevenueCat sees refunds, billing retries and cancellations, so Duct checks app ad conversions against it, never the reverse."),
                ("An SDK key can't read the API.",
                 "Keys starting appl_ or goog_ are for the app. Reading needs a secret V2 key, and Duct tells you if you pasted the wrong kind."),
                ("Customer IDs are hashed.",
                 "Duct keeps a SHA-256 of each app user ID: enough to join one pull to the next, useless for identifying a person."),
                ("Metrics are rate-limited hard.",
                 "RevenueCat's metrics API allows 25 requests a minute. Duct paces its reads rather than finding the limit by failing."),
            ],
            "pairs": [
                ("stripe", "Web and app revenue, read as one number."),
                ("apple_ads", "Installs in, subscribers out."),
                ("mixpanel", "Upgrades counted, upgrades paid."),
            ],
            "setup": [
                "In RevenueCat, open Project settings, then API keys, and create a secret API key (V2).",
                "Give it read access to project configuration, customer information and charts metrics.",
                "In Duct, open Connections, choose RevenueCat and paste the key.",
            ],
            "permissions": "Read-only: a key with read scopes cannot change a product or a subscription, and Duct has no RevenueCat change operation.",
            "faq": [
                ("Can Duct change products, offerings or subscriptions?",
                 "No. Duct has no RevenueCat change operation. It reads metrics, configuration and a customer sample."),
                ("Which customer data does Duct keep?",
                 "From a sample of 500 customers: when each was first and last seen, their country and platform, and their active entitlements, with the user ID hashed."),
                ("Why a secret key and not the one in my app?",
                 "The keys in your app are public SDK keys, and they cannot read RevenueCat's REST API. A secret V2 key with read scopes can."),
                ("Is it free?", "{free}"),
            ],
        },
    },
    {
        "id": "hubspot", "slug": "hubspot", "name": "HubSpot", "group": "revenue",
        "logo": "hubspot.svg", "soon": True,
        "card": "CRM lifecycle stages, pipeline and closed revenue.",
    },
]
