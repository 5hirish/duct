# Blog Writer Agent — Product & Engineering Plan

**Status:** Draft — pre-implementation
**Last updated:** 2026-05-12

---

## 1. Product Narrative

### Who uses this

Duct's primary users are founders, heads of marketing, and growth leads at B2B and B2C SaaS companies. They are not content writers. They understand their product deeply but lack the time and craft to produce blog posts that balance SEO requirements, brand voice, and conversion intent simultaneously. They already use Duct for SEO auditing and growth intelligence; the Blog Writer is the natural next step — from "here are your organic gaps" to "here is a piece of content that fills one of them."

### The job it does

The Blog Writer Agent produces a single, publication-ready blog post. The job covers:

1. Research — understanding the topic, competitive framing, and what statistics or data points should anchor the piece
2. Structure — generating a reader-tested outline that the user can approve or modify before full writing begins
3. Writing — producing conversion-optimised, SEO-enriched long-form content in the user's brand voice
4. Illustration — deciding where images belong and generating them via the Gemini image API
5. Delivery — packaging the finished post (markdown + images) as a downloadable ZIP

### How it fits in Duct's platform

The SEO Audit agent tells users which content topics and keywords are gaps. The Blog Writer agent fills those gaps on demand. The two agents are complementary and can be invoked sequentially by the user without any backend coupling: the audit report surfaces a content opportunity (e.g. "no blog post targeting 'event-driven architecture monitoring'"), and the user copies that topic into the Blog Writer input form.

This keeps the backend agent boundary clean — Blog Writer is self-contained — while the frontend can add a shortcut affordance ("Write a post about this →") in the Audit report view later.

---

## 2. User Flow

### Step 0 — Setup page (`/blog`)

The user lands on a short setup form. Fields:

- **Product context** (auto-filled from stored business context if available; editable) — product name, one-line description, target audience, voice/tone notes
- **Topic description** (required) — free text, e.g. "Why event-driven architecture is better for real-time analytics"
- **Blog URL** (optional) — if provided, the agent fetches up to 3 recent posts from the site to extract style and tone conventions
- **Target word count** (optional, select: Short ~800w / Medium ~1,500w / Long ~2,500w / Auto-decide)
- **Target keywords** (optional) — comma-separated; agent adds its own research on top

On submit, params are stored in `sessionStorage` and the user is routed to `/blog/[sessionId]`.

### Step 1 — Research (automated, no user action)

The pipeline fires immediately. The agent performs:
- Web searches for the topic (statistics, recent articles, expert takes, competitor content)
- Optionally fetches the provided blog URL for style analysis
- Emits `STEP_STARTED / STEP_FINISHED` SSE events for progress display

### Step 2 — Outline review (suspend + user approval)

Session A completes and emits `OUTLINE_READY`. The frontend renders the outline as a structured card with approve / edit options. The user can:
- Approve as-is
- Type feedback to request structural changes

The backend resumes Session B with the approved or adjusted outline.

### Step 3 — Writing (streaming)

The agent writes the full post, streaming markdown to the frontend in real-time via `BLOG_CHUNK` SSE events. The right panel renders it live.

### Step 4 — Image idea selection (AskUserQuestion pause)

The agent proposes 3–5 image ideas (intro, mid-article section breaks, before CTA). Each idea includes a concept description, placement rationale, and alt text. The frontend renders these as a checklist. The user selects which images to generate.

### Step 5 — Image generation (automated, ~5–15s per image)

For each selected image, the backend calls the Gemini Imagen API. Progress is emitted via `STEP_STARTED / STEP_FINISHED` events per image.

### Step 6 — Final post delivery

Once all images are generated, the agent emits `BLOG_POST_READY`. The right panel shows the complete rendered post with images embedded. A "Download ZIP" button becomes active.

### Step 7 — Download

Clicking "Download ZIP" calls `GET /api/agents/blog-writer/sessions/{id}/download`. The backend assembles the ZIP (markdown + images) and returns it as a binary download.

### Step 8 — Chat (Session C)

The session stays alive. The user can ask follow-up questions ("Make the intro punchier", "Add a FAQ section", "Change the CTA to focus on free trial"). The agent responds conversationally and emits `BLOG_POST_UPDATED` events to update the displayed post.

---

## 3. Agent Pipeline

The Blog Writer uses the same two-session Phase 2 + Phase 3 pattern as the SEO Audit, extended with a pre-agent research phase and an additional outline session.

