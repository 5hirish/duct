# The Engine Is Not The Model

**Author:** Shirish Kadam · **Date:** 2026-09-01

Duct asks which harness to run, then picks the model itself — from an environment variable, once, for every job on the machine.

Now that models come from four providers and two of them can arrive as the customer's own key, one global `GENERATE_MODEL` is the wrong shape. This is the UX for it: **three tiers the user fills in, a job-to-tier assignment Duct owns, and a fallback ladder that runs down the tiers the user authored.**

**Status** P1+P2 built · **Surfaces** /settings/models · composer · account menu · **Shape** 3 tiers + modality rows

## 01 · What the user can actually set today

Two controls exist, and neither of them is a model.

The **Engine dialog** (`app/src/components/EngineDialog.jsx`, reached from the account menu) writes one string — `duct_engine` — to `localStorage`. It picks a *harness*: v1 (LangChain) or v3 (Claude Agent SDK). It displays a model name, but that name is decoration: `defaultModel: "Gemini 2.5 Flash"` is a hard-coded label in `app/src/lib/engines.js`, not a setting.

The **provider key cards** on Connections (`ProviderCard.jsx` over `lib/providerKeys.js`) let a customer paste an Anthropic, OpenAI or Gemini key. The key is stored in `sessionStorage` — or the OS keychain on desktop — and sent per request as `X-Provider-*`. Pasting a key changes *whose account pays*. It does not change which model runs.

Everything else is an environment variable. `backend/config.py` carries one triple — `generate_engine`, `generate_provider`, `generate_model` — read unchanged at every model-consuming call site in the product:

| Where | What it does | Model it gets |
| --- | --- | --- |
| agents/insights/setup.py:83 | The insights analyst — the pass that writes the brief | the triple |
| agents/insights/subagents/verify.py:76 | The verifier — proves a number before the analyst states it | the parent's |
| agents/insights/v3/runner.py:224 | The synthesizer subagent (`AgentDefinition`) | the parent's |
| routes/audit.py:76 | SEO audit — crawl reading and scoring | the triple |
| routes/content.py:143 | Content Studio — plans, captions, slides | the triple |
| routes/agents.py:1082 | The generic agent session route | the triple |
| service/memory_consolidation.py:230, :478 | Background memory consolidation and recap | the triple |
| routes/chat.py:36 | Follow-up chat | the triple |
| agents/models.py:162 | Slide and post images | `DEFAULT_IMAGE_MODEL` |

**The seams are already cut.** `build_verify_subagent(tools, model=None)` takes a model and its docstring says why — *"allows a cheaper model for the checking pass than for the analysis"*. Nothing has ever passed one. The v3 runner passes `model=model_str` into `AgentDefinition` — the same string it gave the parent. Two call sites are already asking the question this design answers.

## 02 · Three tiers, not nine dropdowns

The user sets **three models**. Duct decides which of the three every internal job deserves. That division is the whole design: the customer knows their budget and their preferred vendor; only Duct knows that the verification subagent is a narrow arithmetic check and the analyst pass is the deliverable's ceiling.

The alternative — one dropdown per job — makes the user learn Duct's internals to spend their money correctly. The tier abstraction moves that knowledge back where it belongs.

The catalogue already thinks in tiers

`agents/models.py` annotates OpenAI's line with exactly three rungs, in OpenAI's own words: `gpt-5.6-sol` — *"flagship — complex professional work"*; `gpt-5.6-terra` — *"balances intelligence and cost"*; `gpt-5.6-luna` — *"cost-sensitive workloads"*. Anthropic ships Opus / Sonnet / Haiku. Google ships Pro / Flash / Flash-Lite. Every provider already sells three rungs. Duct is not inventing a ladder, it is naming the one that exists.

### Naming: not Quick and Balanced

"Intelligent · Balanced · Quick" is the right shape with a name collision at its centre. `agents/thinking.py` already ships a four-rung user-facing dial whose labels are **Quick, Balanced, Deep, Exhaustive**. Two of the three proposed tier names are already taken by a different setting that appears in the same composer.

