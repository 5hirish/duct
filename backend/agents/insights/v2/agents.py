"""ADK 2.x dynamic-workflow agent graph for the v2 insight pipeline.

duct_insights_pipeline (dynamic @node, rerun_on_resume=True)
├── ctx.run_node(LlmAgent "data_fetch_agent")  # Phase 1: tool calling → writes supplementary_data
└── ctx.run_node(LlmAgent "synthesis_agent")   # Phase 2: structured JSON → writes synthesis_text

Migrated from ADK 1.x: the two-phase pipeline that was a ``SequentialAgent``
(removed as a top-level export in 2.0) is now an imperative dynamic workflow —
an orchestrator function node that dispatches the two ``LlmAgent`` nodes via
``Context.run_node``. The agents themselves are unchanged: the same instruction
templates with ``{state_key}`` injection and ``output_key`` capture, both of
which still work in 2.x (Google's own v2 ``workflow_agent_seq`` sample uses
them). Keeping that plumbing minimises migration risk; the dynamic-workflow
shape is what unlocks the Phase 2 iterative tool loop / conditional branching.

Both agents are constructed per-request (tools vary by goal) so this module
exposes factory functions rather than module-level singletons.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable

from google.adk.agents.context import Context
from google.adk.agents.llm_agent import LlmAgent
from google.adk.workflow import node

from .schema_compat import _strip_to_json, validate_synthesis
from .state_keys import STATE_SUPPLEMENTARY, STATE_SYNTHESIS_TEXT

# Author name of the synthesis agent — the runner filters streaming ``partial``
# events by this so only synthesis tokens are surfaced as ``synthesis_chunk``.
logger = logging.getLogger(__name__)

SYNTHESIS_AGENT_NAME = "synthesis_agent"

# Repair passes run under a different author so their partials are NOT streamed
# to the client (the first synthesis attempt is the live preview; repairs are
# silent and only correct the final structured result).
SYNTHESIS_REPAIR_AGENT_NAME = "synthesis_repair"

# Max self-correction passes if the synthesis output fails SynthesisSchema
# validation. Each pass feeds the exact Pydantic errors back to the model.
MAX_SYNTHESIS_REPAIRS = 2

# Score a candidate so repair never regresses: lower is better. A valid parse is
# best (0). Otherwise prefer JSON with fewer validation errors over prose, which
# is ranked worst (a repair pass sometimes replies "fixed!" instead of JSON).
_PROSE_SCORE = 10**6


def _synthesis_progress_score(raw_text: str, error_msg: str) -> int:
    try:
        json.loads(_strip_to_json(raw_text))
    except Exception:
        return _PROSE_SCORE
    m = re.match(r"(\d+) validation error", error_msg)
    return int(m.group(1)) if m else 1


def build_data_fetch_agent(
    model_str: str,
    adk_tools: list[Callable],
    mode: str,
) -> LlmAgent:
    """Phase 1: let the LLM decide which supplementary tools to call.

    Instruction templates use {key} syntax resolved from session.state at
    runtime by ADK's inject_session_state mechanism.

    The agent outputs a JSON object mapping tool_name → result dict, captured
    via output_key into session.state["supplementary_data"].
    """
    role_by_mode = {
        "organic_growth": (
            "You are a senior organic growth analyst preparing supplementary "
            "data for an SEO and content insight brief."
        ),
        "paid_ads": (
            "You are a senior paid media analyst preparing supplementary "
            "data for a Google Ads performance brief."
        ),
    }
    role_line = role_by_mode.get(
        mode,
        "You are a data analyst preparing supplementary data for an insight brief.",
    )

    instruction = (
        f"{role_line}\n\n"
        "Goal: {goal}\n"
        "Custom goal context: {custom_goal}\n"
        "Additional context: {context}\n"
        "Customer ID: {customer_id}\n"
        "GA4 Property ID: {ga4_property_id}\n"
        "GSC Site URL: {gsc_site_url}\n"
        "Date range: {date_from} to {date_to}\n"
        "Connected sources: {connected_sources}\n\n"
        "You have access to supplementary data tools. Call only the tools "
        "that materially improve actionability for this specific goal and "
        "context. Do NOT call every available tool — be selective.\n\n"
        "When done, output a JSON object mapping tool_name to result for "
        "every tool you called. Output ONLY valid JSON, no explanation or "
        "markdown fences."
    )

    return LlmAgent(
        name="data_fetch_agent",
        model=model_str,
        instruction=instruction,
        tools=adk_tools,
        output_key=STATE_SUPPLEMENTARY,
        disallow_transfer_to_parent=True,
        disallow_transfer_to_peers=True,
    )


def build_synthesis_agent(
    model_str: str,
    synthesis_system_prompt: str,
) -> LlmAgent:
    """Phase 2: produce a structured JSON SynthesisSchema from all collected data.

    The system prompt (assembled by get_system_prompt()) is embedded directly
    in the instruction. Data blocks are injected from session.state via
    {all_briefs} and {supplementary_data} placeholders.

    No tools — avoids the Gemini-only limitation of output_schema + tools
    and keeps the approach provider-agnostic.

    Output is captured as raw text via output_key; the runner applies
    SynthesisSchema.model_validate_json() after the pipeline completes.
    """
    # The synthesis prompt can contain curly-brace patterns from examples or
    # JSON templates. We embed it as-is — ADK's inject_session_state only
    # replaces {identifier} patterns where identifier is a valid Python
    # identifier, leaving JSON syntax like {"key": val} untouched.
    instruction = (
        f"{synthesis_system_prompt}\n\n"
        "<connector_data>\n"
        "{all_briefs}\n"
        "</connector_data>\n\n"
        "<supplementary_data>\n"
        "{supplementary_data}\n"
        "</supplementary_data>\n\n"
        "<task>\n"
        "Based on all data above, produce your structured analysis. "
        "Output ONLY a valid JSON object matching the SynthesisSchema — "
        "no markdown fences, no preamble, no trailing text.\n"
        "</task>"
    )

    return LlmAgent(
        name=SYNTHESIS_AGENT_NAME,
        model=model_str,
        instruction=instruction,
        output_key=STATE_SYNTHESIS_TEXT,
        disallow_transfer_to_parent=True,
        disallow_transfer_to_peers=True,
    )


def build_synthesis_repair_agent(
    model_str: str,
    bad_json: str,
    validation_errors: str,
) -> LlmAgent:
    """Phase 2b: fix a synthesis output that failed SynthesisSchema validation.

    The previous (invalid) output and the exact Pydantic errors are baked into
    the instruction, so no session-state injection is needed. Runs under
    SYNTHESIS_REPAIR_AGENT_NAME so its tokens are not streamed to the client,
    and overwrites state["synthesis_text"] via the same output_key.

    This is provider-agnostic structured-output enforcement — it works on Gemini
    (where ``output_schema`` is rejected) and on Claude alike.
    """
    instruction = (
        "You previously produced a JSON analysis that FAILED schema validation. "
        "Fix it.\n\n"
        "<your_previous_output>\n"
        f"{bad_json}\n"
        "</your_previous_output>\n\n"
        "<validation_errors>\n"
        f"{validation_errors}\n"
        "</validation_errors>\n\n"
        "<task>\n"
        "Output a corrected JSON object that resolves every validation error "
        "above — add missing required fields, remove fields that are not "
        "permitted, and fix mismatched types — while preserving the original "
        "analysis content. Do NOT explain, apologise, or say the JSON is fixed. "
        "Your entire response must be the corrected JSON object and nothing "
        "else: start with '{', end with '}', no markdown fences, no commentary.\n"
        "</task>"
    )
    return LlmAgent(
        name=SYNTHESIS_REPAIR_AGENT_NAME,
        model=model_str,
        instruction=instruction,
        output_key=STATE_SYNTHESIS_TEXT,
        disallow_transfer_to_parent=True,
        disallow_transfer_to_peers=True,
    )


def build_pipeline_node(
    model_str: str,
    adk_tools: list[Callable],
    mode: str,
    synthesis_system_prompt: str,
):
    """Build the two-phase pipeline as an ADK 2.x dynamic-workflow node.

    Returns an orchestrator node (the ADK 2.x replacement for ``SequentialAgent``)
    that runs Phase 1 then Phase 2 via ``Context.run_node``. The orchestrator
    must set ``rerun_on_resume=True`` because dynamically scheduled child nodes
    can be interrupted, causing the parent to re-run to collect their results.

    Each phase captures its output into session state via the agent's
    ``output_key`` (``supplementary_data`` / ``synthesis_text``); the runner
    reads those back from the session after the run completes.

    Phase 2 is self-correcting: if the synthesis output fails SynthesisSchema
    validation, a bounded ``while`` loop re-runs a silent repair agent with the
    exact validation errors fed back — a dynamic-workflow control-flow pattern
    that static graphs / 1.x SequentialAgent could not express.
    """
    data_fetch_agent = build_data_fetch_agent(model_str, adk_tools, mode)
    synthesis_agent = build_synthesis_agent(model_str, synthesis_system_prompt)

    @node(name="duct_insights_pipeline", rerun_on_resume=True)
    async def pipeline(ctx: Context, _input=None) -> None:
        # Phase 1 — data fetch: LLM selects/calls supplementary tools and
        # writes the tool_name→result JSON to state["supplementary_data"].
        await ctx.run_node(data_fetch_agent)

        # Phase 2 — synthesis: reads {all_briefs} + {supplementary_data} from
        # state and writes the SynthesisSchema JSON to state["synthesis_text"].
        # This attempt streams to the client (live preview). We don't set
        # use_as_output: the runner reads results from session state, and a
        # parent node may hold at most one use_as_output delegate (so it would
        # also collide with the repair pass below).
        await ctx.run_node(synthesis_agent)

        # Phase 2b — self-correction: validate and, if invalid, repair (silent).
        # Track the best candidate so a repair pass that regresses (e.g. replies
        # with prose instead of JSON) can never overwrite a better one. Each pass
        # is fed the *best* output so far plus its exact validation errors.
        best_raw = ctx.state.get(STATE_SYNTHESIS_TEXT, "")
        parsed, errors = validate_synthesis(best_raw)
        best_score = 0 if parsed is not None else _synthesis_progress_score(best_raw, errors)

        attempt = 0
        while parsed is None and attempt < MAX_SYNTHESIS_REPAIRS:
            attempt += 1
            logger.info(
                "v2: synthesis invalid (score=%d), repair attempt %d/%d — %s",
                best_score,
                attempt,
                MAX_SYNTHESIS_REPAIRS,
                errors.splitlines()[0] if errors else "?",
            )
            repair_agent = build_synthesis_repair_agent(
                model_str, bad_json=best_raw, validation_errors=errors
            )
            await ctx.run_node(repair_agent)
            candidate = ctx.state.get(STATE_SYNTHESIS_TEXT, "")
            cand_parsed, cand_errors = validate_synthesis(candidate)
            if cand_parsed is not None:
                best_raw, parsed, errors = candidate, cand_parsed, cand_errors
                break
            cand_score = _synthesis_progress_score(candidate, cand_errors)
            if cand_score < best_score:
                best_raw, errors, best_score = candidate, cand_errors, cand_score

        # Ensure state holds the best candidate for the runner's final parse —
        # the last repair pass may have written a worse one.
        ctx.state[STATE_SYNTHESIS_TEXT] = best_raw
        if attempt:
            logger.info(
                "v2: synthesis %s after %d repair attempt(s)",
                "repaired" if parsed is not None else "still invalid",
                attempt,
            )

    return pipeline