```
Phase 0 — Research (pure Python, httpx)
  └── Web search calls (Brave Search API)
  └── Optional: URL fetcher for existing blog style analysis
  └── Emits: STEP_STARTED/FINISHED for each sub-task

Session A — Outline generation (ClaudeSDKClient, output_format=BlogOutline schema)
  └── Tools: none (pure structured output)
  └── Backend emits OUTLINE_READY, suspends via asyncio.Future until user approves
  └── Emits: STEP_STARTED, OUTLINE_READY, STEP_FINISHED

Session B — Writing + image ideas (ClaudeSDKClient, streaming, no output_format)
  └── Tools: AskUserQuestion (image selection only), TodoWrite
  └── include_partial_messages=True; text chunks streamed as BLOG_CHUNK events
  └── Emits: BLOG_CHUNK, QUESTIONS_REQUIRED (image ideas), STEP_FINISHED

Phase 4 — Image generation (pure Python, Gemini REST API)
  └── Called outside SDK after image selection answers received
  └── Emits: STEP_STARTED/FINISHED per image, IMAGE_GENERATED

Session C — Chat (ClaudeSDKClient, conversational, no output_format)
  └── Seeded with full blog post content + approved outline
  └── Tools: AskUserQuestion, TodoWrite
  └── Emits: AGENT_MESSAGE_CHUNK, BLOG_POST_UPDATED, MESSAGE_STOP
```

### Why three SDK sessions

`output_format` in the Claude Agent SDK applies session-wide. Mixing `output_format=BlogOutline` with streaming prose in one session breaks both. The three-session split mirrors the audit's Phase 2 / Phase 3 split:

- **Session A** — Outline (structured JSON output; `output_format=BlogOutline`)
- **Session B** — Writing (streaming prose + `AskUserQuestion` for image selection)
- **Session C** — Chat (conversational, seeded with post context)

### Outline approval pattern (no AskUserQuestion for outline)

The outline is a guaranteed, deterministic output of Session A — not a mid-run agent decision. Rather than having the agent call `AskUserQuestion` for it, the backend:

1. Session A completes; backend emits `OUTLINE_READY` with the BlogOutline payload
2. Backend creates `session.answer_future` and blocks Session B from starting
3. User sends `{ type: "answer", answers: { outline_feedback: "..." } }` (empty = approved)
4. `answer_future` resolves; Session B starts with approved outline injected into its user prompt

This is architecturally cleaner than overloading `AskUserQuestion` for structured outline data.

---

## 4. Sub-agent Strategy

The Blog Writer is a **single orchestrator with tools**, not a multi-agent architecture. Reasons:

- A single coherent voice throughout the post is required; sub-agent handoffs require expensive context-passing to maintain tone consistency
- The sequence outline → write → illustrate is strictly linear with user approval gates; there are no parallelisable subtasks that would justify spawning sub-agents
- The audit agent demonstrates this linear pattern works well with the three-session split

---

## 5. Tool Inventory

### Claude Agent SDK allowed_tools

| Tool | Session | Purpose |
|------|---------|---------|
| `AskUserQuestion` | B (image selection), C | Pause and request user decisions |
| `TodoWrite` | B, C | Internal progress tracking |

Session A has no allowed tools — it only generates structured JSON output.

### Phase 0 Python helpers (not SDK tools)

| Helper | Purpose |
|--------|---------|
| `search_topic(query, n=10)` | Calls Brave Search API; returns titles, snippets, URLs for topic research |
| `fetch_blog_page(url)` | httpx GET via existing `service/crawl/fetcher.py`; extracts article text |
| `extract_style_signals(articles)` | Parses tone markers, avg sentence length, vocabulary density from fetched posts |

### Phase 4: Image generation (outside SDK)

| Integration | Detail |
|------------|--------|
| Model | `imagen-3.0-fast-generate-001` (default) / `imagen-3.0-generate-001` (config override) |
| Credentials | `GEMINI_API_KEY` (already in `config.py`) |
| Transport | `httpx.AsyncClient` — same pattern as the audit crawl phase |
| API endpoint | `POST https://generativelanguage.googleapis.com/v1beta/models/{model}:predict?key={key}` |

---

## 6. Schema Design

### `BlogRequest` — POST body