The collision is not cosmetic. Tier and thinking are orthogonal — *which model* versus *how hard it works* — and you can meaningfully run a Heavy model at Quick thinking or a Light model at Deep. A composer showing "Quick" next to "Quick", meaning two different things, makes an orthogonal pair look like a duplicate.

| Option | Top | Middle | Bottom | Verdict |
| --- | --- | --- | --- | --- |
| Shipped | Heavy | Standard | Light | Chosen Reads as compute weight rather than as a quality verdict, so no rung is an insult. No collision with the thinking dial. |
| As first proposed | Intelligent | Balanced | Quick | Collides Two names already taken by the thinking dial. "Intelligent" also implies the others are not. |
| Considered | Flagship | Standard | Light | Fine Industry vocabulary, already in `models.py`'s own comments — but it names a market position rather than a job. |
| Considered | Frontier | Standard | Light | Fine "Frontier" ages badly — today's frontier is next year's standard. |

Shipped as **Heavy · Standard · Light** — `agents/tiers.py`'s `Tier` enum and `lib/modelTiers.js`'s `TIERS`.

Tier 1

### Heavy

default · gemini-3.1-pro-preview

The pass whose output you will act on. Slow and expensive on purpose.

- Insights analysis — writes the brief
- SEO audit analysis and scoring
Tier 2 · fallback for Heavy

### Standard

default · gemini-3.7-flash

Real reasoning, ordinary cost. Most of what runs.

- Verification subagent
- Content drafting — plans, captions, slides
- Follow-up chat
Tier 3 · fallback for Standard

### Light

default · gemini-3.5-flash-lite

High volume, low judgement. Should be the cheapest thing you own.

- Research reading — crawled pages, connector briefs
- Memory consolidation and recaps
- Session titles

### Why the shipped default is all-Google

The default ships as **Gemini 3.1 Pro → Gemini 3.7 Flash → Gemini 3.5 Flash-Lite**. Three things had to be true for that, and one of them was not, which is why this section is longer than a default deserves.

- **One key must configure all three tiers.** A mixed default leaves a new customer with one key finding two of three tiers broken on arrival. Every triple in `PROVIDER_TRIPLES` is therefore single-provider, and a test asserts it.
- **It must agree with the default engine.** v1 is the default engine and the consolidation target, and `ENGINE_DEFAULT_PROVIDER[V1]` is already Google. Before this change the tier map defaulted to Anthropic while the engine defaulted to Google — two defaults disagreeing about the same install. They now name one provider, and a test pins them together.
- **The rungs must actually differ.** Google's catalogue in `models.py` had no Pro, so Heavy and Standard would both have been `gemini-3.7-flash` — one model typed twice, not a ladder. `gemini-3.1-pro-preview` was added to close that, verified against the live `ListModels` response *and* a real `generateContent` call, because a default naming an id Google does not serve 404s on every fresh install.

**The thing that was not true.** v3's harness is Anthropic-only (`ENGINE_SUPPORTED_PROVIDERS[V3]` is `{anthropic}`) and Content Studio is v3-only, so an all-Google default gives it no tier it can run. The earlier resolver returned *nothing* in that case — a stock install would have shipped one of three agents broken.

The fix is the floor §05 always described and the code had not implemented: when no tier can serve, fall to the *engine's own* default. Content Studio therefore runs on `claude-sonnet-5` and the page says so on every tier row — *"This engine runs Anthropic models only, so standard jobs run on claude-sonnet-5 — this engine's default."* The floor never invents a provider; it uses the engine's declared one, and only when that is reachable.

Two consequences worth recording. `AUTO_POSTURE_MODEL_PREFIXES` listed `"gemini-3-pro"`, which matches nothing Google ships — the 3.x Pro line is `gemini-3.1-pro-preview` — so without adding that prefix every default install would have silently run `auto` projects at `assisted`. And the picker no longer filters models to the current engine: with a Google default on v3 that emptied the list and rendered three blank dropdowns, so it annotates (*"· not on v3"*) instead of hiding.

A one-click **Fill from one provider** control offers the same shape in Anthropic, OpenAI or Google form, because "I have one key and it isn't the default one" is the most common real configuration.

