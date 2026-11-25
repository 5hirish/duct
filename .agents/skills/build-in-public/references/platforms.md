# What X and LinkedIn reward, as of 23 November 2026

**Both networks now rank with large models that predict what one reader will
do, so the only durable tactic is a post that reader would actually read to
the end, reply to and save.** Tricks aimed at the old counters (pods, bait,
link-in-comment) are what both networks say they are removing.

Every claim is marked **primary** (the network's own words or code) or
**secondhand** (a third party's study or a creator's report). Secondhand
numbers guide a test; they are never quoted in a post. Re-check this page
every 90 days, and date any change.

## X: a model predicts each reader's next action

| Claim | Source | Confidence |
|---|---|---|
| The For You feed is ranked by a Grok-based transformer ("Phoenix") that predicts, for each viewer, the probability of each action, then sums them with weights | [xai-org/x-algorithm](https://github.com/xai-org/x-algorithm) README | primary |
| Predicted actions: favourite, reply, repost, quote, share, share by DM, copy link; clicks on the post, profile, link, photo, video and quoted post; dwell and dwell time; video watch; follow the author. Negative: not interested, mute, block, report, scrolled past | same, as summarised from the README | primary, check the repo before quoting exact names |
| Weights scale predicted probabilities, not raw counts | same, 14 Aug 2026 note | primary |
| A second post from the same author in one feed is discounted, and out-of-network posts are discounted; small accounts get a boost below an impressions threshold | same, summarised | primary, summarised |
| Retrieval is trained toward posts "people read all the way through"; ranking now estimates time spent on each post | same, 13 Oct and 8 Oct 2026 notes | primary |
| Links are not held back: X's head of product said in July 2026 that links no longer need to go in replies, and the published code has no hard-coded link penalty | [Postory, reading the 2026 code](https://postory.io/blog/x-algorithm-2026), [OpenTweet on the GitHub release](https://opentweet.io/blog/x-algorithm-open-source-github-2026) | secondhand report of a primary statement |
| "Links lose 30 to 94% of reach" | several creator blogs, e.g. [SocialPilot](https://www.socialpilot.co/blog/twitter-algorithm) | secondhand, unverified, and the sellers of the workaround |
| Premium is not mentioned in the published ranking code | xai-org/x-algorithm | primary (absence) |
| Single images: 16:9 at 1600×900 or 1200×675; vertical 4:5 at 1080×1350 takes more of a phone feed. X publishes ratios, not a pixel spec | [Sked Social](https://skedsocial.com/blog/twitter-post-size-guide), [HeyOrca](https://www.heyorca.com/blog/x-twitter-media-specs-best-practices-2026) | secondhand |

**What it means for a post:** read time and replies are what the model learns
from, so a first line that earns the second, a visual that holds the eye, and
a question worth answering. Mutes and "not interested" cost more than a quiet
post, so bait loses. One original post a day; spend the rest on replies in
the rooms where marketers already talk.

## LinkedIn: interests, not popularity

| Claim | Source | Confidence |
|---|---|---|
| New models "better understand what posts are about and how members' interests change over time"; the goal is a feed "relevant to your interests, not a popularity contest" | [LinkedIn, Improving the Feed, 12 Mar 2026](https://news.linkedin.com/2026/ImprovingTheFeed) | primary |
| LinkedIn is "reducing recycled and click-driven posts", "comment to agree" prompts and videos that do not match their text, and working to make engagement pods ineffective and curb comment automation | same | primary |
| Rewarded: "posts that offer genuine insight, actionable ideas, and thoughtful perspectives" | same | primary |
| Ranking treats a member's interaction history as a sequence (Generative Recommender, LLM-augmented); retrieval uses one LLM embedding model for members and posts | same; [Feed-SR paper](https://arxiv.org/abs/2602.12354); [LLM retrieval paper](https://arxiv.org/html/2510.14223v1) | primary |
| Document (PDF carousel) posts get the most engagement and dwell, around 6.6% engagement, two to three times the dwell of text or image posts | [Dataslayer](https://www.dataslayer.ai/blog/linkedin-algorithm-february-2026-whats-working-now), [LinkBoost](https://www.linkboost.co/blog/linkedin-carousel-posts-guide-2026/) | secondhand |
| One external link in the body cut median reach by 18.8% (Richard van der Blom's 2026 report); other blogs say 25 to 70%; one says the first-comment workaround is "largely patched", another that LinkedIn does not penalise links when the post stands alone | [SocialPilot](https://www.socialpilot.co/blog/linkedin-algorithm), [Vulse](https://vulse.co/blog/how-linkedin-2026-algorithm-works-and-what-it-means-for-your-content-strategy), [van der Blom on Creator Science](https://podcast.creatorscience.com/richard-van-der-blom-2/) | secondhand, conflicting |
| Early engagement ("the golden hour") still seeds the wider test audience | several blogs, none with a method | secondhand, unverified |
| Personal profiles reach several times what a company page does | the private GTM strategy's own research | secondhand |

**What it means for a post:** pick three topics and stay on them, so the
interest model learns who to show him to. Write the insight in the post, not
behind the link. Explainers go out as documents. Reply to every comment
because a real conversation is the signal, not because of a magic hour, and
never use a pod, an auto-commenter or a "comment X" prompt.

## Build in public: what the record says

- **Tailor each network.** Identical text everywhere is the most-cited
  mistake: X rewards a punchy first line, LinkedIn a reflective, lesson-led
  post. ([Postory build-in-public playbook](https://postory.io/blog/build-in-public-x-playbook))
- **Strangers carry it, with one sentence.** Openfilm's founder post drew 755
  views; listicles and creators repeating its one-line description drew
  23,000 and 17,000. Give every post a line worth pasting and a picture worth
  reposting. (Private GTM teardown, 10 Nov 2026; growth-playbook lessons.)
- **The room where the problem lives, not where the tool was built.** A post
  to a coding-tool forum drew 2,500 views and no votes. (growth-playbook
  lessons, 10 Nov 2026.)
- **Vanity metrics are the weak version.** Sharing star counts and MRR is what
  critics call building in public badly; sharing the decision and the lesson
  is the version that compounds. ([DEV, "what building in public means in
  2026"](https://dev.to/udit_kapoor/what-does-building-in-public-actually-mean-in-2026-31oe))
- **No study ties X or LinkedIn posts to GitHub stars or contributors.** The
  only rigorous launch study covers Hacker News
  ([arXiv 2511.04453](https://arxiv.org/html/2511.04453v1)). Measure our own:
  stars, downloads and CLI runs on the day of each post.
