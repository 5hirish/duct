"""The audit's numbers are computed from its findings, not taken from the model.

Two live runs scored an unreachable site 84 "good" because the model was asked
for the overall score and the category scores and did the arithmetic loosely.
These pin the rule that fixed it: every derived number on a submitted report
is overwritten with what the scoring rules say its findings add up to, and the
crawl figures come from the crawl.
"""

from __future__ import annotations

from agents.audit.prompts import build_unified_system_prompt
from agents.audit.schema import (
    AuditCategory,
    AuditFinding,
    CrawlPlan,
    CrawlResult,
    PageSignals,
    ScoreBand,
    Severity,
    StructuredAuditData,
)
from agents.audit.scoring import (
    BANDS,
    CATEGORY_WEIGHTS,
    PENALTIES,
    band_for,
    calibrate,
    overall_score,
    score_category,
    scoring_rules_block,
)


def _finding(severity: Severity, n: int = 0) -> AuditFinding:
    return AuditFinding(
        id=f"f-{severity.value}-{n}", severity=severity, title="t", description="d", tooltip="tt"
    )


def _category(cid: str, *severities: Severity, score: int = 50) -> AuditCategory:
    return AuditCategory(
        id=cid, label=cid, score=score, tooltip="",
        # Deliberately wrong counts: the point is that they get recomputed.
        fail_count=9, warn_count=9, pass_count=9, opp_count=9,
        findings=[_finding(s, i) for i, s in enumerate(severities)],
    )


def _report(*categories: AuditCategory, **over) -> StructuredAuditData:
    return StructuredAuditData(
        url="https://getduct.ai", generated_at="now",
        overall_score=over.pop("overall_score", 84), score_band=over.pop("score_band", ScoreBand.good),
        pages_crawled=over.pop("pages_crawled", 1), total_sitemap_urls=over.pop("total_sitemap_urls", 0),
        categories=list(categories), **over,
    )


def _crawl(*statuses: int, sitemap_total: int = 24) -> CrawlResult:
    return CrawlResult(
        plan=CrawlPlan(root_url="https://getduct.ai", total_sitemap_urls=sitemap_total),
        pages=[PageSignals(url=f"https://getduct.ai/p{i}", http_status=s) for i, s in enumerate(statuses)],
    )


# ---------------------------------------------------------------------------
# The rules
# ---------------------------------------------------------------------------

def test_a_category_loses_its_tiers_penalty_per_fail_and_warn_and_floors_at_zero():
    assert score_category(_category("on_page_seo", Severity.fail, Severity.warn)) == 100 - 20 - 8
    assert score_category(_category("structured_data", Severity.fail, Severity.warn)) == 100 - 8 - 3
    # PASS and OPPORTUNITY findings are free.
    assert score_category(_category("geo_aio", Severity.pass_, Severity.opportunity)) == 100
    assert score_category(_category("on_page_seo", *([Severity.fail] * 6))) == 0


def test_the_overall_is_the_weighted_mean_of_the_categories_present():
    categories = [
        _category("on_page_seo", score=40),       # weight .25
        _category("technical_foundation", score=100),  # weight .20
    ]
    for c in categories:
        c.findings = []  # keep the scores we set; overall_score reads c.score as given
    assert overall_score(categories) == round((40 * 0.25 + 100 * 0.20) / 0.45)


def test_bands_follow_the_thresholds_the_prompt_states():
    assert band_for(85) == ScoreBand.healthy
    assert band_for(84) == ScoreBand.good
    assert band_for(70) == ScoreBand.good
    assert band_for(69) == ScoreBand.needs_work
    assert band_for(55) == ScoreBand.needs_work
    assert band_for(54) == ScoreBand.critical
    assert band_for(0) == ScoreBand.critical


def test_the_weights_cover_the_nine_categories_and_sum_to_one():
    assert len(CATEGORY_WEIGHTS) == 9
    assert abs(sum(CATEGORY_WEIGHTS.values()) - 1.0) < 1e-9
    assert set(PENALTIES) == set(CATEGORY_WEIGHTS)
    assert [floor for floor, _ in BANDS] == sorted((floor for floor, _ in BANDS), reverse=True)


# ---------------------------------------------------------------------------
# calibrate — what a submitted report ends up carrying
# ---------------------------------------------------------------------------

def test_calibrate_overwrites_the_models_tally_with_what_its_findings_add_up_to():
    report = _report(
        _category("on_page_seo", Severity.fail, Severity.fail, Severity.warn, Severity.pass_),
        _category("technical_foundation", Severity.warn, Severity.opportunity),
        overall_score=84, score_band=ScoreBand.good, total_issues=0, total_warnings=0,
    )

    calibrate(report, _crawl(200))

    on_page, technical = report.categories
    assert (on_page.fail_count, on_page.warn_count, on_page.pass_count, on_page.opp_count) == (2, 1, 1, 0)
    assert on_page.score == 100 - 40 - 8
    assert technical.score == 100 - 8
    assert (report.total_issues, report.total_warnings, report.total_opportunities) == (2, 2, 1)
    expected = round((52 * 0.25 + 92 * 0.20) / 0.45)
    assert report.overall_score == expected
    assert report.score_band == band_for(expected)


def test_crawl_figures_come_from_the_crawl_and_count_only_pages_that_answered():
    report = _report(_category("on_page_seo"), pages_crawled=1, total_sitemap_urls=0)

    calibrate(report, _crawl(200, 404, 0, sitemap_total=24))

    assert report.pages_crawled == 2, "a 404 is an observation; no response at all is not a crawled page"
    assert report.total_sitemap_urls == 24


def test_a_resumed_chat_on_a_crawl_stub_keeps_the_stored_crawl_figures():
    report = _report(_category("on_page_seo"), pages_crawled=12, total_sitemap_urls=40)

    calibrate(report, CrawlResult(plan=CrawlPlan(root_url="https://getduct.ai")))

    assert (report.pages_crawled, report.total_sitemap_urls) == (12, 40)


def test_a_category_id_the_model_invented_is_scored_but_carries_no_weight():
    report = _report(
        _category("on_page_seo", Severity.fail),
        _category("mobile_experience", Severity.fail, Severity.fail, Severity.fail),
    )

    calibrate(report, _crawl(200))

    invented = report.categories[1]
    assert invented.score == 100 - 3 * 12
    assert report.overall_score == 80, "only on_page_seo has a weight"


# ---------------------------------------------------------------------------
# The prompt shows the same rules the backend applies
# ---------------------------------------------------------------------------

def test_the_prompts_scoring_tables_are_rendered_from_the_constants():
    prompt = build_unified_system_prompt(report_mode="template")
    block = scoring_rules_block()
    assert block in prompt
    for cid, weight in CATEGORY_WEIGHTS.items():
        assert f"| {cid:<21} | {round(weight * 100):>3}%" in block
    assert "| on_page_seo, technical_foundation | -20 | -8 |" in block
    assert "Score bands: 85–100 Healthy · 70–84 Good · 55–69 Needs work · <55 Critical" in block
    assert "recomputes" in block, "the model is told its tally is not the number that ships"
