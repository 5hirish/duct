# Artifact store — design notes & roadmap

How the industry builds AI artifacts (Claude artifacts, Claude Code artifacts,
ChatGPT Canvas, Gemini Canvas, Copilot Workspace, Notion AI), and what Duct's
artifact store (`backend/models/artifact.py`, added 2026-08) adopts from it.
Researched 2026-08-26; sources at the bottom.

## What Duct already matches (validated by the research)

- **kind + MIME split** — `kind` carries product semantics, `content_type`
  picks the renderer. Same shape as Claude's type taxonomy. Extend with vendor
  types (`application/vnd.duct.*`), don't replace.
- **Full-version snapshots** — every version is an immutable full row under a
  stable `group_id`. This is what everyone converged on: patches (Claude's
  `old_str/new_str`, Canvas's regex updates) are a *transport/token
  optimization*; storage is always full snapshots. OpenAI shipped regex
  patching and then instructed the model to full-rewrite almost always — the
  cautionary tale against clever patching.
- **Many artifacts per conversation**, linked by `conversation_id` — the norm.
- **Source-in, render-per-type** — store authorable source (structured JSON,
  HTML, markdown); the client owns rendering. Never store compiled output as
  the source of truth. Duct's structured-JSON reports are the strongest form
  of this (the "Notion-native-object" path): schema-validated, semantically
  diffable, re-renderable when templates improve.
- **Split-workspace layout** (chat left, artifact right) — the industry-
  standard shell; ChatGPT retired Canvas in favor of typed blocks in the
  stream, i.e. the Claude-style model won.

## Implemented 2026-08-26

Items 1–4, 6 (partially), and 7 below shipped in the artifact-sprint commit:
slugs (`artifacts.slug`, migration c8f3a1d92b4e, `ensure_unique_slug` /
`resolve_reference` — slug, group id, version id, or pasted URL), the three
write verbs as audit MCP tools (`CreateArtifact` / `UpdateArtifact`
exact-string patches with unique-match validation and rewrite-fallback errors /
`RewriteArtifact`; reports excluded — they keep their validated flow), vendor
MIME types (`application/vnd.duct.{report,table,chart,diff}+json`,
`text/vnd.mermaid`) with per-type renderers (`ArtifactRenderer.jsx`), restore-
as-new-version, show-changes unified diff + semantic report summary, optimistic
concurrency (`expected_version` → conflict), per-version labels, in-chat
artifact cards (`ARTIFACT_UPDATED` SSE), and derived exports (PDF/CSV/MD,
cached per version). Deferred: sharing/publish (private-only for now), React
component artifacts, viewer-side AI capabilities.

## Adopt next (roughly ordered)

1. **Model-chosen semantic slugs.** Let the agent coin a kebab-case
   `identifier` at creation (`acme-seo-audit-2026-08`), stored on the group and
   resolved slug→group_id in the tool layer. Models reuse a slug they coined
   far more reliably than a UUID. (Claude `identifier`, Canvas `name`.)
2. **Three edit verbs as agent tools** — `create_artifact`,
   `update_artifact(edits: [{old_str, new_str}])` (exact-string, unique-match,
   fall back to rewrite on any ambiguity), `rewrite_artifact`. Every edit
   materializes a new version. For JSON reports prefer section-scoped
   replacement over string patching.
3. **New content types**: `text/markdown` (memos/plans — don't make agents
   write HTML for prose), `application/vnd.duct.table+json` / `text/csv`
   (keyword lists, calendars — sortable table + CSV/XLSX export),
   `text/vnd.mermaid` (funnels, site maps), and
   `application/vnd.duct.diff+json` — the staged-execution **change set as a
   first-class artifact** (Copilot Workspace's lesson: the reviewable
   intermediate is the artifact).
4. **Version UX**: linear picker + prev/next (no branching — nobody ships it),
   "Restore this version" = promote old snapshot to new head,
   "Show changes" diff toggle. Duct can beat incumbents here: structured JSON
   reports diff semantically ("3 new issues, 2 resolved since v2").
5. **Sharing** (when it comes): private by default; explicit publish mints a
   share URL distinct from the app URL; audience tiers (people → workspace →
   public link) with an admin gate; **version pinning** on share links
   ("always latest" vs "sharing v3") — essential for agency→client reports;
   shared HTML served from an **isolated origin** with strict CSP, never the
   app domain; comments with a "send to agent" activation that can produce a
   new version (this closes the audit→execution upsell loop).
6. **Derived exports, not authored binaries**: PDF/XLSX/PNG generated on
   demand per version and cached in object storage keyed by
   (version_id, format). Mirrors Anthropic's split between browser-rendered
   artifacts and its separate file-creation pipeline.
7. **Optimistic concurrency** on writes (base-version id, conflict on stale) —
   cheap now, painful to retrofit.
8. **Defer**: arbitrary React-component artifacts (need a transpile sandbox +
   dependency whitelist + security review). Chart-spec JSON rendered by our
   own components gives the same interactivity with no code execution.

## Sources

claude.ai artifacts: support.claude.com/en/articles/9487310 ·
reidbarber.com/blog/reverse-engineering-claude-artifacts ·
claude.com/blog/claude-powered-artifacts ·
support.claude.com/en/articles/12111783 (file creation) ·
Claude Code artifacts: code.claude.com/docs/en/artifacts ·
ChatGPT Canvas: openai.com/index/introducing-canvas ·
help.openai.com/en/articles/9930697 · canmore spec
(github.com/edoardoavenia/chatgpt-system-prompts) ·
Gemini Canvas: support.google.com/gemini/answer/16047321 ·
Copilot Workspace: github.com/githubnext/copilot-workspace-user-manual