## 03 · Which job sits on which tier

This table is Duct's, not the user's. It ships versioned, it is *shown* on the settings page behind a disclosure, and it is not editable — editing it is what the five-dropdown design was, and the whole point of tiers is to not ask.

| Job | Tier | Call site | Why this tier |
| --- | --- | --- | --- |
| Insights analysis | Heavy | insights/setup.py:83 | Writes the brief. This is the deliverable. |
| Audit analysis & scoring | Heavy | routes/audit.py:76 | Nine weighted categories over a whole site — the judgement *is* the product. |
| Verification | Standard | subagents/verify.py:76 | Re-derives a number from a source. Narrow, checkable, high volume. |
| Synthesis (v3) | Standard | insights/v3/runner.py:224 | Structured JSON from prepared briefs, no tools. |
| Content drafting | Standard | routes/content.py:143 | Voice over reasoning. The tier most people will want to move. |
| Follow-up chat | Standard | routes/chat.py:36 | Conversational, context already assembled. |
| Research reading | Light | crawl · connector briefs | Enormous context, little judgement. The classic cheap-long-context job. |
| Memory consolidation | Light | memory_consolidation.py:230, :478 | Background, constant, invisible. Fails soft today and should stay cheap. |
| Recaps & titles | Light | chat summaries | Cosmetic strings. |

The disclosure that renders this on the settings page is labelled *"What runs on each tier"* and is collapsed by default. It exists so that a user who moves Light to a very cheap model can see they just changed how their crawled pages get read — not so they can argue with the assignment.

## 04 · The screen

A new page at `/settings/models`. The account menu's *Engine* item becomes **Models & engine** and links here; the Engine dialog is retired. The three provider key cards move off Connections, which goes back to being about data sources only.

Settings › Models & engine

##### Tiers

Three models. Duct picks the right one for each job — and falls down the list when one is unavailable.

HeavyThe analysis you act onClaude Opus 5 Your keyStandardMost of what runs · fallback for HeavyClaude Sonnet 5 Your keyLightHigh volume, low judgement · fallback for StandardGPT-5.6 Luna Needs an OpenAI key Add keyLight jobs run on **Claude Sonnet 5** (Standard) until you add one.▸ What runs on each tierFill from one provider

##### Modality

Only shown for what your tier models cannot produce themselves.

ImagesSlide and post images · Content StudioAuto · Gemini 3.1 Flash Image ReadyNone of your tier models generate images, so Duct uses a dedicated one.VideoShort-form video · Content StudioNot connected Connect HiggsfieldVideo generation is a connected service, not a model you pick here.

##### Providers

Your keys. Stored in this browser session — in the OS keychain on desktop — and sent with each request. Never on our servers.

Anthropic Your key
Google Duct's key
OpenAI Not set Add
OpenRouter Not set Add

##### Runtime

The harness that runs the agents. Most people never change this — it decides what agents *can do*, not how good they are.

Enginev3 runs Anthropic models only. SEO Audit and Content Studio require it.v1 LangChainv3 Claude SDK

Four deliberate choices:

- **Three rows above the fold.** The entire model configuration is visible without scrolling, which is the difference between a setting people tune and a setting people avoid.
- **Each tier states its own fallback role.** *"fallback for Heavy"* on the Standard row means the ladder is learned by reading the page, not by reading docs.
- **Modality rows are conditional and mostly say "Auto".** A user should never be asked to choose an image model they have never heard of.
- **Engine is demoted to *Runtime*, at the bottom.** It is a capability switch, not a quality dial, and putting it first is what taught users to look for models in the wrong place.

Rows autosave with an undo toast. No Apply button: a modal has to commit or discard, a page does not. The map is read per request, so a change takes effect on the next run and never mid-run.

## 05 · Falling down the ladder

Heavy → Standard → Light, and never upward. This is the mechanic that makes three tiers better than three unrelated dropdowns: **the user authors their own degradation path once, and every job inherits it.**

It has to be reconciled with the fallback Duct already has, because the two are different in kind and the existing one has a documented rule the new one appears to break.