```python
class BlogProductContext(BaseModel):
    product_name: str = ""
    product_description: str = ""    # one-liner
    target_audience: str = ""
    usp: str = ""
    brand_voice: str = ""            # e.g. "confident but approachable, no jargon"
    terminology: list[str] = []      # brand-specific terms to use/avoid

class BlogRequest(BaseModel):
    topic: str                       # required
    product_context: BlogProductContext = Field(default_factory=BlogProductContext)
    blog_url: str = ""               # optional: fetch recent posts for style matching
    target_word_count: int | None = None    # None = agent decides
    keywords: list[str] = []         # optional; agent supplements with research
    engine: str = ""
```

### `BlogOutline` — Session A structured output

```python
class BlogSection(BaseModel):
    heading: str
    level: Literal["h2", "h3"]
    description: str     # what this section covers; 1–2 sentences for the writer
    image_slot: bool = False    # whether an image placeholder belongs here

class BlogOutline(BaseModel):
    title: str
    meta_description: str       # 145–160 chars, primary keyword included
    primary_keyword: str
    secondary_keywords: list[str]
    excerpt: str                # 2–3 sentence teaser for card display
    sections: list[BlogSection]
    estimated_word_count: int
    cta_placement: str          # e.g. "after section 4"
```

### `ImageIdea` — proposed by agent, selected by user

```python
class ImageIdea(BaseModel):
    idea_id: str                      # e.g. "img-01"
    placement_heading: str            # H2/H3 before which the image appears
    concept: str                      # generation prompt description
    rationale: str                    # why this image belongs here
    alt_text: str                     # ready-to-use alt attribute
    aspect_ratio: Literal["16:9", "1:1", "4:3"] = "16:9"
```

### `GeneratedImage` — result of Gemini generation

```python
class GeneratedImage(BaseModel):
    idea_id: str
    filename: str              # e.g. "image-img-01.png"
    base64_data: str           # base64 PNG; in-session only
    media_type: str = "image/png"
    placement_heading: str
    alt_text: str
```

### `BlogPost` — deliverable (versioned)

```python
class BlogPost(BaseModel):
    title: str
    meta_description: str
    primary_keyword: str
    secondary_keywords: list[str]
    excerpt: str               # card teaser
    markdown_body: str         # full markdown; image placeholders: ![alt]({{img-01}})
    images: list[GeneratedImage]
    word_count: int
    generated_at: str          # ISO 8601
    update_label: str = ""
```

Image placeholders in `markdown_body` use `{{img-01}}` tokens. Frontend resolves to `data:image/png;base64,...`. ZIP packager resolves to `./images/image-img-01.png`.

### `BlogSession` — in-memory session dataclass

```python
@dataclass
class BlogSession:
    session_id: str
    agent_type: str = "blog-writer"
    event_queue: asyncio.Queue       # agent → SSE consumer
    chat_queue: asyncio.Queue        # user → agent (Session C)
    answer_future: asyncio.Future | None   # AskUserQuestion / outline approval bridge
    created_at: float = 0.0
    post_versions: list[VersionedBlogPost] = field(default_factory=list)
    outline: BlogOutline | None = None
    image_ideas: list[ImageIdea] = field(default_factory=list)
    generated_images: list[GeneratedImage] = field(default_factory=list)
```

---

## 7. SSE Events

All events carry `session_id` and `ts` (added by `_emit_to_queue`).

Defined in `backend/agents/blog/events.py` (mirrored in `app/src/lib/blogEvents.js`).

| Event | Payload | Purpose |
|-------|---------|---------|
| `step_started` | `{ step_id, label, status }` | Reuses audit shape |
| `step_finished` | `{ step_id, label, status, payload? }` | Reuses audit shape |
| `questions_required` | `{ question_type, questions }` | Reuses audit shape + `question_type` discriminator |
| `outline_ready` | `{ outline: BlogOutline }` | Outline generated; frontend shows review card |
| `blog_chunk` | `{ text }` | Streaming prose tokens during writing |
| `image_generated` | `{ idea_id, filename, base64_data, media_type, placement_heading, alt_text }` | One image done |
| `blog_post_ready` | `{ version_id, label, payload: BlogPost }` | Full post assembled |
| `blog_post_updated` | `{ version_id, label, payload: BlogPost }` | Post updated by chat |
| `agent_message_chunk` | `{ text }` | Chat streaming (Session C) |
| `message_stop` | `{}` | Turn complete |
| `pipeline_finished` | `{ status }` | All phases done |
| `pipeline_failed` | `{ status, error }` | Error path |
| `todo_update` | `{ todos }` | Reuses audit shape |

