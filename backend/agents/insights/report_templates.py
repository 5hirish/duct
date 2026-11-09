"""What a growth report is made of, and which of a project's sources can feed it.

A template is a question ("how is growth going", "how is search doing") and
the blocks that answer it, each naming the sources that can fill it. The
person picks the template and the sources on the Analytics tab; the agent
gets the plan as a ``<report_plan>`` block in its user turn
(``prompts/autonomous.report_plan_block``) and decides what to fetch inside
it. A block none of the chosen sources can fill is left out of the plan,
never left for the model to fill with a guess.

Sources are three kinds, because that is how a project reaches them:

* a **connector** with an insights catalog (GA4, Search Console, Google Ads,
  Mixpanel, Clarity, GrowthBook), read through FetchData;
* the project's **schedulers** (PostBridge, Zernio), read through the
  ``social_post_metrics`` entity — one source however many schedulers hold
  accounts, because the person thinks "my posts", not "my scheduler";
* an **MCP server** the person connected (OpenSEO, PostHog), read through
  CallConnectedTool. Only the two presets whose data is growth data and whose
  read-only tools Duct trusts (``service/mcp/presets.trust_read_only``): a
  report runs unattended, so a server whose every call shows the approval
  card could never answer it.

Framework-free; ``routes/content.py`` lists the sources and starts the run.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from agents.insights.catalog.publishers import PUBLISHERS_SOURCE

KIND_CONNECTOR = "connector"
KIND_PUBLISHERS = "publishers"
KIND_MCP = "mcp"

STATUS_READY = "ready"
STATUS_NEEDS_ACCOUNT = "needs_account"
STATUS_NEEDS_ATTENTION = "needs_attention"
STATUS_NOT_CONNECTED = "not_connected"


@dataclass(frozen=True)
class ReportSource:
    """One thing a report can read from, as the picker and the plan name it."""

    id: str
    label: str
    kind: str
    #: One line on what it contributes, for the picker and the plan.
    gives: str


SOURCES: dict[str, ReportSource] = {
    s.id: s
    for s in (
        ReportSource("ga4", "Google Analytics", KIND_CONNECTOR, "sessions, landing pages, conversion paths"),
        ReportSource("gsc", "Search Console", KIND_CONNECTOR, "organic clicks, impressions, queries, pages"),
        ReportSource("google_ads", "Google Ads", KIND_CONNECTOR, "spend, conversions, campaigns"),
        ReportSource("mixpanel", "Mixpanel", KIND_CONNECTOR, "product events, activation"),
        ReportSource("clarity", "Microsoft Clarity", KIND_CONNECTOR, "on-page friction: rage and dead clicks"),
        ReportSource("growthbook", "GrowthBook", KIND_CONNECTOR, "running experiments and their results"),
        ReportSource(PUBLISHERS_SOURCE, "Social posts", KIND_PUBLISHERS, "views, likes, comments and shares per post"),
        ReportSource("openseo", "OpenSEO", KIND_MCP, "rankings, keyword volumes, backlinks, site audits"),
        ReportSource("posthog", "PostHog", KIND_MCP, "product analytics: signups, activation, retention, web vitals"),
    )
}

#: MCP presets a report may read. The ids are ``service/mcp/presets`` ids.
MCP_REPORT_SOURCES: frozenset[str] = frozenset({"openseo", "posthog"})


@dataclass(frozen=True)
class BlockPlan:
    block_id: str
    block_type: str
    title: str
    #: What to put in it, in the words the prompt hands the model.
    asks: str
    #: Sources that can fill it; any one suffices. Empty means any source.
    needs: tuple[str, ...] = ()

    def fillable_by(self, chosen: set[str]) -> bool:
        return not self.needs or bool(chosen & set(self.needs))


@dataclass(frozen=True)
class ReportTemplate:
    id: str
    label: str
    description: str
    #: The question the agent answers; also the memory query for the run.
    question: str
    sources: tuple[str, ...]
    blocks: tuple[BlockPlan, ...]

    def plan_for(self, chosen: set[str]) -> list[BlockPlan]:
        return [b for b in self.blocks if b.fillable_by(chosen)]

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "description": self.description,
            "sources": list(self.sources),
        }


_TRAFFIC = ("ga4", "posthog", "gsc")
_PRODUCT = ("posthog", "mixpanel", "ga4")
_SEARCH = ("gsc", "openseo")

TEMPLATES: dict[str, ReportTemplate] = {
    t.id: t
    for t in (
        ReportTemplate(
            id="growth_overview",
            label="Growth overview",
            description="Search, traffic, posts and signups on one page, with what moved and what to do.",
            question="How is growth going across search, traffic, social posts and signups, and what should change?",
            sources=("gsc", "ga4", "posthog", PUBLISHERS_SOURCE, "openseo", "google_ads", "mixpanel"),
            blocks=(
                BlockPlan("headline", "kpi_strip", "Headline numbers",
                          "Four to six numbers that say how the period went, each against the period before: "
                          "organic clicks, sessions, signups or key events, post views, spend if ads ran."),
                BlockPlan("traffic", "time_series", "Visits over the period",
                          "Sessions (or organic clicks when there is no analytics) by day or week, the window "
                          "and the one before it if the source allows.", _TRAFFIC),
                BlockPlan("channels", "bar_chart", "Where visitors came from",
                          "Sessions by channel or source, ranked, at most ten bars.", ("ga4", "posthog")),
                BlockPlan("queries", "table", "Search: queries and pages that moved",
                          "The queries or pages with the biggest change in clicks, with impressions, CTR and "
                          "position; rankings and volumes from OpenSEO where connected.", _SEARCH),
                BlockPlan("posts", "bar_chart", "Posts by views",
                          "The top posts in the window by views, with the platform; engagement rate in the note.",
                          (PUBLISHERS_SOURCE,)),
                BlockPlan("product", "kpi_strip", "Product",
                          "Signups, activation and retention or the key events the project tracks.", _PRODUCT),
                BlockPlan("signals", "signal_list", "What moved",
                          "Three to six findings ranked by what they are worth, each with its number, "
                          "window and source."),
                BlockPlan("actions", "action_list", "What to do next",
                          "Three to five actions ordered by impact for the effort, each sized and checkable."),
            ),
        ),
        ReportTemplate(
            id="seo",
            label="Search",
            description="Organic clicks, the queries and pages behind them, rankings and what to fix.",
            question="How is organic search doing: which queries and pages gained or lost, and what should be fixed first?",
            sources=("gsc", "openseo", "ga4"),
            blocks=(
                BlockPlan("headline", "kpi_strip", "Organic headline",
                          "Clicks, impressions, CTR and average position against the period before; organic "
                          "sessions where analytics is connected."),
                BlockPlan("clicks", "time_series", "Organic clicks over the period",
                          "Clicks by day or week across the window and the one before it.", ("gsc", "openseo")),
                BlockPlan("queries", "table", "Queries that moved",
                          "Queries with the largest change in clicks; impressions, CTR and position beside them.",
                          _SEARCH),
                BlockPlan("pages", "table", "Pages that moved",
                          "Pages with the largest change in clicks, and the landing pages' engagement where "
                          "analytics has it.", ("gsc", "ga4", "openseo")),
                BlockPlan("rankings", "bar_chart", "Rankings and volumes",
                          "Tracked keywords by position or volume from OpenSEO; skip without it.", ("openseo",)),
                BlockPlan("signals", "signal_list", "What moved",
                          "Cannibalisation, pages losing position, queries with high impressions and low CTR."),
                BlockPlan("actions", "action_list", "What to fix first",
                          "Ranked by clicks at stake for the effort."),
            ),
        ),
        ReportTemplate(
            id="social",
            label="Social posts",
            description="How the posts did, by platform and pillar, and what they sent to the site.",
            question="How did the social posts perform in the window, which platform and kind of post earned the most, and did they send anyone to the site?",
            sources=(PUBLISHERS_SOURCE, "ga4", "posthog"),
            blocks=(
                BlockPlan("headline", "kpi_strip", "Posts headline",
                          "Posts published, views, engagement rate and the social sessions they drove.", ()),
                BlockPlan("posts", "bar_chart", "Posts by views",
                          "Top posts by views with the platform; at most ten bars.", (PUBLISHERS_SOURCE,)),
                BlockPlan("platforms", "pie_chart", "Views by platform",
                          "Share of views by platform, from the subtotals.", (PUBLISHERS_SOURCE,)),
                BlockPlan("referrals", "time_series", "Visits from social",
                          "Sessions from social channels by day across the window.", ("ga4", "posthog")),
                BlockPlan("signals", "signal_list", "What worked",
                          "Which posts and platforms earned engagement, and which did not; posting cadence."),
                BlockPlan("actions", "action_list", "What to post next",
                          "Formats and platforms to lean into, with the number that says why."),
            ),
        ),
        ReportTemplate(
            id="product",
            label="Product",
            description="Signups, activation, retention and the friction in between.",
            question="How is the product side of growth doing: signups, activation, retention, and where people get stuck?",
            sources=("posthog", "mixpanel", "ga4", "clarity", "growthbook"),
            blocks=(
                BlockPlan("headline", "kpi_strip", "Product headline",
                          "Signups, activation rate, retention and the key events, against the period before."),
                BlockPlan("funnel", "bar_chart", "Signup funnel",
                          "Visitors to signups to activated, as counts.", _PRODUCT),
                BlockPlan("events", "time_series", "Key events over the period",
                          "The project's key events by day or week.", _PRODUCT),
                BlockPlan("friction", "table", "Where people get stuck",
                          "Pages by rage and dead clicks, or drop-off steps.", ("clarity", "posthog")),
                BlockPlan("experiments", "table", "Experiments",
                          "Running experiments with their exposure and result.", ("growthbook", "posthog")),
                BlockPlan("signals", "signal_list", "What moved",
                          "Three to six findings ranked by what they are worth, each with its number and source."),
                BlockPlan("actions", "action_list", "What to do next",
                          "Three to five actions ordered by impact for the effort, each sized and checkable."),
            ),
        ),
    )
}

DEFAULT_TEMPLATE = "growth_overview"


def template(template_id: str) -> ReportTemplate | None:
    return TEMPLATES.get((template_id or "").strip().lower())


def templates_as_dicts() -> list[dict[str, Any]]:
    return [t.as_dict() for t in TEMPLATES.values()]


# ---------------------------------------------------------------------------
# What this project can actually read
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SourceState:
    source: ReportSource
    status: str
    detail: str = ""

    @property
    def ready(self) -> bool:
        return self.status == STATUS_READY

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.source.id,
            "label": self.source.label,
            "kind": self.source.kind,
            "gives": self.source.gives,
            "status": self.status,
            "detail": self.detail,
        }


def source_states(db, *, user_id: UUID, project) -> list[SourceState]:
    """Every report source and where this project stands on it. Connectors
    come from the project's bindings, the schedulers from the owner's keys,
    MCP servers from the signed-in user's own (never the owner's: a server
    token reads a whole account)."""
    from service.connector_access import STATUS_AVAILABLE, STATUS_BOUND, list_data_sources
    from service.mcp.store import list_servers
    from service.publishers.registry import connected_specs

    out: list[SourceState] = []
    connectors = {
        s.connector_id: s for s in list_data_sources(db, user_id=user_id, project_id=project.id)
    }
    servers = {s["preset"]: s for s in list_servers(db, user_id) if s.get("preset")}
    schedulers = connected_specs(project.user_id, db)

    for source in SOURCES.values():
        if source.kind == KIND_CONNECTOR:
            data = connectors.get(source.id)
            if data is None or data.status not in (STATUS_BOUND, STATUS_AVAILABLE):
                out.append(SourceState(source, STATUS_NOT_CONNECTED))
            elif data.status == STATUS_BOUND:
                out.append(SourceState(source, STATUS_READY, data.account_name or data.account_id))
            else:
                out.append(SourceState(source, STATUS_NEEDS_ACCOUNT, data.account_name or ""))
        elif source.kind == KIND_PUBLISHERS:
            if schedulers:
                out.append(SourceState(source, STATUS_READY, ", ".join(s.label for s in schedulers)))
            else:
                out.append(SourceState(source, STATUS_NOT_CONNECTED))
        else:
            row = servers.get(source.id)
            if row is None:
                out.append(SourceState(source, STATUS_NOT_CONNECTED))
            elif row.get("problem"):
                out.append(SourceState(source, STATUS_NEEDS_ATTENTION, str(row.get("name") or "")))
            else:
                out.append(SourceState(source, STATUS_READY, str(row.get("name") or "")))
    return out


def choose_sources(tmpl: ReportTemplate, states: list[SourceState], wanted: list[str] | None) -> list[SourceState]:
    """The sources a run reads: the ones asked for that are ready and the
    template takes, or every ready compatible source when nothing was asked."""
    ready = [s for s in states if s.ready and s.source.id in tmpl.sources]
    if not wanted:
        return ready
    asked = {w.strip().lower() for w in wanted}
    return [s for s in ready if s.source.id in asked]


__all__ = [
    "DEFAULT_TEMPLATE",
    "KIND_CONNECTOR",
    "KIND_MCP",
    "KIND_PUBLISHERS",
    "MCP_REPORT_SOURCES",
    "SOURCES",
    "STATUS_NEEDS_ACCOUNT",
    "STATUS_NEEDS_ATTENTION",
    "STATUS_NOT_CONNECTED",
    "STATUS_READY",
    "BlockPlan",
    "ReportSource",
    "ReportTemplate",
    "SourceState",
    "TEMPLATES",
    "choose_sources",
    "source_states",
    "template",
    "templates_as_dicts",
]
