# Contributing without writing app code

[CONTRIBUTING.md](CONTRIBUTING.md) is written for someone about to run
`poetry install` or `npm install`. This one is for a designer, PM, or marketer
who has an opinion worth landing but no interest in the four-stack table at the
top of that file. You don't need to set up a database, understand FastAPI, or
know what a membership check is to fix a landing page headline, flag a
contrast problem, or draft a blog post.

Two things make this realistic in a way it wasn't a couple of years ago:

- **You can look at the thing without running the whole stack.** The static
  site needs one command and no build step. The app has an isolated preview
  route that skips auth and the real screen entirely.
- **An AI coding assistant (Claude Code, Cursor, or similar) can do the
  mechanical part** — finding the file, matching the existing HTML/CSS
  pattern, updating the sitemap — if you can describe *what* should change and
  *why*. That's the part that actually needs your judgment, and it's the part
  these paths are built around.

## You're a designer

**Look before you touch anything.**
- Site pages (`site/`, `for-*.html`, the blog, the changelog): pure HTML/CSS,
  no build step.
  ```bash
  python3 -m http.server 8090 --directory site
  ```
  Open <http://localhost:8090>. Read [`site/DESIGN.md`](site/DESIGN.md) first —
  it's the visual system as built: tokens, the accent-variant rule, contrast
  rules for the brand orange, section rhythm.
- App components (`app/`): the `/preview` route renders one component in
  isolation — every state, no sign-in, no need to reproduce the real screen.
  ```bash
  cd app && npm install && npm run dev
  ```
  Open <http://localhost:3003/preview>. If you have an agent that reads this
  repo's skills, `component-preview` drives this for you: point it at a
  component name and the state you need to see (empty, loading, failed, long
  name, disabled).

**Report or fix it.** Open a [Design / UX feedback issue](../../issues/new?template=design_feedback.yml)
— screenshot, page or component, what's wrong. If you'd rather hand it
straight to an agent, describe the fix in the issue and check "I'd like to try
this myself" — the issue is already scoped for that.

## You're a PM

**Propose, don't prescribe.** Open-ended ideas belong in
[Discussions](../../discussions); a specific, scoped change belongs in a
[Feature request](../../issues/new?template=feature_request.yml) issue. The
"the problem" field asks for the situation, not the fix — that's deliberate,
the fix is often not the one first imagined.

**A new audience or campaign angle is a landing page, not a spec doc.**
`site/` landing pages (`for-*.html`) exist to test a hypothesis fast, one per
audience or angle, A/B'd by URL. The `new-page` skill builds one from an
audience slug, a headline, and subtext — same design system, only the copy and
audience framing change. If you can write the three sentences, an agent can
build the page.

**If you find yourself repeating a process**, that's worth turning into a
skill rather than an issue every time — see below.

## You're doing marketing or content

**Blog posts, landing-page copy, and changelog entries are all skills**, not
hand-authored HTML:
- `add-blog-post` — plans, writes, and files a new Insights post, updates the
  index and sitemap.
- `new-page` — a new audience-specific landing page.
- `add-changelog-entry` — turns what shipped since the last entry into a
  human-readable release note, RSS item, and sitemap update.

Read [`site/AGENTS.md`](site/AGENTS.md) for what each content type is *for*
(landing pages validate a channel, the blog compounds organic search, the
changelog is proof-of-motion for someone deciding whether to install) and
[`site/DESIGN.md`](site/DESIGN.md) for the copy voice — it's been codified
from the site's best lines, not written from a generic style guide.

**Have a draft, an outline, or just a keyword cluster you think we're missing?**
Open a [Content idea issue](../../issues/new?template=content_idea.yml). Paste
what you have — a rough draft is more useful to an agent than a one-line ask.

## Turn what you know into a skill

Everything above routes through `.agents/skills/<name>/SKILL.md` — a short
recipe that any agent reading this repo (Claude Code, Cursor, Codex, Copilot)
can follow the same way. If you find yourself giving the same instructions
twice — "here's how I want landing-page copy to sound," "here's the checklist
before an illustration ships" — write it down as a skill instead. That's a
contribution that pays out every time someone uses it after you, not just once.

Look at [`add-blog-post`](.agents/skills/add-blog-post/SKILL.md) or
[`mosaic-panel`](.agents/skills/mosaic-panel/SKILL.md) for the shape: a short
description, an argument hint, and the steps written the way you'd explain it
to a smart person who's never seen this project. The root
[`AGENTS.md`](AGENTS.md) has the mechanics (the directory needs a `SKILL.md`
plus a symlink from each tool's own skills folder — ask an agent to wire that
part up, it's mechanical).

## Get credited

Add yourself to [`CONTRIBUTORS.md`](CONTRIBUTORS.md) in the same PR — design,
content, code, or anything else. No contribution is too small to be listed
for.