**`question_type` discriminator** on `questions_required`:
- `"general"` — standard Q&A (same as audit)
- `"outline_approval"` — outline feedback text area (frontend renders `BlogOutlineCard`)
- `"image_selection"` — image checklist (frontend renders `BlogImagePicker`)

### Step IDs

| Step | Label |
|------|-------|
| `research_topic` | "Researching topic" |
| `fetch_blog_style` | "Analysing blog style" |
| `generate_outline` | "Building outline" |
| `write_post` | "Writing post" |
| `generate_images` | "Generating images" |
| `assemble_post` | "Assembling final post" |

---

## 8. Backend File Structure

```
backend/agents/blog/
├── __init__.py
├── events.py          # BlogEvent StrEnum, BlogStep StrEnum, STEP_LABELS dict
├── schema.py          # All data models above
├── prompts.py         # build_outline_system_prompt(), build_outline_user_prompt(),
│                      # build_write_system_prompt(), build_write_user_prompt(),
│                      # build_chat_system_prompt(), build_chat_seed_message()
└── v3/
    ├── __init__.py
    └── runner.py      # ClaudeBlogRunner + phase functions:
                       #   run_research()            ← Phase 0
                       #   run_outline_session()     ← Session A
                       #   run_write_session()       ← Session B
                       #   run_image_generation()    ← Phase 4 (Gemini REST)
                       #   run_chat_session()        ← Session C
                       #   run_pipeline()            ← orchestrates all
                       # session registry:
                       #   create_blog_session(), get_session(), close_session()

backend/service/web/
├── __init__.py
├── search.py          # search_topic(query, n) → list[SearchResult]
│                      # Brave Search API (BRAVE_SEARCH_API_KEY); stubs when key absent
└── fetcher.py         # fetch_page_text(url) → str
                       # Thin wrapper over service/crawl/fetcher.py

backend/service/blog/
├── __init__.py
└── packager.py        # build_zip(session: BlogSession) → bytes
                       # Assembles post.md + images/ subfolder via zipfile stdlib
```

### Routes additions (`backend/routes/agents.py`)

- Import `BlogRequest`, `ClaudeBlogRunner`, blog session helpers
- Add `_start_blog_writer()` dispatcher function
- Add `elif agent_type == AgentType.BLOG_WRITER:` branch in `_dispatch_start()`
- Add download route:

```
GET /api/agents/blog-writer/sessions/{session_id}/download
→ build_zip(session) → StreamingResponse(media_type="application/zip")
```

Register this route **before** the generic `GET /{type}/sessions/{id}` route to avoid FastAPI path conflicts.

### Config additions (`backend/config.py`)

```python
brave_search_api_key: str = ""
gemini_image_model: str = Field(default="imagen-3.0-fast-generate-001")
```

`gemini_api_key` already exists and is reused for the Imagen API.

---

## 9. Frontend Design

### Routes

```
app/src/app/(app)/blog/
├── page.jsx                  # Setup form (BlogSetupPage)
└── [sessionId]/
    └── page.jsx              # Session workspace (BlogWorkspace)
```

### Components

```
app/src/components/blog/
├── BlogWorkspace.jsx         # Split-panel orchestrator (mirrors AuditWorkspace.jsx)
├── BlogChat.jsx              # Left panel: steps, chat, question cards
├── BlogPostPreview.jsx       # Right panel: live markdown render + images
├── BlogOutlineCard.jsx       # Outline approval UI (approve / feedback textarea)
├── BlogImagePicker.jsx       # Image idea checklist with concept text
├── BlogImagePreview.jsx      # Single generated image with status indicator
└── BlogDownloadButton.jsx    # Disabled until blog_post_ready; triggers ZIP download
```

### Split-panel layout

50/50 horizontal split, draggable divider, width persisted in `localStorage` as `blog_split_w`.

**Left panel (Chat):**
- Step progress bar: Research → Outline → Writing → Images → Done
- Chat bubble history
- `BlogOutlineCard` when `question_type === "outline_approval"`
- `BlogImagePicker` when `question_type === "image_selection"`
- Chat input (active after `blog_post_ready`)

**Right panel (Post Preview):**
- Header: "Blog Post" + version dropdown + Download button
- Live markdown render during `blog_chunk` streaming (`react-markdown` + `remark-gfm`)
- Inline `<img>` from base64 data when `image_generated` events arrive
- Skeleton loader before any content appears

### Outline approval card (`BlogOutlineCard.jsx`)