### Three levels, not one

Heavy **gemini-3.1-pro-preview** → 529 → within-tier **gemini-3.7-flash** → 529 → Standard tier **gemini-3.7-flash** → Light tier **gemini-3.5-flash-lite** → engine default **gemini-2.5-flash**

- **Within a tier** — the existing `resolve_fallback_models`: same provider, one step, v1 only. It handles a transient overload without changing whose key pays or which vendor answers. Unchanged by this design.
- **Across tiers** — the new ladder. Fires when a tier is *unreachable* (no credential for its provider), *unsupported* by the engine, or has exhausted its within-tier step.
- **Below the tiers** — the engine's own default, which is today's behaviour and the floor everything else stands on. It exists because the shipped default is Google and v3's harness is Anthropic-only: without it Content Studio would have no model at all on a stock install. It never invents a provider — it takes the engine's declared default, and only when that provider is reachable. If it is not, the run fails at the door rather than halfway through a brief.

**Why the cross-provider hop is allowed here and not there.** `MODEL_FALLBACK`'s docstring rules out cross-provider fallback on two grounds: no credential, and *"reaching for Duct's own key would move a customer's spend onto our account without asking."* The tier ladder answers the second directly — *the user chose these three models and this order*, so the hop is asked for rather than assumed. The first ground is physical and survives: a tier whose provider has no reachable key is **skipped**, never attempted.

### The rules

- **Downward only.** Light never escalates to Heavy. This mirrors `effective_autonomy`, where "a model can only ever *lower* the posture, never raise it" — and for the same reason: a silent upgrade is a cost surprise, and cost surprises are how a settings page loses trust.
- **Skip, don't fail.** An unreachable tier is stepped over. Only when *every* tier is unreachable does the run refuse to start — which is today's behaviour in `resolve_model`, *"a run that cannot reach a model should fail at the door rather than halfway through a brief."*
- **Whose key pays is never silently changed.** Each tier row shows its credential source — Your key / Duct's key / Not set. A ladder step that moves a run from the customer's key onto Duct's is visible on the page before it ever happens.
- **A step is reported, not buried.** The run record names the tier that actually served it. A brief written by Light when the user configured Heavy is a materially different deliverable and has to say so.
- **Configuration gaps and runtime errors take the same path.** One ladder, two triggers. The settings page previews the config case in words — *"Light jobs run on Claude Sonnet 5 until you add one"* — which is the same computation the runtime does.

One thing to decide before P2

Whether a Heavy failure should descend for the *whole run* or per call. Per call is more faithful and can produce a brief whose analysis is Heavy and whose verification silently ran two tiers down. Per run is coarser and easier to report honestly. This design assumes **per call, reported per run** — the run record lists every tier that served it — but it is a real fork and the cheaper answer is per run.

## 06 · Modality, and what "multimodal" has to mean

The rule asked for is: a modality row appears *unless the tier model can already do it*. That is right, and it depends entirely on a distinction the catalogue does not currently make.

Not the question

### Multimodal input

Reading an image. Nearly every frontier chat model does this — Claude, GPT and Gemini all accept image input, which is how the file-upload capability already works.

If "multimodal" meant this, the Images row would never appear, and the product would have no way to generate a slide.

The question

### Multimodal output

Emitting an image or a video. Almost no chat model does this. In Duct's current catalogue, **none** do: image generation lives in a disjoint `ImageModel` enum (`gemini-3.1-flash-image` and friends) reached through a different SDK call path.

So the "unless" clause is forward-looking, and needs a capability table to become checkable.

### The capability table

A new `MODEL_MODALITY` in `agents/models.py`, built exactly like `MODEL_THINKING` — keyed by `ModelName` so a catalogue rename breaks the import rather than silently stopping matching, and paired with a test so a new model cannot ship without someone deciding what it can emit.

```
class Modality(StrEnum):
    TEXT  = "text"
    IMAGE = "image"
    VIDEO = "video"

# What each model can EMIT. Input modality is not modelled: every catalogue
# chat model accepts images, so it would be a column of True.
MODEL_EMITS: dict[str, frozenset[Modality]] = { ... }
```

