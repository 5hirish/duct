# Documentation index

Engineering and reference material for Duct. Folder indexes list only the
references; records are found by their dated filenames.

**Start with [`architecture.html`](architecture.html)**: the interactive map
of the monorepo, each app, and the internals a contributor meets first. Open
the file in a browser; it is self-contained.

| Folder | What is in it |
|--------|---------------|
| [`engineering/`](engineering/) | How we build: a short list of references, and dated records beside them |
| [`design/`](design/) | UX specs and design decisions |
| [`archive/2026-Q2/`](archive/2026-Q2/) | Records that would now mislead, each with a row saying why |
| [`guides/`](guides/) | Third-party model prompting references, each with its source and licence |

Product strategy, go-to-market and MVP scope are kept in a separate private
repository along with the deployment runbooks, so this index covers engineering
and reference material only.

## Naming

Two kinds of document, told apart by the filename:

- **Records** — `YYYY-MM-DD-<slug>.md|html`: a review, a plan, a research
  report, a decision. The date is the day it was written and the document is
  frozen from then on. Outcomes and corrections go in a dated addendum at the
  bottom, or in a new record, never by rewriting the argument, so a reader
  always knows how old the reasoning is.
- **References** — `<slug>.md`: a runbook, a contract, an inventory, a
  watch-list. Anything that has to be true *now*. Rewritten in place, and it
  says when it was last brought up to date.

Every document carries one line under its title naming the author (the git
user who wrote it) and its date: `**Author:** … · **Date:** …` on a record,
`**Author:** … · **Updated:** …` on a reference (an HTML page uses
`<b>Author</b>` / `<b>Date</b>` in its masthead). `scripts/check_docs.py`
(`make check-docs`, `docs.yml` on pull requests) fails a file that has
neither line, a record whose date disagrees with its filename, a reference
that was edited without its `Updated:` line moving, an HTML file with no
figure in it, or a document whose `files: [...]` lists name a path that no
longer exists (the architecture page lists one per box). `guides/` is exempt as third-party material with its own
provenance headers; folder `README.md` indexes and the generated
`engineering/agent-prompts.md` are exempt too.

## Writing

- **Markdown, unless the doc needs a figure.** HTML is for a diagram, a
  chart, a rendered demonstration — something markdown cannot show. A page
  of prose and tables in HTML costs styling to write and tokens to read and
  gives nothing back; six of the seven HTML reports here were converted to
  markdown on 2026-09-14 for exactly that reason, and the check above keeps
  the rule.
- **Structured.** Lead with the answer. Short sections under headings, a
  table for anything compared, a list for anything parallel. A reader should
  be able to find the one fact they came for without reading the rest.
- **Brief.** Say it once, in plain words, and stop. A record that takes more
  than a few minutes to read is hiding its point; the 25 to 100 KB reports
  that used to live here are the length to avoid, not the model.
- **Human-readable.** Written for the next person on the team, not for the
  agent that wrote it. Expand an acronym the first time; name a file only
  when the reader has to open it.

- **`engineering/`** — *how we build*. Records and references side by side;
  the folder index says which each one is.
- **`design/`** — UX specs and design decisions.
- **`archive/<quarter>/`** — records only. A doc moves here when following it
  would produce the wrong thing, not merely when the work ships. Every archived
  file carries a banner saying what replaced it, and a row in that folder's
  `README.md` saying why.

Agent conventions are in [`../backend/AGENTS.md`](../backend/AGENTS.md); cross-agent
design and per-agent plans go in `engineering/`. There is no separate `agents/` folder —
one existed for a single unbuilt plan, which is now archived.

Add a short `README.md` in a folder when its purpose is non-obvious or status (draft vs active) matters.
