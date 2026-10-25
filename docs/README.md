# Duct docs

**Author:** Shirish Kadam · **Updated:** 2026-10-25

How Duct is built, what was decided and why, written for the next person on
the team. Product strategy, go-to-market and the deployment runbooks live in a
separate private repository; this folder holds engineering and reference
material only.

## Start here

| I want to… | Read |
|---|---|
| See how the monorepo, the apps and the agents fit together | [architecture.html](architecture.html), an interactive map. Open the file in a browser; it is self-contained |
| Decide where something is recorded before adding a table, event or log | [Data model](engineering/data-model.md) |
| Add or change an agent | [Building and changing agents](engineering/agent-engineering.md) |
| Know where every secret lives and what protects it | [Credential storage](engineering/credential-storage.md) |
| Find every other reference, by task | [Engineering](engineering/README.md) |
| Read the plan, review or research behind a decision | `engineering/`, by date. `ls` sorts the records into a timeline |

## Folders

| Folder | Holds |
|---|---|
| `engineering/` | How we build: a short list of references kept current, and dated records beside them |
| `design/` | UX specs and design decisions |
| `archive/<quarter>/` | Records a reader should no longer follow. Each carries a banner naming what replaced it, and a row in the folder's README saying why |
| `guides/` | Third-party model prompting references, each with its source and licence |
| `assets/` | Images the READMEs embed |
| `figures/` | Standalone SVG figures that Markdown docs embed (create when first needed) |

Agent conventions are rules, not docs: they live in each area's `AGENTS.md`
(backend agents in [`backend/AGENTS.md`](../backend/AGENTS.md)). Cross-agent
design and per-agent plans are records in `engineering/`. Add a `README.md` to
a folder only when its purpose is not obvious from its name.

## Naming

The filename says whether a document may change.

| | References (`<slug>.md`) | Records (`YYYY-MM-DD-<slug>.md`) |
|---|---|---|
| Describe | How things are now: a runbook, a contract, an inventory | A review, plan, research report or decision, on the day it was written |
| Header line | `**Author:** … · **Updated:** YYYY-MM-DD` | `**Author:** … · **Date:** YYYY-MM-DD` |
| When things change | Rewritten in place, in the same change as the code, and the date moves | Frozen. Outcomes and corrections go in a dated addendum at the bottom, or a new record, so a reader always knows how old the reasoning is |

The author is the git user who wrote it; an HTML page carries the same two
lines in its masthead. `make check-docs` (`docs.yml` on pull requests)
enforces the rule. The script, `scripts/check_docs.py`, lists exactly what
fails and what is exempt: the third-party guides, folder indexes and the
generated agent prompts page.

## Writing docs

Docs are for people. The code, the schemas and the `AGENTS.md` files are for
agents. A reader gets the point in 5 seconds and the picture in 30, without
reading a paragraph.

1. **Four layers.** The title and one line on why it matters. A figure or a
   table, then **At a glance** in 3–5 bullets. Sections whose headings state
   their point: "Only approved actions write", never "Overview". Detail last,
   as links.
2. **Not too technical.** What it does and why, before how. Paths, config
   keys, field lists and function names live in the code or the area's
   `AGENTS.md`; link to them. Explain each term once, in plain words.
3. **Show, don't tell.** A figure for a flow, a table for a comparison,
   numbered steps for a procedure, short prose for the why. At most one
   callout per screen, labelled Rule, Why or Gotcha.
4. **Short.** One idea per paragraph, three lines at most. An explainer stays
   under about 1,000 words (5 minutes), a how-to under 600. Longer than that,
   split it by what each reader needs to do.
5. **Figures** are standalone SVGs in `figures/<doc>-<name>.svg`, with light
   and dark palettes, at most eight boxes, arrows labelled with verbs. The
   caption states the takeaway, not the topic.
6. **Markdown, unless the doc is interactive.** HTML is for a page the reader
   drives, like the architecture map, and it must carry a figure. An HTML page
   of prose fails the check: six sat unread until 2026-09-14.
7. **Rewriting loses nothing.** List every fact the old doc holds, give each
   a home (the new doc, the code, another doc, an `AGENTS.md`), and fix
   inbound links by meaning.
8. **No customer data.** The repository is public: invented names and
   synthetic accounts only.
9. **Before you hand it over.** Does the first line say what this is and why
   it matters? Do the headings and bold text alone tell the story? Would a
   newcomer know every term? What could be cut without loss?

Files written for agents and engineers keep their density: `AGENTS.md`,
`STYLE.md`, `DESIGN.md` and generated references are detail by design.