With that table the Images row resolves itself:

1. Does any configured tier model emit `IMAGE`? Use the highest one that does; the row reads *"Handled by your Standard model"* and offers no dropdown.
2. Otherwise fall to the dedicated modality model. The row reads *"Auto · Gemini 3.1 Flash Image"* with an expandable override.

Today branch 1 is unreachable and branch 2 always wins. That is the correct thing to build anyway: it is three lines of resolution, and it means the day a tier model gains image output the row changes by itself rather than needing a UI change.

### Video is a connector, not a model

Worth stating because it breaks the pattern deliberately. There is **no video model in the backend at all** — no enum, no call path. The planned route is the Higgsfield hosted MCP over bearer auth, which is a *connected service*: it has an account, a subscription and an OAuth-shaped setup, not a model id in a dropdown.

So the Video row renders as a connection state — *"Not connected · Connect Higgsfield"* — and links to Connections. It appears on this page because this is where a user goes to ask "what makes my media", and answering "nowhere, here's how" is better than the row not existing. It ships with the video feature, not before.

The same shape covers whatever comes next — audio, speech — without a new concept: **a modality is either something a tier model emits, a dedicated model Duct picks, or a service you connect.**

## 07 · Flagging what cannot run

Four states. The rule: **a warning always names the consequence, and the consequence is always which tier will actually serve the job instead.**

| State | Trigger | What the row says | Save |
| --- | --- | --- | --- |
| Ready | Provider reachable, engine supports it | The credential source, named exactly — see below | — |
| Needs a key | No BYO key and no server key for that provider | "Light jobs run on **Claude Sonnet 5** (Standard) until you add one." + inline *Add key* | Saves |
| Not on this engine | Provider ∉ `ENGINE_SUPPORTED_PROVIDERS[engine]` | "v3 runs Anthropic models only. On v3 this tier falls to **Claude Sonnet 5**." + *Switch to v1* | Saves |
| Lowers autonomy | Heavy model outside `AUTO_POSTURE_MODEL_PREFIXES` on an `auto` project | "This project runs at **auto**. On this model it will run at **assisted** — it asks more often." | Saves |

Saving is never blocked. Someone configuring a fresh install picks the models they want and *then* goes and gets the keys; a form that refuses the first half until the second is done makes the setup order the developer's, not the user's.

**The fallback claim has to be true.** "Runs on Claude Sonnet 5 (Standard)" must be computed by the same code that will actually pick it — the tier ladder plus `resolve_engine_model` — not by a UI guess. That is why provider status is a server endpoint rather than a client-side check against which keys the browser happens to hold.

### Naming the credential, precisely

The chip on a ready row answers one question — *who is paying for this run* — and it has to answer it exactly. "Duct's key" was the first attempt and it covered two opposite situations: a key in the operator's own `.env` on a laptop or self-hosted box, and Duct's hosted key on the deployment we run. Same config field, and the customer cares enormously which one it is.

| `source` | Chip | Means |
| --- | --- | --- |
| user | Your key | An `X-Provider-*` header this request supplied. |
| env | From env | This instance's own environment — desktop, self-hosted, or local dev. |
| cloud | Duct cloud | Our hosted key. Our account is paying. |
| subscription | Your subscription | The operator's Claude subscription on this machine. |
| none | Not set | Unreachable. |

Five values, one definition, and a test that pins them. The reason for the test is that there *were* two definitions for a while: the provider tiles kept a private copy of the mapping, and when `server` split into `env` and `cloud` every tile silently fell through to "No key set" while the tier rows two tabs away correctly read "From env". The tiles now import the same table the tier rows use.

### The autonomy state is the one nobody expects

`service/execution/policy.py` already downgrades a project: *"a model outside `AUTO_POSTURE_MODELS` runs an `auto` project at `assisted`."* Today that is invisible. The moment users can point Heavy at a cheap model — and the moment a ladder step can do it for them — that mismatch goes from rare to routine. Surfacing it is the difference between a setting and a trap.

