# What the three personas say on Reddit

**Author:** Shirish Kadam · **Date:** 2026-11-24

**The threads confirmed most of the personas and moved three things: solo owners struggle to
decide when to stop a channel, small businesses often do not own their own ad accounts, and
marketers want to know what size of gap between platforms is normal.** This record is the
evidence behind the persona pages as of this date.

| | |
|---|---|
| **Method** | 25 Reddit searches about the problems themselves, never about Duct; comments read on the three threads with the most useful replies |
| **Window** | Posts from the last 12 months (Nov 2025 to Nov 2026) |
| **Rooms** | r/smallbusiness, r/SaaS, r/Entrepreneur, r/startups, r/ycombinator, r/PPC, r/googleads, r/GoogleAnalytics, r/analytics, r/SEO, r/DigitalMarketing, r/marketing, r/AskMarketing, r/agency, r/Solopreneur, r/freelance |
| **Tool** | SociaVault, through the `social-research` skill; about 30 credits, until the balance ran out |
| **Not done** | LinkedIn, X and YouTube (the free balance hit zero first), and comments on eight more threads (Google Ads "impossible", the one-person marketing team, AI executing ad changes, auto-apply losses, fractional client tracking). Rerun those when credits are topped up |

## What moved in the personas

| Persona | Before | After |
|---|---|---|
| `solo` | "Cannot tell which channel works" | **Cannot decide when a channel has failed.** Most of the marketing simply does not get done; what pays this week does |
| `solo` | Tool fatigue was a guess | Confirmed and strong: owners are tired of every problem being "solved" by another subscription |
| `team` | Agency value was a survey number | Confirmed, plus a new pain: **the agency holds the accounts**, and the owner feels held hostage |
| `marketer` | "Why don't the numbers match?" | Marketers know why. They ask **what gap is normal and what gap means it broke** |
| `marketer` | Traffic-drop questions were a guess | Confirmed, with a 2026 cause: AI Overviews answering the query while rankings hold |

## Patterns, by persona

A pattern is a pain seen in three or more threads across at least two rooms.

**Solo founders and owners**
- Ads feel opaque and risky: "Google Ads is impossible" (r/smallbusiness, Nov, 117 comments); is Google Ads a waste of money for a small SaaS (r/SaaS, 67); an owner who let Google set up the account and burned about $3k (r/PPC, 48).
- Deciding when a channel has failed, and money vs traffic (r/Entrepreneur, Nov, 67; r/Entrepreneur, Mar, 49; r/EntrepreneurRideAlong, Nov, 33).
- Marketing as the job that loses: the top reply in a 129-comment r/smallbusiness thread says most of it just doesn't get done. Builders "terrified of marketing" once the product is done (r/ycombinator, 166).
- Subscription fatigue (r/smallbusiness, 70; r/Entrepreneur, 53).
- GA4 avoided or endured (r/GoogleAnalytics, 42; r/analytics, 27).

**Small teams and businesses**
- Agencies that do not deliver, or that the owner cannot judge: a third agency in two years (r/Entrepreneurs, 43); two freelancers paid, zero new accounts (r/smallbusinessowner, Nov, 41); sick of the agency at $10k a month in ads (r/smallbusiness, 61).
- Account ownership: an agency that will not give a dentist admin access to their own Google Ads (r/DigitalMarketing, 179); every top reply on the r/smallbusiness thread says the business must own the accounts.
- Platforms that disagree with the till: Meta and Shopify never match (r/ecommerce, 26); a fifth of store orders missing from GA4 while executives want one funnel (r/analytics, 23).

**Marketers**
- Reporting got worse with better tools (r/PPC, 32); how long client reports take (r/DigitalMarketing, 29 and 48). Replies: reporting is a trust proxy; clients want the next step, not "CPA went down a little"; most weeks nothing material changed.
- Explaining platform gaps to clients (r/PPC, 53 and 42; r/GoogleAnalytics, 32 and 21).
- Traffic drops from AI Overviews, and rankings up while traffic falls (r/SEO, Oct, 77; r/DigitalMarketing, 21).
- Too many clients, and tracking what was promised to each (r/Solopreneur, Nov, 67; r/marketingagency, 69; r/freelance, 71).
- Platforms changing accounts unasked: auto-apply re-broadened campaigns and burned $600 in six days (r/PPC, 37); recommendations "quietly rewriting campaigns" (r/PPC, 16).
- In-house team of one: 151 comments on how hard it is, with "can AI do all of it?" in the question (r/marketing, Sep).

**AI, across all three**
- Scepticism about AI running ad accounts: "is LinkedIn just full of it?" (r/googleads, 51); Google's AI wrote an ad that Google then disapproved (r/PPC, 60).
- Demand for tools that are "not just hype" (r/DigitalMarketing, 62 and 125).

## Product questions this raises

These go through `prioritize`, not straight into code.

1. **Connecting without owning:** what does Duct say when a business cannot connect because an agency owns the account? (`team`)
2. **A channel verdict:** can the first answer be "keep, fix or stop this channel", with its money? (`solo`)
3. **The normal gap:** can Duct learn each project's usual gap between platforms and flag a change? (`marketer`)
4. **The quiet week:** can a brief say "nothing material changed" in three lines? (`marketer`)

## Rules this research kept

Threads were paraphrased, no usernames were kept, and raw responses stayed out of the
repository. Comment counts are as fetched on 2026-11-24.
