# Data model

**Author:** Shirish Kadam, Claude · **Updated:** 2026-09-26

Every table the backend owns, what it records, and which one answers a given
question. The models in [`backend/models/`](../../backend/models/) are the
source of truth for columns; this page is for the step before that, deciding
where something lives. `backend/tests/test_data_model_doc.py` fails when a
table exists that this page does not list.

## Where is it recorded?

Read this before proposing a new table, event kind or log. Four stores already
record what happens, and each has one job. Most "we need to store X" turns out
to be "X is already in one of these, and nothing reads it yet."

| Question | Table | Written by | Shape |
|---|---|---|---|
| What was said, and what did each tool return? | `agent_events` | the conversation recorder, every turn | append-only, one row per turn part, ordered by `seq` |
| Who did what to a project, and when? | `activity_logs` | `service/activity.py::log_activity`, after each domain write | append-only, one row per lifecycle transition, with actor (`user` / `agent` / `auto`) and `conversation_id` |
| What state is a proposed change in right now? | `execution_change_sets` | `service/execution/service.py` | mutable, one row per change set; per-change status and results in `changes` |
| What does the agent know that it cannot re-derive? | `project_memories` | memory tools and consolidation, `service/memory.py` | bi-temporal, typed, sourced; a later value for the same key supersedes the earlier one |

How they relate: `agent_events`, `activity_logs` and `artifacts` are the raw
evidence and stay append-only; `project_memories` is the layer distilled from
them, the only one written to be put in front of a model
([`backend/models/memory.py`](../../backend/models/memory.py), "Layer 1 of
four"). A human decision on a change set (approve, reject, apply, rollback) is
an `activity_logs` row and a status on `execution_change_sets`, never a third
record.

Conversation state the model resumes from (LangGraph checkpoints) is not in
this list: LangGraph creates and migrates its own tables outside Alembic
(`db/migrate.LANGGRAPH_TABLES`, and
[`backend/agents/core/checkpoint.py`](../../backend/agents/core/checkpoint.py)).

## Tables by area

### People and access

| Table | Holds |
|---|---|
| `users` | one row per person (or per desktop install, for a guest); user-scope switches like `memory_paused` |
| `auth_identities` | how a user signs in: Google, guest install, or a linked ChatGPT account (a merge key, never a login alone) |
| `oauth_states` | short-lived OAuth `state` values, single-use, with an expiry |
| `projects` | the unit everything else hangs off: settings, `autonomy_level`, `memory_paused` |
| `project_members` | who can see a project. Authorization is membership, not `projects.user_id` |
| `project_invitations` | pending email invites into a project |
| `user_profile` | who the operator is and how they want to be written to |
| `user_model_settings` | the user's model per tier, and whether a run may step down a tier when out of quota |

### Connectors

| Table | Holds |
|---|---|
| `connector_credentials` | a user's connection to one provider account (OAuth refresh token or key), with `residency` (server or device) |
| `project_connectors` | which credential a project uses, and which entity inside it (GA4 property, GSC site, GTM container) |

### Agents and conversations

| Table | Holds |
|---|---|
| `agent_conversations` | one thread: agent type, project, run status, compaction summary, `seq` allocator, optional link to the artifact it edits |
| `agent_events` | the thread's transcript (see above). `kind` is free text: `user`, `assistant`, `thinking`, `tool_use`, `tool_result`, `question`, `answer`, `context`, `compacted`, `memory_*`, `failure` |
| `activity_logs` | see above. The project's audit trail: change-set transitions, GTM publishes, artifact versions. Not a mirror of tool calls |
| `agent_contexts` | per project and agent, a JSON blob of working notes the agent carries between runs |
| `artifacts` | every version of every output (brief, report, image): `group_id` is the identity, one immutable row per version; bytes in object storage, never a public URL |
| `project_memories` | see above. Scopes `user`, `project`, `artifact` in one table |
| `model_usage` | one row per model call with tokens and cost, so a user can see their own bill |

### Execution

| Table | Holds |
|---|---|
| `execution_change_sets` | see above. Status runs `proposed → approved → applying → applied / partial / failed`, or `rejected`, or `rolled_back` |
| `execution_guardrails` | per-account rules a change may never break; checked at propose and again at apply |

### Content studio

| Table | Holds |
|---|---|
| `content_plans` | a content plan and its strategy |
| `content_posts` | one post: type (slideshow, video), slides, status, performance counts (`perf`: keys per `service/content_metrics.py`; typed-in ones listed in `manual_keys`, which no sync overwrites) |
| `content_assets` | generated images, uploads and references |
| `content_formats` | a project's library of post formats |
| `content_avatars` | a project's library of avatars |
| `content_social_links` | social accounts linked for publishing |

### Growth experiments

| Table | Holds |
|---|---|
| `lead_magnets` | an email captured by a free audit, with its report once the audit finishes |
| `execution_interest` | which done-for-you services a lead asked about |