The copy constraint from the policy docstring holds: this is a *posture* change, not a permissions change. Say "it asks more often", never "it is less safe" — `AUTO_APPLY_ALLOWLIST` and the destructive gate are byte-identical at both levels.

## 08 · Per-run override, and the one advanced escape hatch

### The composer

Settings are the steady state. The composer needs the other thing — *"this one matters, use the good model"* — and with tiers it becomes a three-way pick rather than a model list:

ComposerDeep
Heavy · this run

Run

Runs every job one tier up for this run. Thinking stays at **Deep**.

Tiers make this cleaner than the per-job design allowed. "Run this at Heavy" is a single, comprehensible instruction — it lifts the whole run, not one hidden sub-step — and it sits beside the thinking dial as the second of two orthogonal decisions: **which model, and how hard it works.** The two dials having disjoint vocabularies is what makes that pair readable, which is §02's naming argument arriving in the place it matters.

It does not persist, and it appears on the run record. A sticky override that outlives its reason is how people pay Heavy prices for a month and blame the product.

### Per-agent tier overrides

One collapsed *Advanced* list, for the single sentence tiers cannot say: *"audits deserve Heavy, everything else Standard."* Rows pick a **tier**, not a model — `SEO Audit · analysis → Heavy` — so the override inherits every ladder and modality rule instead of forking them.

Deliberately a list you add to, not a matrix. It is also the most droppable thing in this document: if P2 ships and nobody asks for it, that is the answer.

## 09 · The contract behind the screen

The layering follows the split the codebase already keeps: `models.py` owns what a model *is*, `engines.py` owns which engine *may use* it — so the new module owns which tier *gets* it, and reads the other two rather than duplicating them.

#### backend/agents/tiers.py — new

```
class Tier(StrEnum):
    HEAVY = "heavy"
    STANDARD = "standard"
    LIGHT    = "light"

# Descending. The ladder is this tuple; there is no other ordering anywhere.
TIER_ORDER: tuple[Tier, ...] = (Tier.HEAVY, Tier.STANDARD, Tier.LIGHT)

# Duct's assignment — §03. Versioned, shown in the UI, not user-editable.
JOB_TIER: dict[Job, Tier] = { ... }

def resolve_tier_model(
    job: Job,
    engine: Engine,
    *,
    tier_map: dict | None = None,
    reachable: frozenset[Provider],
) -> TierResolution:
    """The model for this job, the tier it came from, and every tier skipped.

    Walks TIER_ORDER from JOB_TIER[job] downward, skipping tiers whose
    provider is not in `reachable` or not supported by `engine`. Returns the
    skips so the caller can log them and the UI can render the same sentence.
    """
```

`reachable` is passed in rather than computed here, for the reason `models.get_api_key_kwargs` already documents: credentials are per-request, and a module that reaches for global config races across concurrent requests carrying different BYO keys.

#### GET /api/providers/status — new

Per-provider reachability. It must be called *with* the request's `X-Provider-*` headers, because the truthful answer is the union of the customer's keys and the server's — and only the server sees both. Returns, per provider: `reachable`, `source` (`"user"` | `"server"` | `"none"`), and the engines that accept it. This is what turns the four row states and every credential chip from a client-side guess into a fact.

#### The request payload

The map rides the path `UserPreferences` already uses — a top-level field on every agent request, stored client-side. Same shape, same lifecycle, no new persistence tier:

```
{ "preferences": { ... },
  "models": {
    "tiers":     { "heavy": "gemini-3.1-pro-preview",
                   "standard": "gemini-3.7-flash",
                   "light":    "gemini-3.5-flash-lite" },
    "modality":  { "image": "gemini-3.1-flash-image" },
    "overrides": { "audit_seo": { "analysis": "heavy" } },
    "run":       { "tier": "heavy" }
  } }
```

Client storage is `duct_model_map` in `localStorage`, beside `duct_engine` and `duct_user_preferences`. Per-user, not per-project. An absent tier means "unset", which resolves to the engine default — so an empty map is byte-for-byte today's behaviour and the migration is a no-op. That is a requirement, not a nicety: `generate_model` is set in production env files.

