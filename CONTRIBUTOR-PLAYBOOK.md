# Contributing without writing app code

You can fix a headline on getduct.ai, flag a contrast problem or draft a blog
post without a database, FastAPI or a membership check. This page is for a
designer, PM or marketer with an opinion worth landing; engineers start at
[CONTRIBUTING.md](CONTRIBUTING.md).

## At a glance

| I want to… | Do this |
|---|---|
| Fix or flag something on the website | Serve `site/` locally, then open a [design feedback issue](../../issues/new?template=design_feedback.yml) or fix the page |
| Check an app screen or component | Open `/preview`: one component, every state, no sign-in |
| Propose a feature | An idea goes in [Discussions](../../discussions); a scoped change in a [feature request](../../issues/new?template=feature_request.yml) |
| Test a new audience or angle | A landing page, built by the `new-page` skill |
| Publish a post or a release note | The `add-blog-post` and `add-changelog-entry` skills |
| Stop repeating yourself | Write the instruction down once, as a skill |

> **Why this works:** you can look at the real thing without running the
> stack, and an AI coding assistant (Claude Code, Cursor, Codex, Copilot) does
> the mechanical part: finding the file, matching the HTML/CSS pattern,
> updating the sitemap. You supply the part that needs judgment: *what* should
> change and *why*.

## You're a designer

**Look at the real page or component first, then say what's wrong.**

The website (`site/`: the landing pages, the blog, the changelog) is plain
HTML and CSS with no build step:

1. **Serve it.** `python3 -m http.server 8090 --directory site`
2. **Open** <http://localhost:8090>.
3. **Read [`site/DESIGN.md`](site/DESIGN.md)** before changing anything: the
   visual system as built, the accent-variant rule, the contrast rules for the
   brand orange.

An app component renders alone at `/preview`, in every state, with no sign-in
and no real screen to reproduce:

1. **Start the app.** `cd app && npm install && npm run dev`
2. **Open** <http://localhost:3003/preview>.
3. **Or ask an agent.** The `component-preview` skill takes a component name
   and the state you need: empty, loading, failed, long name, disabled.

**Report it** with a [design feedback issue](../../issues/new?template=design_feedback.yml):
a screenshot, the page or component, what's wrong. To hand it straight to an
agent, describe the fix in the issue and tick "I'd like to try fixing this
myself".

## You're a PM

**Describe the problem, not the fix.** The feature request form asks for the
situation on purpose: the fix is often not the one first imagined. Open-ended
ideas go in [Discussions](../../discussions).

**A new audience or campaign angle is a landing page, not a spec.** Each
`site/for-*.html` page tests one hypothesis for one audience, A/B'd by URL.
Give the `new-page` skill an audience slug, a headline and a subtext and it
builds the page on the same design system. If you can write the three
sentences, an agent can build the page.

## You're doing marketing or content

**Content is a skill, not hand-written HTML.**

| You want | Skill | It does |
|---|---|---|
| A blog post | `add-blog-post` | Plans, writes and files an Insights post; updates the index and the sitemap |
| A landing page | `new-page` | One audience-specific page on the shared design system |
| A release note | `add-changelog-entry` | Turns what shipped into a readable entry, an RSS item and a sitemap update |

[`site/AGENTS.md`](site/AGENTS.md) says what each content type is for:
landing pages validate a channel, the blog compounds organic search, the
changelog shows motion to someone deciding whether to install.
[`site/DESIGN.md`](site/DESIGN.md) holds the copy voice, codified from the
site's best lines rather than a generic style guide.

Have a draft, an outline or a keyword cluster we're missing? Open a
[content idea issue](../../issues/new?template=content_idea.yml). A rough
draft is more useful to an agent than a one-line ask.

## Turn what you know into a skill

Everything above runs through `.agents/skills/<name>/SKILL.md`: a short recipe
that any agent reading this repo follows the same way. If you find yourself
giving the same instruction twice ("here's how landing-page copy should
sound", "here's the checklist before an illustration ships"), write it as a
skill. It pays out every time someone uses it after you.

Copy the shape of [`add-blog-post`](.agents/skills/add-blog-post/SKILL.md) or
[`mosaic-panel`](.agents/skills/mosaic-panel/SKILL.md): a short description, an
argument hint, and steps written for a smart person who has never seen this
project. The wiring (a directory, a `SKILL.md`, a symlink from each tool's own
skills folder) is in [`AGENTS.md`](AGENTS.md); ask an agent to do it.

## Get credited

Add yourself to [`CONTRIBUTORS.md`](CONTRIBUTORS.md) in the same PR, for
design, content, code or anything else. No contribution is too small.
