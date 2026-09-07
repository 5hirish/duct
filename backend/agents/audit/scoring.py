"""The audit report's numbers, computed from its findings.

The scoring rules the prompt hands the model are arithmetic: a category starts
at 100 and loses a fixed amount per FAIL and per WARN, the overall score is a
weighted mean, the band is a threshold. The model was asked to do that
arithmetic itself and did it loosely — a site whose homepage returned no
response at all was scored 84 "good", and the eval judge marked calibration
down on every run for it. A number the backend can derive is a number the
model should not be asked for, so the rules live here, the prompt's tables are
rendered from these constants, and ``calibrate`` overwrites whatever the model
sent with what its own findings add up to.

Two figures come from the crawl rather than the findings: ``pages_crawled`` and
``total_sitemap_urls``. A model asked for them fabricates ("1 of 0 sitemap
URLs"); the crawl already knows.
"""

from __future__ import annotations

import logging

from agents.audit.schema import (
    AuditCategory,
    CrawlResult,
    ScoreBand,
    Severity,
    StructuredAuditData,
)

logger = logging.getLogger(__name__)

# Share of the overall score each category carries. Order is the report order
# (heaviest first), which is also the order the prompt's table shows.
CATEGORY_WEIGHTS: dict[str, float] = {
    "on_page_seo":           0.25,
    "technical_foundation":  0.20,
    "blog_content_strategy": 0.15,
    "internal_linking":      0.15,
    "eeat_signals":          0.12,
    "geo_aio":               0.07,
    "structured_data":       0.04,
    "open_graph_social":     0.01,
    "off_page_authority":    0.01,
}

# Points a category loses per FAIL and per WARN finding. PASS and OPPORTUNITY
# never cost anything — the prompt's severity rules already say an opportunity
# is "currently harmless".
PENALTIES: dict[str, tuple[int, int]] = {
    "on_page_seo":           (20, 8),
    "technical_foundation":  (20, 8),
    "blog_content_strategy": (15, 6),
    "internal_linking":      (15, 6),
    "eeat_signals":          (12, 5),
    "geo_aio":               (12, 5),
    "structured_data":       (8, 3),
    "open_graph_social":     (8, 3),
    "off_page_authority":    (8, 3),
}
# A category id the model invented gets the middle tier: it still scores from
# its findings, it just carries no weight in the overall.
_UNKNOWN_CATEGORY_PENALTY = (12, 5)

# Lower bound of each band, highest first.
BANDS: tuple[tuple[int, ScoreBand], ...] = (
    (85, ScoreBand.healthy),
    (70, ScoreBand.good),
    (55, ScoreBand.needs_work),
    (0,  ScoreBand.critical),
)

# A model whose own tally lands this far from the computed one is worth a log
# line: it means the findings and the headline number disagreed in what it sent.
_DRIFT_WORTH_LOGGING = 10


def score_category(category: AuditCategory) -> int:
    per_fail, per_warn = PENALTIES.get(category.id, _UNKNOWN_CATEGORY_PENALTY)
    fails = sum(1 for f in category.findings if f.severity == Severity.fail)
    warns = sum(1 for f in category.findings if f.severity == Severity.warn)
    return max(0, 100 - fails * per_fail - warns * per_warn)


def overall_score(categories: list[AuditCategory]) -> int:
    """Weighted mean over the categories present.

    Normalised by the weights actually present, so a report missing a category
    is scored on what it assessed rather than silently treating the gap as 0.
    A report with only unknown ids falls back to a plain mean.
    """
    weighted = [(c.score, CATEGORY_WEIGHTS[c.id]) for c in categories if c.id in CATEGORY_WEIGHTS]
    if weighted:
        total_weight = sum(w for _, w in weighted)
        return round(sum(s * w for s, w in weighted) / total_weight)
    if categories:
        return round(sum(c.score for c in categories) / len(categories))
    return 0


def band_for(score: int) -> ScoreBand:
    for floor, band in BANDS:
        if score >= floor:
            return band
    return ScoreBand.critical


def calibrate(structured: StructuredAuditData, crawl_result: CrawlResult) -> StructuredAuditData:
    """Overwrite every derived number on the report with what its findings imply.

    Mutates and returns ``structured``. Called on every submit path (initial
    build and chat resubmit, both engines), so a report never carries a score
    its findings do not support.
    """
    claimed = structured.overall_score
    for category in structured.categories:
        severities = [f.severity for f in category.findings]
        category.fail_count = severities.count(Severity.fail)
        category.warn_count = severities.count(Severity.warn)
        category.pass_count = severities.count(Severity.pass_)
        category.opp_count = severities.count(Severity.opportunity)
        category.score = score_category(category)

    structured.total_issues = sum(c.fail_count for c in structured.categories)
    structured.total_warnings = sum(c.warn_count for c in structured.categories)
    structured.total_opportunities = sum(c.opp_count for c in structured.categories)
    structured.overall_score = overall_score(structured.categories)
    structured.score_band = band_for(structured.overall_score)

    # A resumed chat runs on a crawl stub with no pages; the figures it carries
    # came from the stored report, so they stand.
    if crawl_result.pages:
        structured.pages_crawled = sum(1 for p in crawl_result.pages if p.http_status > 0)
        structured.total_sitemap_urls = crawl_result.plan.total_sitemap_urls

    if abs(claimed - structured.overall_score) >= _DRIFT_WORTH_LOGGING:
        logger.info(
            "audit scoring: model claimed overall %d, findings add up to %d (%s)",
            claimed, structured.overall_score, structured.score_band.value,
        )
    return structured


def scoring_rules_block() -> str:
    """The weights and penalties as the prompt shows them, from the same constants
    the backend scores with — so the two cannot drift apart."""
    weight_rows = "\n".join(
        f"| {cid:<21} | {round(weight * 100):>3}%   |" for cid, weight in CATEGORY_WEIGHTS.items()
    )
    tiers: dict[tuple[int, int], list[str]] = {}
    for cid, penalty in PENALTIES.items():
        tiers.setdefault(penalty, []).append(cid)
    penalty_rows = "\n".join(
        f"| {', '.join(ids)} | -{per_fail} | -{per_warn} |"
        for (per_fail, per_warn), ids in tiers.items()
    )
    uppers = [100] + [floor - 1 for floor, _ in BANDS[:-1]]
    band_text = " · ".join(
        (f"{floor}–{upper}" if floor else f"<{upper + 1}")
        + f" {band.value.replace('_', ' ').capitalize()}"
        for (floor, band), upper in zip(BANDS, uppers)
    )
    return (
        "## Category weights\n\n"
        "| category              | weight |\n"
        "|-----------------------|--------|\n"
        f"{weight_rows}\n\n"
        "## Per-category scoring\n\n"
        "Each category starts at 100 and loses points per finding:\n\n"
        "| categories | per FAIL | per WARN |\n"
        "|------------|----------|----------|\n"
        f"{penalty_rows}\n\n"
        "Floor at 0. Overall score = weighted average across all 9 categories.\n"
        f"Score bands: {band_text}\n\n"
        "The backend recomputes every category `score`, the four counts, the totals, "
        "`overall_score` and `score_band` from the findings you record, using exactly "
        "these rules. Fill them in with your own tally, but know that a problem you do "
        "not record as a finding does not count against the site."
    )


__all__ = [
    "BANDS",
    "CATEGORY_WEIGHTS",
    "PENALTIES",
    "band_for",
    "calibrate",
    "overall_score",
    "score_category",
    "scoring_rules_block",
]