Validation

Every value is re-resolved server-side through `resolve_engine_model`. A client that sends `claude-opus-5[1m]` to v1, or a model whose provider the engine does not support, gets the engine default — the same treatment a bad `GENERATE_MODEL` gets today. The browser proposes; `engines.py` disposes. Nothing here widens what a request can make the server do.

## 10 · Build order

**Where this stands.** The shipped default is the all-Google triple, with `gemini-3.1-pro-preview` added to the catalogue for the Heavy rung and the engine-default floor implemented under the ladder. P1 and the settings half of P2 are built: `agents/tiers.py`, `GET /api/providers/status`, `GET /api/models/catalogue`, `POST /api/models/preview`, the `/settings/models` page with its three tabs, and `MODEL_EMITS`. The Engine dialog is retired and the provider cards have moved off Connections.

**What is not done, and matters:** no agent run reads the saved map yet. `resolve_tier_model` is exercised by the settings preview and by tests, but `insights/setup.py`, `routes/audit.py`, `routes/content.py` and `routes/agents.py` still resolve their model from `cfg.generate_model`. Until that wiring lands, the page configures a preference the runs ignore — which is the exact failure this design was written to end, so it is the next thing to build and nothing else should jump the queue.

P1 ✓

### Make the truth visible

No new settings. `GET /api/providers/status`, and `/settings/models` rendering today's resolved model read-only, with per-provider credential sources and the key cards moved over from Connections.

- Ships value alone: "which model am I actually on, and whose key is paying" is currently unanswerable from the UI.
- De-risks the hard half — resolution and status — before anything is writable.
P2 ◐

### Three tiers and the ladder

**Built:** `agents/tiers.py`, the three writable rows, *Fill from one provider*, reset, the row states and the server-resolved fallback sentence.

**Remaining:** the `models.tiers` request field, and passing the resolved model at each call site — starting with the two seams that already accept one, `build_verify_subagent(model=…)` and the v3 `AgentDefinition`, since they are the cheapest proof the plumbing works.

P3

### Modality and the composer

`MODEL_EMITS`, the self-resolving Images row, and the per-run tier chip. Retire the Engine dialog; the account menu points at the page. The Video row lands with the Higgsfield work, not here.

P4

### Cost, and only then overrides

Observed cost-per-run per tier from the OpenTelemetry GenAI spans already pinned in `agent-ports-and-events.md` — the number that makes the whole page make sense. Estimates before that exist would be fiction. Per-agent tier overrides ship here if anyone has asked by then.

## 11 · What this deliberately does not do

- **No per-job model picking.** §03's table is the implementation, not the interface. Exposing it is the design this one replaced.
- **No per-project maps.** Projects are the sharing boundary for members; a per-project tier map means a collaborator's spend is set by someone else's page, and the precedence line grows a fourth layer. Revisit if per-client cost ceilings are actually asked for.
- **No automatic routing.** "Duct picks the cheapest tier that can do this" is a different product. It needs P4's cost telemetry and an eval harness to prove the cheap tier was good enough. Three tiers first; if nobody changes the default, that is the signal to build routing rather than more dropdowns.
- **No upward fallback, ever.** Named in §05 and worth repeating: the ladder only descends.
- **No model catalogue in the browser.** Dropdown options come from the server, derived from `ModelName` — the same list `thinking.py` keys its table by. A hard-coded JS list is exactly the drift that made `defaultModel: "Gemini 2.5 Flash"` a lie in the current dialog.

**The one-line test for this design.** A user pastes one Anthropic key and never opens this page. Today: one env-var model does every job, and a cheap background recap costs the same as the brief. After P2: Opus writes the analysis, Sonnet verifies and drafts, Haiku reads crawled pages and consolidates memory — from that single key, with a ladder that degrades gracefully when a tier is missing, and a page that says which tier actually served the run.

Design doc · Duct · references `backend/agents/engines.py`, `agents/models.py`, `agents/thinking.py`, `service/execution/policy.py`, `app/src/lib/engines.js`, `app/src/components/EngineDialog.jsx`.