- Displays proposed title (H1 preview)
- Numbered list of H2 sections with H3 sub-items
- "Approve" button (primary)
- "Give feedback" toggle → text area for structural notes
- Sends `{ type: "answer", answers: { outline_feedback: "" | "notes..." } }`

### Image picker (`BlogImagePicker.jsx`)

- Heading: "Select images to generate"
- Checkbox list: concept text + placement label + alt text preview per idea
- "Select All" / "Deselect All" shortcuts
- "Generate selected" button

### Download

```js
async function handleDownload() {
  const resp = await fetch(`/api/agents/blog-writer/sessions/${sessionId}/download`, {
    headers: backendApiHeaders()
  });
  const blob = await resp.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `blog-${slugify(title)}.zip`;
  a.click();
  URL.revokeObjectURL(url);
}
```

---

## 10. Image Generation

### Model

Default: `imagen-3.0-fast-generate-001` (~5–8s per image, lower cost)  
Override: `imagen-3.0-generate-001` (higher quality, ~10–15s) via `cfg.gemini_image_model`

### API

```
POST https://generativelanguage.googleapis.com/v1beta/models/{model}:predict?key={GEMINI_API_KEY}
{
  "instances": [{ "prompt": "{concept}" }],
  "parameters": {
    "sampleCount": 1,
    "aspectRatio": "16:9",
    "safetyFilterLevel": "block_some"
  }
}
```

Response: `predictions[0].bytesBase64Encoded` (PNG).

### Prompting strategy for images

The writing agent is instructed to produce `concept` fields that follow this structure:

> `"{Style descriptor} illustration/photo of {subject} showing {key visual elements}, {mood/color direction}, minimal text, suitable for a professional blog post"`

Example: `"Clean flat-design illustration of event streams as glowing arrows flowing between microservices on a dark navy background, electric blue and white accents, no text"`

### Placeholder resolution

- **Markdown body:** `![{alt_text}]({{img-01}})` tokens in the agent's output
- **Frontend:** replaces `{{img-01}}` with `data:image/png;base64,{base64_data}`
- **ZIP packager:** replaces `{{img-01}}` with `./images/image-img-01.png` and writes PNG to ZIP

---

## 11. Download Packaging

### ZIP structure

```
blog-{slug}.zip
├── post.md
└── images/
    ├── image-img-01.png
    ├── image-img-02.png
    └── ...
```

`post.md` includes YAML front matter + full markdown body with `./images/` references.

### Front matter template

```yaml
---
title: "{title}"
date: "{YYYY-MM-DD}"
meta_description: "{meta_description}"
excerpt: "{excerpt}"
keywords: [{primary_keyword}, {secondary_keywords}]
---
```

### `backend/service/blog/packager.py`

```python
def build_zip(session: BlogSession) -> bytes:
    post = session.post_versions[-1].post
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        md = _resolve_placeholders(post.markdown_body, post.images)
        zf.writestr("post.md", _front_matter(post) + md)
        for img in post.images:
            zf.writestr(f"images/{img.filename}", base64.b64decode(img.base64_data))
    return buf.getvalue()
```

---

## 12. Registry Updates

### `backend/agents/registry.py`

Activate `BLOG_WRITER` and add `VERSIONED_OUTPUT`:

```python
def _blog_writer_spec() -> AgentSpec:
    from agents.blog.schema import BlogRequest
    return AgentSpec(
        type=AgentType.BLOG_WRITER,
        name="Blog Writer",
        description=(
            "SEO-optimised blog content generation. Researches your topic, drafts a "
            "conversion-focused post in your brand voice, generates images, and "
            "delivers a ready-to-publish ZIP."
        ),
        capabilities=[
            AgentCapability.STREAMING,
            AgentCapability.INTERACTIVE_QUESTIONS,
            AgentCapability.VERSIONED_OUTPUT,
            AgentCapability.CHAT,
        ],
        config_schema=BlogRequest.model_json_schema(),
        active=True,
    )
```

---

## 13. Prompt Design Notes

### Outline system prompt (Session A)

```
You are an expert content strategist and SEO writer.

Rules:
- Title (H1): compelling, keyword-rich, under 65 characters
- 4–7 H2 sections; H3s only for sections with 3+ sub-topics
- Each section description tells a writer exactly what to cover in 2–3 sentences
- Mark exactly 3 sections with image_slot: true (after intro, mid-article, before CTA)
- meta_description: 145–160 chars, primary keyword included, benefit-first framing
- excerpt: 2–3 sentence teaser for card display; no spoilers
```

### Writing system prompt (Session B)

