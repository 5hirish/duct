"""Memory retrieval evaluation — a fixed corpus, 50 questions, five axes.

The LongMemEval (2410.10813) axes, adapted to what Duct's memory actually has
to answer, and scored without a model in the loop:

* **extraction** — one fact, stated once, has to come back.
* **multi-session** — the answer needs entries written on different days.
* **temporal** — the question carries a date range ("last month", "in the last
  7 days", "between X and Y"); the right window has to be read out of it.
* **knowledge update** — the fact changed. The current value must come back and
  the superseded one must not, which is the **stale-fact rate**: vanilla RAG
  serves superseded facts 15-40% of the time (MemStrata 2606.26511), and a
  bi-temporal ledger with deterministic supersession should be at ~0%.
* **abstention** — nothing in memory answers this. Returning something anyway is
  the failure; benchmarks now test this explicitly.

Deliberately judge-free, unlike tests/eval/ for reports: retrieval either
returns the right rows or it does not, so scoring is exact and the whole set
runs in CI in under a second. That also makes it a regression test for the
Phase 3 ranking and time-expansion code, not just a benchmark.

Dates are relative to now, so the corpus stays valid whenever it runs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from uuid import UUID

from service.memory import remember, search
from utils.dates import utcnow

# --- axes -------------------------------------------------------------------

EXTRACTION = "extraction"
MULTI_SESSION = "multi-session"
TEMPORAL = "temporal"
KNOWLEDGE_UPDATE = "knowledge-update"
ABSTENTION = "abstention"


@dataclass(frozen=True)
class Entry:
    """One corpus row. ``days_ago`` anchors it relative to the run."""

    slug: str
    kind: str
    title: str
    days_ago: int
    entity_key: str = ""
    attribute: str = ""
    period: str = ""
    body: str = ""
    resolved_days_ago: int | None = None  # incidents that have since closed


@dataclass(frozen=True)
class Question:
    """One graded question. ``expect`` and ``reject`` are corpus slugs."""

    axis: str
    question: str
    expect: tuple[str, ...] = ()
    reject: tuple[str, ...] = ()


# --- the corpus -------------------------------------------------------------
# A plausible six months of one account: a target that moved, an incident that
# opened and closed, decisions with reasons, dated metrics, open watches.

CORPUS: tuple[Entry, ...] = (
    # A goal that changed — the knowledge-update spine of the set.
    Entry("cpa_target_old", "goal", "Target CPA $60", 200, "kpi:cpa", "target"),
    Entry("cpa_target_new", "goal", "Target CPA $45", 60, "kpi:cpa", "target",
          body="Lowered after the Q1 margin review."),
    # A site status that changed.
    Entry("score_old", "status", "SEO health score 62", 120, "site:acme.com", "score"),
    Entry("score_new", "status", "SEO health score 78", 10, "site:acme.com", "score"),
    # An indexation state that changed.
    Entry("pricing_indexed", "status", "/pricing is indexed", 90, "page:/pricing", "indexation"),
    Entry("pricing_redirected", "status", "/pricing 301s to /plans, no longer indexed", 47,
          "page:/pricing", "indexation"),
    # Decisions, with their reasons.
    Entry("redirect_decision", "decision",
          "Redirected /pricing to /plans to consolidate duplicate content", 47,
          body="Two pages competed for the same query set; /plans had the stronger backlinks."),
    Entry("match_type_decision", "decision",
          "Moved the Brand campaign to exact match only", 90,
          body="Broad match was buying competitor navigational traffic at 3x the CPA."),
    Entry("no_index_decision", "decision",
          "Decided not to noindex the blog tag pages", 130,
          body="They carry internal links the crawler depends on."),
    # An incident that opened and closed.
    Entry("clicks_incident", "incident",
          "Organic clicks down 23% week over week after the /pricing redirect", 45,
          "page:/plans", "clicks", resolved_days_ago=30,
          body="Recovered once /plans picked up the redirected authority."),
    # An incident still open.
    Entry("checkout_incident", "incident",
          "Checkout returns 500 on mobile Safari", 12, "page:/checkout", "errors"),
    # Watches.
    Entry("indexation_watch", "watch",
          "Watch /plans indexation weekly until it holds for a month", 40,
          "page:/plans", "indexation"),
    Entry("competitor_watch", "watch",
          "Watch competitor pricing page for a free tier launch", 20,
          "competitor:databox", "pricing"),
    # Dated metrics — distinct periods, so they coexist rather than supersede.
    Entry("cpa_q1", "metric", "Brand CPA $71, up 38% on the prior period", 150,
          "kpi:cpa", "actual", period="2026-Q1"),
    Entry("cpa_q2", "metric", "Brand CPA $52, down 27% on Q1", 75,
          "kpi:cpa", "actual", period="2026-Q2"),
    Entry("clicks_28d", "metric", "Organic clicks 12,400 over the last 28 days", 5,
          "kpi:organic_clicks", "actual", period="last-28d"),
    Entry("ctr_28d", "metric", "Average GSC CTR 3.1% over the last 28 days", 5,
          "kpi:ctr", "actual", period="last-28d"),
    # Actions taken on the account.
    Entry("negatives_action", "action", "14 negative keywords added to the Brand campaign", 8,
          "campaign:brand", "negatives"),
    Entry("sitemap_action", "action", "Sitemap resubmitted to Search Console", 35,
          "site:acme.com", "sitemap"),
    # Conclusions the agent reached.
    Entry("ttfb_conclusion", "conclusion",
          "Slow TTFB on /blog is server-render bound, not a CDN problem", 25,
          body="Cache hit ratio was already 94%; origin response time was the whole delta."),
    Entry("h1_conclusion", "conclusion",
          "Duplicate H1s across 40 blog posts come from the theme template", 70),
    # Milestones and events.
    Entry("first_audit", "milestone", "First SEO audit completed", 120),
    Entry("replatform", "event", "Site replatformed to Next.js", 160),
    # Entities.
    Entry("brand_campaign", "entity", "Brand is the highest-spend campaign", 100,
          "campaign:brand", "role"),
)

BY_SLUG: dict[str, Entry] = {e.slug: e for e in CORPUS}


# --- the questions ----------------------------------------------------------

QUESTIONS: tuple[Question, ...] = (
    # extraction — one stated fact, asked plainly
    Question(EXTRACTION, "why did we move the Brand campaign to exact match", ("match_type_decision",)),
    Question(EXTRACTION, "what is slow about the blog TTFB", ("ttfb_conclusion",)),
    Question(EXTRACTION, "where do the duplicate H1s come from", ("h1_conclusion",)),
    Question(EXTRACTION, "checkout 500 errors", ("checkout_incident",)),
    Question(EXTRACTION, "what did we decide about the blog tag pages", ("no_index_decision",)),
    Question(EXTRACTION, "sitemap resubmitted", ("sitemap_action",)),
    Question(EXTRACTION, "which campaign spends the most", ("brand_campaign",)),
    Question(EXTRACTION, "negative keywords added to Brand", ("negatives_action",)),
    Question(EXTRACTION, "when was the site replatformed", ("replatform",)),
    Question(EXTRACTION, "what are we watching on the competitor pricing page", ("competitor_watch",)),

    # multi-session — the answer spans entries written on different days
    Question(MULTI_SESSION, "what happened with the pricing redirect",
             ("redirect_decision", "clicks_incident")),
    Question(MULTI_SESSION, "everything about /plans indexation",
             ("pricing_redirected", "indexation_watch")),
    Question(MULTI_SESSION, "brand campaign history", ("match_type_decision", "negatives_action")),
    Question(MULTI_SESSION, "what do we know about CPA", ("cpa_target_new", "cpa_q2")),
    Question(MULTI_SESSION, "organic clicks", ("clicks_28d", "clicks_incident")),
    Question(MULTI_SESSION, "what has been done to the site in Search Console",
             ("sitemap_action",)),
    Question(MULTI_SESSION, "open problems on the site", ("checkout_incident",)),
    Question(MULTI_SESSION, "what is the SEO health score", ("score_new",)),
    Question(MULTI_SESSION, "duplicate content decisions", ("redirect_decision",)),
    Question(MULTI_SESSION, "blog issues", ("ttfb_conclusion", "h1_conclusion")),

    # temporal — the range has to be read out of the question
    Question(TEMPORAL, "what did we change in the last 7 days", ("negatives_action",),
             reject=("replatform", "first_audit", "match_type_decision")),
    Question(TEMPORAL, "which metrics landed in the last 7 days", ("clicks_28d", "ctr_28d"),
             reject=("cpa_q1", "cpa_q2")),
    Question(TEMPORAL, "what happened in the last 14 days",
             ("checkout_incident", "score_new"), reject=("replatform", "h1_conclusion")),
    Question(TEMPORAL, "incidents in the last 60 days", ("checkout_incident", "clicks_incident"),
             reject=("replatform",)),
    Question(TEMPORAL, "decisions in the last 100 days",
             ("redirect_decision", "match_type_decision"), reject=("no_index_decision",)),
    Question(TEMPORAL, "what did we conclude in the last 30 days", ("ttfb_conclusion",),
             reject=("h1_conclusion",)),
    Question(TEMPORAL, "actions in the last 45 days", ("negatives_action", "sitemap_action"),
             reject=("first_audit",)),
    Question(TEMPORAL, "the last 20 days", ("checkout_incident", "score_new", "negatives_action"),
             reject=("first_audit", "replatform")),
    Question(TEMPORAL, "what was going on 6 months ago", (), reject=("clicks_28d", "ctr_28d")),
    Question(TEMPORAL, "watches opened in the last 30 days", ("competitor_watch",),
             reject=("indexation_watch",)),

    # knowledge update — the current value wins, the superseded one stays out
    Question(KNOWLEDGE_UPDATE, "what is our CPA target", ("cpa_target_new",),
             reject=("cpa_target_old",)),
    Question(KNOWLEDGE_UPDATE, "what is the current SEO score", ("score_new",),
             reject=("score_old",)),
    Question(KNOWLEDGE_UPDATE, "is /pricing indexed", ("pricing_redirected",),
             reject=("pricing_indexed",)),
    Question(KNOWLEDGE_UPDATE, "target CPA", ("cpa_target_new",), reject=("cpa_target_old",)),
    Question(KNOWLEDGE_UPDATE, "SEO health score", ("score_new",), reject=("score_old",)),
    Question(KNOWLEDGE_UPDATE, "indexation status of the pricing page",
             ("pricing_redirected",), reject=("pricing_indexed",)),
    Question(KNOWLEDGE_UPDATE, "what are we targeting for cost per acquisition",
             ("cpa_target_new",), reject=("cpa_target_old",)),
    Question(KNOWLEDGE_UPDATE, "site score now", ("score_new",), reject=("score_old",)),
    Question(KNOWLEDGE_UPDATE, "does /pricing still resolve", ("pricing_redirected",),
             reject=("pricing_indexed",)),
    Question(KNOWLEDGE_UPDATE, "current goal for CPA", ("cpa_target_new",),
             reject=("cpa_target_old",)),

    # abstention — memory has nothing; returning something is the failure
    Question(ABSTENTION, "what is our TikTok posting cadence"),
    Question(ABSTENTION, "which email provider do we use"),
    Question(ABSTENTION, "who owns the LinkedIn account"),
    Question(ABSTENTION, "what did the podcast sponsorship cost"),
    Question(ABSTENTION, "when does the office lease expire"),
    Question(ABSTENTION, "what is the refund policy"),
    Question(ABSTENTION, "how many warehouse SKUs are active"),
    Question(ABSTENTION, "what is the Shopify theme version"),
    Question(ABSTENTION, "which payroll system are we on"),
    Question(ABSTENTION, "what is the Series A valuation"),
)


def seed_corpus(db, project_id: UUID) -> dict[str, UUID]:
    """Write the corpus and return slug → row id.

    Entries are written oldest first so supersession runs the way it would in
    life: the $60 target is current until the $45 one lands on the same key.
    """
    now = utcnow()
    index: dict[str, UUID] = {}
    for entry in sorted(CORPUS, key=lambda e: -e.days_ago):
        observed = now - timedelta(days=entry.days_ago)
        row = remember(
            db,
            kind=entry.kind,
            title=entry.title,
            body=entry.body,
            project_id=project_id,
            entity_key=entry.entity_key,
            attribute=entry.attribute,
            period=entry.period,
            observed_at=observed,
            valid_to=(
                now - timedelta(days=entry.resolved_days_ago)
                if entry.resolved_days_ago is not None
                else None
            ),
            source_refs=[{"source": "eval"}],
        )
        if row is not None:
            index[entry.slug] = row.id
    return index


@dataclass
class AxisResult:
    axis: str
    asked: int = 0
    recall_hits: int = 0
    recall_wanted: int = 0
    rejected_seen: int = 0
    rejected_wanted: int = 0
    abstained: int = 0
    misses: list[str] = field(default_factory=list)

    @property
    def recall(self) -> float:
        return self.recall_hits / self.recall_wanted if self.recall_wanted else 1.0

    @property
    def leak_rate(self) -> float:
        """Share of entries that should have stayed out but came back.

        On the knowledge-update axis this is the stale-fact rate.
        """
        return self.rejected_seen / self.rejected_wanted if self.rejected_wanted else 0.0


def run_eval(db, project_id: UUID, index: dict[str, UUID], *, k: int = 5) -> dict[str, AxisResult]:
    """Ask every question through the real search path and score the answers."""
    results: dict[str, AxisResult] = {}
    for q in QUESTIONS:
        result = results.setdefault(q.axis, AxisResult(axis=q.axis))
        result.asked += 1
        rows = search(
            db,
            project_id=project_id,
            query=q.question,
            limit=k,
            time_aware=True,
            rank=True,
        )
        got = {row.id for row in rows}

        result.recall_wanted += len(q.expect)
        for slug in q.expect:
            if index.get(slug) in got:
                result.recall_hits += 1
            else:
                result.misses.append(f"{q.question!r} missed {slug}")

        result.rejected_wanted += len(q.reject)
        for slug in q.reject:
            if index.get(slug) in got:
                result.rejected_seen += 1
                result.misses.append(f"{q.question!r} returned {slug}, which is not current")

        if q.axis == ABSTENTION:
            if not rows:
                result.abstained += 1
            else:
                result.misses.append(
                    f"{q.question!r} should have returned nothing, got {len(rows)}"
                )
    return results


def format_report(results: dict[str, AxisResult]) -> str:
    """A one-line-per-axis summary, for a CI log or a run by hand."""
    lines = [f"{'axis':<16} {'asked':>5} {'recall':>7} {'leaked':>7} {'abstain':>8}"]
    for axis, r in results.items():
        abstain = f"{r.abstained}/{r.asked}" if axis == ABSTENTION else "-"
        lines.append(
            f"{axis:<16} {r.asked:>5} {r.recall:>6.0%} {r.leak_rate:>6.0%} {abstain:>8}"
        )
    return "\n".join(lines)
