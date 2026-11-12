# Duct launch check

Find out before you launch why Google won't index a page, why a shared link
previews blank, why ChatGPT can't read the site and whether your signups are
tracked. Ask your coding agent "is my site ready to launch?" and you get a
score out of 100, three fixes ranked by impact and effort, and a card to post.

## Install

| Agent | Command |
|---|---|
| Claude Code | `/plugin marketplace add 5hirish/duct`, then `/plugin install duct@duct` |
| Codex | `codex plugin marketplace add 5hirish/duct`, then install Duct from `/plugins` |
| Any agent (Cursor, Copilot, OpenCode and more) | `npx skills add 5hirish/duct` |

No Duct account and no key.

## What it runs, fetches and sends

Disclosed in full, because the agent runs these on your machine:

- **Runs** `npx -y getduct@0.1.1`, the open-source CLI in this repository's
  [`cli/`](https://github.com/5hirish/duct/tree/main/cli), pinned to that exact
  version and downloaded from npm. It has no dependencies.
- **Fetches** the site you name: about 10 pages plus `robots.txt`, the sitemap
  and `llms.txt`, roughly 80 requests, two at a time, with the User-Agent
  `getduct/<version>`.
- **Reads** the repository you have open, locally, to check what the page
  promises against what the code does. Nothing from it leaves your machine.
- **Writes** three new files at the repository root: the report
  `duct-launch-check.md`, the result `duct-launch-check.json` and the
  1200x630 card `duct-launch-check.png`. It changes your code only one fix at
  a time, after showing the diff and getting your yes, and never commits,
  pushes or deploys.
- **Sends** nothing to Duct or anyone else. The only network traffic is to npm
  (the download) and to the site being checked.

## What's inside

[`launch-check/`](launch-check/) is the skill: the instructions your agent
follows, and the checklist it scores against. Source, issues and the MIT
licence: [github.com/5hirish/duct](https://github.com/5hirish/duct).