```
You are an expert B2B/B2C content writer. Write the full blog post as markdown
following the approved outline exactly.

Rules:
- Write in the brand voice specified in the product context
- Target word count: {target_word_count} (or auto-decide for best conversion)
- Place image placeholders as ![{alt_text}]({{img-01}}) at image_slot positions
  and populate the corresponding ImageIdea for each
- Weave CTAs: one soft CTA mid-article, one hard CTA at end
- Anchor claims with statistics from the research context provided
- After completing the post body, call AskUserQuestion with question_type="image_selection"
  and the 3–5 ImageIdea objects as the question payload
```

### Chat system prompt (Session C)

Seeded with: full BlogPost JSON (minus base64 image data to keep prompt size manageable) + approved outline + Q&A history. Conversational; responses wrap any post updates in `<blog_post_update>` tags (mirroring the audit's `<audit_report_update>` pattern).

---

## 14. Open Questions and Decisions Needed

### Q1: Brave Search API key
Phase 0 research uses Brave Search. A `BRAVE_SEARCH_API_KEY` must be procured and added to the Railway environment. Without it, the runner stubs empty research results (post can still be written from product context alone, but with lower factual richness).

### Q2: Gemini Imagen API access path
Confirm whether `imagen-3.0-fast-generate-001` is accessible via the Google AI Studio key (`GEMINI_API_KEY`) or requires a Vertex AI service account. If Vertex AI, a `GOOGLE_APPLICATION_CREDENTIALS` service account JSON must be added to Railway env.

### Q3: Session registry isolation
Currently `routes/agents.py` prunes only the audit's `_sessions` dict. Adding a Blog Writer session store requires either (a) updating the pruner to also iterate blog sessions, or (b) refactoring to a shared `agents/sessions.py` registry. Option (b) is cleaner and should be done before both agents run in production to prevent memory leaks.

### Q4: In-memory image storage at scale
Base64 PNG images at 1024×576 run ~150–400KB each. At 3–5 images/session × 50 concurrent sessions = 25–100MB in-memory. Acceptable for Railway Starter plan MVP. For scale, offload to R2/S3 with pre-signed URLs and a session-scoped TTL.

### Q5: ZIP download route conflict
Register `GET /blog-writer/sessions/{id}/download` before the generic `GET /{type}/sessions/{id}` route in FastAPI to avoid path matching conflicts.

---

## 15. Implementation Sequence

1. `backend/agents/blog/events.py`
2. `backend/agents/blog/schema.py`
3. `backend/agents/blog/prompts.py`
4. `backend/service/web/search.py` + `fetcher.py`
5. `backend/service/blog/packager.py`
6. `backend/agents/blog/v3/runner.py`
7. `backend/routes/agents.py` — dispatcher + download endpoint
8. `backend/agents/registry.py` — activate spec
9. `backend/config.py` — Brave Search key + image model fields
10. `app/src/lib/blogEvents.js`
11. `app/src/components/blog/` — all workspace components
12. `app/src/app/(app)/blog/` — setup page + session page
13. `app/src/lib/api.js` — add `downloadBlogPost()`

## Critical reference files

- [backend/agents/audit/v3/runner.py](../../backend/agents/audit/v3/runner.py) — direct structural template; every phase function and session lifecycle pattern mirrors this
- [backend/agents/audit/schema.py](../../backend/agents/audit/schema.py) — `AuditSession`/`VersionedReport` dataclass pattern to replicate
- [backend/routes/agents.py](../../backend/routes/agents.py) — `_dispatch_start()` and session wiring
- [app/src/components/audit/AuditWorkspace.jsx](../../app/src/components/audit/AuditWorkspace.jsx) — split-panel + SSE event handling pattern
- [backend/agents/registry.py](../../backend/agents/registry.py) — activate the existing `BLOG_WRITER` spec

## Verification

After implementation:

1. `POST /api/agents/blog-writer/sessions` with a `BlogRequest` — verify session created and SSE stream opens
2. Stream emits `step_started` for research, then `outline_ready`, then pauses waiting for answer
3. Send outline approval answer — stream resumes with `blog_chunk` events
4. After writing completes, `questions_required` with `question_type: "image_selection"` appears
5. Send image selection — each selected image produces `image_generated` events, then `blog_post_ready`
6. `GET /api/agents/blog-writer/sessions/{id}/download` returns a valid ZIP with `post.md` and `images/`
7. Chat follow-up produces `agent_message_chunk` events and optionally `blog_post_updated`
