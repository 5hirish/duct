# TikTok Research MCP

A global [MCP](https://modelcontextprotocol.io) server for **TikTok research &
discovery** via [Apify](https://apify.com). Search TikTok by keyword or hashtag,
deconstruct a specific post URL, and fetch media on demand for visual analysis —
from **Claude Code** or the **Claude Desktop** app, on any project.

Extracted from the Duct backend's Apify integration (`backend/service/apify`) as
a self-contained package with no dependency on the backend or its database.

## Design

- **Searches are cheap by default.** Keyword/hashtag/URL tools return compact
  post metadata + media *URLs* only — never media bytes. Media is downloaded only
  when you explicitly call `fetch_tiktok_media`.
- **One actor.** All discovery uses `clockworks/tiktok-scraper`. Each search is
  **one billable Apify actor run** — keep `results_per_page` small while exploring.
- **Run-and-wait.** Search tools start the run and poll to completion (bounded by
  `max_wait_s`). If a run is slow, they return a `dataset_id`; call
  `get_tiktok_results(dataset_id)` to fetch once it finishes.

## Tools

| Tool | Purpose |
| --- | --- |
| `search_tiktok_by_keyword` | Full-text TikTok search (`searchQueries`). |
| `search_tiktok_by_hashtag` | Posts for one or more hashtags (`hashtags`). |
| `scrape_tiktok_url` | Deconstruct specific post/video URLs (`postURLs`). |
| `get_tiktok_results` | Finish / re-fetch a run's dataset by id. |
| `fetch_tiktok_media` | On-demand: `kind="images"` → inline images; `kind="video"` → saves `.mp4` to a temp path. |

Each search result includes: `url`, `caption`, `created_at`, `stats`
(views/likes/comments/shares/saves), `author`, `music`, `duration_s`, `hashtags`,
`cover_url` / `original_cover_url`, `slideshow_image_links`, `is_ad`,
`is_sponsored`, `language`. Pass the image URLs to `fetch_tiktok_media` to view them.

## Setup

Requires [`uv`](https://docs.astral.sh/uv/) and Python ≥ 3.11.

```bash
cd mcp/tiktok-research
uv sync
```

Set your Apify token (create one at
https://console.apify.com/account/integrations):

```bash
cp .env.example .env   # then edit APIFY_API_KEY=...
```

The server reads `APIFY_API_KEY` (fallback `APIFY_TOKEN`) from its process env.
The registration snippets below pass it via the MCP config's `env` block.

### Optional env

- `TIKTOK_MCP_DEFAULT_RESULTS` (default `20`)
- `TIKTOK_MCP_MAX_WAIT_S` (default `120`)
- `TIKTOK_MCP_MEDIA_DIR` (default OS temp dir) — where `kind="video"` saves `.mp4`.

## Register globally

Replace `<ABS>` with the absolute path to this directory
(`.../duct/mcp/tiktok-research`).

### Claude Code (user scope — available in every project)

```bash
claude mcp add tiktok-research --scope user \
  --env APIFY_API_KEY=<your-token> \
  -- uv run --directory <ABS> tiktok-research-mcp
```

Verify with `/mcp` inside Claude Code, then try:
_"Search TikTok for the keyword 'cold plunge', 5 results."_

### Claude Desktop (Mac)

Edit `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "tiktok-research": {
      "command": "uv",
      "args": ["run", "--directory", "<ABS>", "tiktok-research-mcp"],
      "env": { "APIFY_API_KEY": "<your-token>" }
    }
  }
}
```

Restart Claude Desktop.

## Local smoke test (no Claude)

Inspect the tools with the MCP Inspector:

```bash
npx @modelcontextprotocol/inspector uv run --directory . tiktok-research-mcp
```

## Cost note

Every keyword/hashtag/URL search triggers a metered Apify actor run, and
`fetch_tiktok_media(kind="video")` triggers another (media-enabled) run. Keep
`results_per_page` low while testing.

## Not included (future)

- **claude.ai web/mobile** connector — needs a remote HTTP transport + hosting +
  OAuth. The tool layer is transport-agnostic, so this is an additive mode.
- Trending-feed tool (`clockworks/free-tiktok-scraper`), profile/competitor
  scrape with comments, and video-understanding handoff.
