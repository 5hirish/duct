# Agent memory — the converged taxonomy and the UX patterns

Reference notes extracted from the memory research of 2026-08-28. The full report
(product internals, frameworks, the Duct design) is
[`agent-memory-research.html`](agent-memory-research.html); this file keeps the two
parts worth re-reading on their own — **what the literature converged on** and
**which product patterns make memory feel personal rather than surveillant** — so
they can be cited from design docs without opening the report. arXiv ids are given
inline; sources are at the bottom.

---

## Part A · Synthesis — the taxonomy the field converged on

### 1. Where memory lives (form / substrate)

- **Parametric** — in weights: fine-tuning, LoRA "personal models" (Second Me,
  2503.08102), knowledge editing. Fast and implicit; hard to audit or delete.
- **Non-parametric / contextual / token-level** — text or structured records outside
  the model, injected at inference. Subdivided by topology:
  - flat lists (MemGPT's queue, Mem0 facts),
  - planar graphs and trees (A-MEM notes + links 2502.12110, HippoRAG knowledge
    graph 2405.14831, RAPTOR summary tree 2401.18059),
  - hierarchical / multi-layer (Zep episodes → entities → communities 2501.13956;
    MemoryBank turns → daily → global summaries 2305.10250).
- **Latent** — KV-cache / activation memory (MemOS's "activation" tier, 2507.03724).
  Emerging.
- HippoRAG 2 (2502.14802) reframes the whole space as **non-parametric continual
  learning**; MemOS treats migration across the three substrates (plaintext →
  activation → parameter) as a lifecycle, with a `MemCube` carrying provenance,
  timestamps, version, access control, priority and usage stats.

### 2. What memory is for (function)

The cognitive-science trio plus working memory is now the shared vocabulary:

| Class | What it holds | Representative systems |
|---|---|---|
| **Working** | the context window itself | MemGPT main context, Letta core blocks, MIRIX Core |
| **Episodic** | time-stamped events and experiences ("what happened when") | Generative Agents memory stream, MIRIX Episodic, Zep episodes, MemMachine verbatim episodes |
| **Semantic** | distilled facts, preferences, profiles | Mem0 facts, MemoryBank portrait, Zep entity edges, Hindsight world facts + entity summaries |
| **Procedural** | how-to knowledge and skills | MIRIX Procedural, CLAUDE.md / skills, MemP, LEGOMem |

Two refinements from 2025:

- The 47-author survey "Memory in the Age of AI Agents" (2512.13564) re-cuts function
  as **factual** (about the user / the environment / the agent itself) vs
  **experiential** (case-based, strategy-based, skill-based) vs **working**, and
  forms as token-level / parametric / latent, with dynamics of formation, evolution
  and retrieval.
- Hindsight (2512.12818) adds **beliefs** as a distinct, revisable network alongside
  world facts, agent experiences and entity summaries, with traceable belief
  updates (retain / recall / reflect).
- MIRIX (2507.07957) is the widest product-style split: **Core, Episodic, Semantic,
  Procedural, Resource** (documents, files, images) and **Knowledge Vault**
  (credentials, addresses, sensitive verbatim data), each owned by a specialised
  memory-manager agent under a meta manager.

### 3. Retrieval strategies

- Scoring evolved from **relevance + recency + importance** (Generative Agents,
  2304.03442: exponential recency decay, LLM-rated importance 1–10 at write time,
  embedding relevance, each min-max normalised) → **hybrid dense + sparse (BM25) +
  graph traversal** (Zep; HippoRAG's Personalized PageRank) → **reranking**
  (RRF / MMR / cross-encoder). 2026 production systems fuse semantic, lexical and
  entity signals.
- **Explicit tool-based retrieval** (MemGPT `recall_search`, Claude's
  `conversation_search`) vs **automatic injection** (ChatGPT's system-prompt sections,
  Mem0 pre-fetch). The former is visible and decision-making; the latter is seamless
  but opaque.
- **Query construction matters as much as the index.** LongMemEval (2410.10813):
  decompose sessions into rounds; **fact-augmented key expansion** (index each round
  with extracted user facts: +9.4% recall, +5.4% accuracy); **time-aware query
  expansion** (an LLM extracts the time range from the question: +6.8–11.3% recall
  on temporal questions); Chain-of-Note reading (+up to 10 pts even with perfect
  retrieval). MIRIX's **active retrieval** generates a topic first, then searches the
  relevant stores. T-Mem (2606.15405) writes **triggers at encode time** — the future
  contexts in which a memory will be needed.

### 4. Consolidation and reflection

- **Write path:** extract → dedupe / merge → ADD / UPDATE / DELETE / NOOP (Mem0
  2504.19413) → link and evolve neighbours (A-MEM: new notes may rewrite the
  context and tags of existing notes) → **invalidate rather than delete** (Zep).
- **Offline path:** reflection trees (Generative Agents — reflection fires when the
  sum of recent importance crosses a threshold; the agent asks the three most
  salient questions, retrieves against them and generates insights **with citations
  to the evidence records**), daily → global summaries (MemoryBank), sleep-time
  agents rewriting memory blocks (Letta; sleep-time compute 2504.13171 gives ~5×
  less test-time compute for the same accuracy, best when queries are
  predictable), "Dreaming" (ChatGPT), "Auto Dream" (Claude Code).
- **Consensus:** consolidation should run *between* interactions, produce
  *traceable* abstractions (citations back to evidence), and be re-runnable.
- **Forgetting:** Ebbinghaus decay (MemoryBank — retention `R = e^(−t/S)`, strength
  `S` +1 on each recall, elapsed time reset on recall), heat scores (MemoryOS
  2506.06326), decay-weighted recency (Supermemory), explicit deletion / unlearning
  (Always-On Agents survey 2606.30306).

### 5. Temporal validity of facts

- **Bi-temporal modelling** — event time (`valid_at` / `invalid_at`) vs transaction
  time (`created_at` / `expired_at`) — with **supersession instead of deletion** is
  the accepted answer (Zep/Graphiti, Supermemory, MemStrata 2606.26511). "What did
  we believe on date X" becomes answerable.
- **Freshness resolution should be deterministic code, not LLM judgement.** "Don't
  Ask the LLM to Track Freshness" (2606.01435) and MemStrata: vanilla RAG serves
  superseded facts 15–40% of the time; a `(subject, relation)` supersession rule in a
  bi-temporal ledger drives that to ~0%.
- MemConflict (2605.20926) defines memory validity as query-conditioned fitness for
  use along three axes: temporal validity, factual correctness, contextual
  applicability. Benchmarks now test knowledge updates and abstention explicitly
  (LongMemEval).
- **Evidence before belief.** Eywa (2605.30771) stores immutable source evidence
  *before* deriving canonical facts, validates extractions against source support,
  and keeps retrieval deterministic (no LLM calls inside retrieval). MemIR
  (2605.25869) names the failure mode — **provenance-role collapse** — and types
  atoms as evidence / cue / claim. MemMachine (2604.04853) keeps verbatim episodes
  alongside profile memory to avoid compounding lossy extraction.

### 6. Evaluation

- LoCoMo (2402.17753) and LongMemEval (2410.10813) dominate; BEAM (ICLR 2026) pushes
  to 1M–10M tokens and adds event ordering and contradiction resolution.
- "Anatomy of Agentic Memory" (2602.19320): benchmarks saturate (LoCoMo fits in a
  context window; LLM-judge scores cluster at 85–92%); F1 misranks systems versus
  semantic judges; small backbones silently corrupt structured memories (format
  errors up to 30%); maintenance cost is hidden (MemoryOS ~32 s/query vs ~1 s for a
  simple store).
- The next frontier is scale ("temporal abstraction at scale": Mem0's BEAM score
  drops 64 → 49 from 1M to 10M tokens), **contextual integrity** (CIMemories
  2511.14937: frontier models leak inappropriate attributes in up to 69% of cases,
  behave binary share-all / share-nothing, and get worse with usage — privacy
  prompting does not fix it) and **governance** (Always-On Agents: six axes —
  authority, scope, mutability, provenance, recoverability, actionability — and
  the observation that *proactive* recall is much harder than query-driven recall).

---

## Part B · UX patterns for memory that feels personal, intelligent and alive

### B1. Provenance — showing which memory or past conversation an answer draws on

| Pattern | Product examples | Notes |
|---|---|---|
| **Citation chips that link back to the source chat** | **Claude** — references to earlier conversations carry citations linking to the original chats, with an inline option to delete that conversation | Provenance and control in one place |
| **Visible retrieval as a tool call** | **Claude** exposes `conversation_search` / `recent_chats` as visible tool calls, so you see exactly when and how it accesses previous context; ChatGPT injects memory silently at conversation start | Willison's critique of ChatGPT: silent injection makes fresh starts hard and carries bad context forward |
| **Jump-to-source from synthesised answers** | **Granola** — every Chat answer has inline citations to the meeting note / transcript line; double-click surfaces the exact excerpt and speaker; folder-level queries cite specific meetings and timestamps | The best "evidence before belief" UX outside chat assistants |
| **"Which of your data did I use?"** | **Gemini** — ask "Did you use any info from past chats?"; Personal Intelligence (opt-in, per source) tries to reference which sources informed a response | Provenance on request, not by default |
| **Excerpts of the chats referenced** | **Grok** — a book icon under a response opens a sidebar with excerpts from the previous chats it referenced, each with **Forget** | |
| **Receipts by default** | **Mistral Le Chat** — "you'll always see what memory is in play, with links to the source"; **Perplexity Brain** — each memory shows its origin session, file or connector | |
| **Memory sources** | **ChatGPT** (May 2026) — book icon lists which memories / past chats / files / custom instructions personalised a response, with "why this was used" and correct / delete / not-relevant; explicitly not exhaustive | |
| **Anti-pattern: invisible profile injection** | **ChatGPT** (2025) — hidden system-prompt sections (Model Set Context, Assistant Response Preferences, Notable Past Conversation Topics, Helpful User Insights, ~40 Recent Conversation Content digests, User Interaction Metadata), none inspectable. Smashing Magazine's case: a "Half Moon Bay" sign silently added to a generated image from a prior chat — "no log, no timeline" | Smashing's proposed fix is an **Audit Trail / "Show Work"** pattern: a replayable log of what context was used |
| **Architectural provenance** | Mem0 **OpenMemory** dashboard logs every read/write per app; MemOS `MemCube` metadata carries source and version; Eywa / Hindsight keep evidence pointers and traceable belief updates | Extraction-only stores (facts without episodes) cannot cite |

### B2. Timeline UIs for memory and history

| Pattern | Product examples |
|---|---|
| **Scrubbable timeline of snapshots** | **Windows Recall** — search box + scrubbable timeline of screen snapshots with dates, a "Now" button, **Click to Do** to act on elements inside a snapshot; opt-in, encrypted, on-device, app/site exclusions, per-snapshot delete, full reset/export. **Rewind.ai** (2022–24) let you drag a range on the timeline and ask AI about that period; rebranded to Limitless in Apr 2024 and shut down after Meta's Dec 2025 acquisition |
| **Lifelog: day → auto-titled moments → summary / transcript** | **Limitless Pendant** — the Lifelog tab organises the day into conversations with summaries, action items and transcripts, plus "ask AI about your lifelogs"; recordings auto-delete after 30 days unless saved; Consent Mode chimes and pauses recording. **Bee** (Amazon) — segments each conversation into auto-titled sections with per-section summaries, an end-of-day recap with sentiment and commitments, daily "insights and patterns", and a **Facts** list of long-term things to remember that Bee *proposes* for the user to accept or edit |
| **Radial memory timeline** | **Hermes Agent** `/journey` / Star Map — memories and skills as a zoomable node graph on radial time rings (core = oldest, outer rings = newer), scrubbable playback, All / Used / Learned filter, edit or delete nodes in place |
| **Relationship / record timeline with AI roll-ups** | **Attio** — shared per-record timelines (emails, notes, calls) plus AI attributes that summarise calls and notes into fields; **HubSpot** — timeline consolidates touchpoints into a customer journey |
| **Periodic reflective summaries** | **Rosebud** — persistent memory across the journal, weekly summaries that reflect patterns back, an annual "Wrapped" (archetypes, arcs, moments); **Bee** daily recap; **Replika** Diary — first-person entries the companion writes about your chats every day or two, which you can like, edit or delete; **Dot** (New Computer, shut down Oct 2025) — "a living journal, a chronicle of life that talks back" with proactive follow-ups referencing past chats |
| **Resurfacing instead of browsing** | **Mem 2.0 "Heads Up"** auto-resurfaces related notes, topics and meeting timelines in context; **Reflect** uses auto-backlinks to people and projects as the retrieval scaffold |
| **Timestamps on memories themselves** | ChatGPT's Manage memories list shows entry text left, date added right; Claude Code stamps auto-memory files with a `modified` ISO timestamp "so both you and Claude can see how current the fact is" |

### B3. Trust and control

**Save-time signalling**

- **"Memory updated" chip** under the assistant message in ChatGPT when a fact is
  saved; Meta AI supports explicit "remember this" alongside automatic saves with
  review / update / delete; Copilot shows a "Memory updated" notification; Claude
  Code prints "Saved N memories" / "Recalled N memories" (filenames clickable);
  Hermes has `memory_notifications: off | on | verbose`. ShapeofAI's pattern
  guidance: "signal memory capture in real time".

**Review / edit / delete**

- **ChatGPT:** Settings → Personalization → Manage memories: each saved entry as a
  row with date, hover-to-delete, "Clear all", global toggle; legacy split toggles
  "Reference saved memories" vs "Reference chat history". From June 2026
  ("Dreaming") the list is replaced by a **synthesised memory summary organised by
  category** (professional context, communication style, technical level,
  preferences, goals) that users edit by highlighting text or typing a correction,
  plus **topic controls for what ChatGPT may bring up unprompted vs leave alone**.
- **Claude:** Settings → Memory lists remembered **Topics**; open one to read, edit
  or delete; changes apply to the next conversation; **project-scoped** memory kept
  separate from non-project chats; **pause** (keep existing, stop new) vs **reset**
  (delete all); org owners can disable memory; memory **import / export** to and
  from other AI tools; sensitive topics (health, race, religion, politics…) only
  stored on opt-in; extensive safety testing on wellbeing topics before launch.
- **Gemini:** "Personal context → Your past chats" toggle (on by default); correct
  Gemini in chat; delete source chats from activity to forget; no per-fact editor for
  inferred memories.
- **Microsoft 365 Copilot:** view / edit / delete saved memories; personalisation
  toggle; "Ask me 10 questions about myself" onboarding; admin data-processing
  control; chat-history inferences purge 7 days after the source chats are deleted
  and 30 days after personalisation is disabled.
- **Claude Code:** `/memory` opens the plain-Markdown memory folder; auto memory
  limited to four kinds (`user`, `feedback`, `project`, `reference`), skips anything
  derivable from the codebase; disable per project or via env var.
- **Hermes Agent:** `write_approval: true` stages every write for `/memory pending`,
  `/memory approve <id>`, `/memory reject <id>`; `hermes journey list | delete | edit`.
- **Mem0 OpenMemory:** filter memories by app / category / date, pause individual
  memories, revoke an app's access, per-read audit log.
- **Character.AI (May 2026):** Story Memory with pins protected from compaction;
  auto-captured Facts per persona / character / side character with add / edit /
  disable / delete and copy-to-new-chat; a **Memory Usage** bar showing what fills
  memory.

**"What do you know about me?"**

- Supported conversationally in Claude, ChatGPT, Gemini and Copilot; Claude's help
  centre frames the Topics list as the answer. CHI 2026 research ("Relational Gains,
  Privacy Strains", Chen, Molina, Liao, Snyder) shows this moment is where trust
  breaks: most of 20 interviewees had **negative expectancy violations** on seeing
  what ChatGPT remembered — unforgetting, over-detailed, emotionless — and asked for
  more visibility, accessibility, transparency and control.

**Scope, opt-out, incognito**

- **Ephemeral mode is a shared contract:** ChatGPT Temporary Chat (deleted within
  30 days; since Jan 2026 keeps preferences but not content; since Aug 2026
  personalised or non-personalised, with "save to history"), Claude Incognito (ghost
  icon; not saved, not searchable, not in memory), Gemini Temporary Chat (72-hour
  retention, no personalisation or training).
- **Scoped memory** (per project / workspace) is the consensus mitigation for
  context bleed: Claude Projects, ChatGPT project-only memory (forced on shared
  projects), Claude Code per-repo, Perplexity Spaces, Hermes profiles, Mem0 per-app
  ACLs. TechPolicy.press argues project separation is a *contextual-integrity*
  safeguard, not just a productivity feature.
- **Default-on vs opt-in:** Gemini past chats and ChatGPT memory are default-on;
  Gemini Personal Intelligence, Windows Recall and Limitless Consent Mode are
  opt-in. A 300-user contextual-integrity survey (2508.06760) found 82% rate chatbot
  conversations as sensitive or highly sensitive — more than email — yet about half
  discuss health and a third finances.

**What users say they want**

- 18 interviews on RAG-based memory (2508.07664): incomplete mental models; wanted
  review / edit / delete, **categorisation** of memories, transparency about how
  inferred data is used, and control over generation and updating.
- ShapeofAI's Memory pattern checklist: never hide memory; distinguish preferences
  from identity facts; support code-switching (work vs personal); global vs scoped vs
  ephemeral; a knowledge map; editable details; easy reset.
- AI UX Playground's memory-management pattern: list with count and search; inspect
  (text, category, last updated); inline edit; manual add; delete with confirm;
  **label declared vs inferred**; explain pause vs delete.
- A 2026 memory design guide (hidekazu-konishi.com) proposes a record envelope
  `{source, confidence, written_at, last_confirmed_at, expires_at, validity_basis,
  supersedes}`, TTL per memory type, usage-based decay and staleness re-verification.

### B4. Proactive recall — done well vs creepy

**What the evidence says about the boundary**

- **Contextual vs identity personalisation:** "given what you are doing right now,
  here is something relevant" is welcomed; "given everything we know about who you
  are, here is what we think you need" is resisted. Comfort drops sharply for
  devices that seem to be listening and for **connecting information across
  unrelated contexts without explicit permission**. Only 42% trust businesses to use
  AI ethically; 71% trust more when data use is clearly explained; a 2026 Usercentrics
  report found only 8% fully comfortable with AI assistants accessing data without
  conditions.
- **Contextual integrity** (Nissenbaum) is the frame most research uses: the same
  fact is appropriate in one task and a violation in another. CIMemories shows
  models cannot yet make that call reliably, so the *product* must enforce scope
  rather than trusting the model's judgement.
- **Expectancy violation is the mechanism of creepiness** (CHI 2026): users are
  startled by detail they did not know was stored, by recall of things they consider
  forgotten, and by inferences they never stated. Bee's reviewers draw the same
  line: recap of a business call = useful; 24/7 eavesdropping in personal life =
  creepy.
- **Manipulation risk:** personalised AI messages can be up to 6× more persuasive
  than human-written ones; recommendations are transparency about the categories
  stored and what counts as sensitive, meaningful consent (not opt-out), and purpose
  limitation via project separation.

**Patterns that make proactive recall feel alive rather than surveillant**

1. **Make the recall visible and attributable** — show the retrieval (Claude's tool
   call), cite the source (Claude, Granola, Grok, Mistral), or say "based on your
   chat about X on <date>". The CHI findings say visibility itself is the fix.
2. **Let the user set the "bring up unprompted" boundary per topic** — ChatGPT's
   topic controls; Claude's "tell Claude what to focus on or ignore"; Meta AI only
   remembers what you choose to share.
3. **Propose, don't impose, long-term facts** — Bee suggests Facts for acceptance;
   Hermes stages writes for approval; Claude Code writes only user / feedback /
   project / reference notes and skips derivable facts; Mem0's ADD / UPDATE / DELETE /
   NOOP gate keeps the store from bloating with trivia.
4. **Keep recall inside the context it was learned in** — project-scoped memory;
   Gemini's per-source connections. Cross-context recall (a health fact surfacing in
   a work chat) is the canonical creepy case.
5. **Prefer contextual triggers with a calibrated threshold over LLM whim** — a
   ~220 MiB temporal-graph model gives a per-event trigger probability that beats
   LLM "should I bring this up?" by +16.7 F1 at 12–83× the speed (2605.30152);
   T-Mem's write-time triggers make relevant memories findable without broad profile
   injection; PERMA (2603.23231) shows preferences drift, so supersession and
   freshness rules are what stop stale preferences surfacing confidently.
6. **Show freshness and let facts expire** — timestamps on memories (ChatGPT rows,
   Claude Code `modified`), invalidated-not-deleted facts (Zep), decay (Supermemory),
   auto-delete windows (Limitless 30 days, Gemini 72 h).
7. **Offer an always-available off-ramp** — ephemeral mode, pause vs reset,
   per-memory delete from the citation itself (Claude), revoke per app (OpenMemory).
8. **Signal the ambient state** — Bee's recording light, Limitless' consent chime,
   Recall's opt-in and exclusions. Ambient-capture products that skipped this
   (Rewind, early Recall) drew the strongest backlash.

**Products that got the "alive" feeling right (per reviews):** Dot's unprompted
follow-ups tied to things you told it (a trip, a recipe) were widely praised as
feeling like a friend — but it worked because Dot only used what you had told *it*,
in a single companion context. Rosebud's weekly reflections and Bee's daily recap
feel alive because they are **periodic, expected rituals** rather than surprise
interjections.

---

## Sources

**Papers** (arXiv ids): MemGPT 2310.08560 · Generative Agents 2304.03442 ·
MemoryBank 2305.10250 · RAPTOR 2401.18059 · HippoRAG 2405.14831 · HippoRAG 2
2502.14802 · LoCoMo 2402.17753 · LongMemEval 2410.10813 · Zep 2501.13956 · A-MEM
2502.12110 · Second Me 2503.08102 · Sleep-time Compute 2504.13171 · Mem0
2504.19413 · MemoryOS 2506.06326 · MemOS 2507.03724 · MIRIX 2507.07957 · Hindsight
2512.12818 · surveys 2404.13501, 2505.00675, 2512.13564, 2602.19320, 2606.30306 ·
Memory-as-Asset 2603.14212 · MemConflict 2605.20926 · freshness recipe 2606.01435 ·
MemStrata 2606.26511 · Eywa 2605.30771 · MemIR 2605.25869 · MemMachine 2604.04853 ·
T-Mem 2606.15405 · proactive triggers 2605.30152 · CIMemories 2511.14937 · PERMA
2603.23231 · personalised LTI 2510.07925 · CI privacy norms 2508.06760 · RAG-memory
privacy perceptions 2508.07664 · "Relational Gains, Privacy Strains" CHI 2026
(doi 10.1145/3772318.3791635) · usable privacy-respecting LTM, CHI EA 2026
(doi 10.1145/3772363.3799198).

**Products and essays:** letta.com/blog/sleep-time-compute ·
docs.letta.com/guides/agents/memory-blocks · mem0.ai/blog/state-of-ai-agent-memory-2026 ·
mem0 OpenMemory blog · support.claude.com/en/articles/11817273 · claude.com/blog/memory ·
code.claude.com/docs/en/memory · simonwillison.net/2025/Sep/12/claude-memory ·
embracethered.com (ChatGPT memory internals, 2025-05) · ai-toolbox.co ChatGPT memory
guide 2026 · buildthisnow.com ChatGPT Dreaming (third-party) ·
blog.google Gemini temporary chats · support.google.com/gemini/answer/16598469 ·
datacamp.com Gemini Personal Intelligence · learn.microsoft.com
copilot-personalization-memory · neowin.net Meta AI WhatsApp memory ·
support.microsoft.com Windows Recall · screenpi.pe on Rewind · help.limitless.ai
Pendant FAQ · samjulien.com and TechCrunch (2026-05-24) on Bee · granola.ai
meeting-recall · rosebud.app · fastcompany.com on Dot · producthunt.com Mem 2.0 ·
crm.org Attio review · shapeof.ai/patterns/memory · aiuxplayground.com memory-manage
pattern · smashingmagazine.com AI transparency patterns (2026-05) ·
techpolicy.press "What we risk when AI systems remember" · cmswire.com
personalisation vs surveillance · supermemory.ai temporal knowledge graphs ·
hermes-agent.nousresearch.com docs (memory, desktop) · blog.character.ai/memory
(2026-05-21) · hidekazu-konishi.com AI agent memory design guide (2026-08).

Caveats: OpenAI's own pages blocked direct fetches, so ChatGPT "Dreaming" details
are from third-party reporting; two ACM full texts were paywalled, so the CHI EA
findings come from abstracts; the Limitless in-app layout is described from reviews.
