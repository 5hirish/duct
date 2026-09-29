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
  from the catalogue and `{stripe_version}` from service/stripe/client.py, so
  a version bump reaches the page without anyone editing it.
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
    },
    {
        "id": "apple_ads", "slug": "apple-search-ads", "name": "Apple Search Ads", "group": "ads",
        "logo": "apple-search-ads.svg", "meta": "backend/service/apple/ads/fetch.py", "label": "Apple Search Ads",
        "card": "Spend, taps and installs, by campaign and search term.",
        "auth": "API key pair", "pack": "backend/agents/knowledge/apple_ads.md",
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
    },
    {
        "id": "gtm", "slug": "google-tag-manager", "name": "Google Tag Manager", "short": "Tag Manager", "group": "analytics",
        "logo": "google-tag-manager.svg", "meta": "backend/service/google/gtm.py", "label": "Google Tag Manager",
        "card": "Tags, variables and container versions, staged, with rollback.",
        "auth": "Sign in with Google", "pack": "backend/agents/knowledge/gtm.md",
    },
    # ── Product and experiments ────────────────────────────────────────────
    {
        "id": "mixpanel", "slug": "mixpanel", "name": "Mixpanel", "group": "product",
        "logo": "mixpanel.svg", "meta": "backend/service/mixpanel/fetch.py", "label": "Mixpanel",
        "card": "Signups, logins and upgrades, one name across web and app.",
        "auth": "Service account", "pack": "backend/agents/knowledge/mixpanel.md",
    },
    {
        "id": "clarity", "slug": "microsoft-clarity", "name": "Microsoft Clarity", "short": "Clarity", "group": "product",
        "logo": "clarity.svg", "meta": "backend/service/clarity/fetch.py", "label": "Microsoft Clarity",
        "card": "Rage clicks, dead clicks, quick-backs and script errors, per page.",
        "auth": "Export token", "pack": "backend/agents/knowledge/clarity.md",
    },
    {
        "id": "growthbook", "slug": "growthbook", "name": "GrowthBook", "group": "product",
        "logo": "growthbook.svg", "meta": "backend/service/growthbook/fetch.py", "label": "GrowthBook",
        "card": "Which tests are live, whether they still bucket, per-metric results.",
        "auth": "API key", "pack": "backend/agents/knowledge/growthbook.md",
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
    },
    {
        "id": "hubspot", "slug": "hubspot", "name": "HubSpot", "group": "revenue",
        "logo": "hubspot.svg", "soon": True,
        "card": "CRM lifecycle stages, pipeline and closed revenue.",
    },
]
