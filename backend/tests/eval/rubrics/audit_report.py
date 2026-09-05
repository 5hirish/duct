"""Rubric + artifact renderer for the SEO Audit agent's report deliverable.

The dimensions below grade the qualities that make an audit *worth paying for*
and that structural validation cannot catch: a report can satisfy
``StructuredAuditData`` completely while being generic, uncalibrated, or
recommending work in the wrong order.

This exists to answer two questions that only a live run can settle
(the engine consolidation review (duct-cloud, private) §6.6):

1. **Which models may we offer?** Customers bring their own key, so a weak model
   produces a bad audit that gets blamed on Duct. Score each candidate model on
   this rubric and admit only those that pass.
2. **Has V1 earned V3's retirement?** Same rubric, both engines, same site.

Grading is deliberately harsh on *evidence*: the single most common failure mode
of a weak model here is a fluent, confident audit whose findings are not tied to
anything actually crawled.
"""

from __future__ import annotations

from typing import Any

from tests.eval.judge import JudgeArtifact
from tests.eval.rubric import Dimension, Marker, Rubric


def audit_report_rubric() -> Rubric:
    """The grading rubric for a finished SEO audit report."""
    return Rubric(
        name="audit_seo_report",
        pass_threshold=3.6,
        persona=(
            "You are the head of growth at the audited company. You have run SEO for a "
            "decade, you have read dozens of agency audits, and you are deeply cynical "
            "about all of them. You are looking for one thing: does this tell me "
            "something specific about MY site that I did not already know, and can my "
            "team act on it on Monday morning? Generic best-practice advice you could "
            "get from any blog post is worthless to you, and confident claims that do "
            "not cite a real page or a real number make you distrust the whole document."
        ),
        dimensions=[
            Dimension(
                "evidence_grounding",
                "Evidence grounding",
                "Findings cite concrete artifacts from the crawl — specific URLs, actual "
                "title/meta text, real status codes, measured counts. A finding that "
                "asserts a problem without pointing at the page or value that "
                "demonstrates it scores 1–2, no matter how plausible it sounds. "
                "Hallucinated pages or invented metrics are an automatic 1.",
                weight=2.0,
                min_score=3,
            ),
            Dimension(
                "specificity",
                "Site specificity",
                "The report could only have been written about THIS site. Advice that "
                "would apply verbatim to any website ('improve your meta descriptions', "
                "'build quality backlinks') scores low even when technically correct.",
                weight=1.5,
                min_score=3,
            ),
            Dimension(
                "score_calibration",
                "Score calibration",
                "Category scores and the overall score track the severity and volume of "
                "the findings underneath them. Scores are on a 0–100 scale. A category "
                "with several critical issues scoring 80/100, or a clean category "
                "scoring 40/100, is miscalibrated. The score band must match the "
                "numeric score.",
                weight=1.0,
                min_score=2,
            ),
            Dimension(
                "prioritisation",
                "Prioritisation quality",
                "Top priorities are ordered by realistic impact-per-effort for this site, "
                "not by category order or severity label alone. A high-effort, low-impact "
                "item above a trivial high-impact fix is a prioritisation failure.",
                weight=1.5,
                min_score=2,
            ),
            Dimension(
                "actionability",
                "Actionability",
                "Each recommendation states what to change, where, and how to tell it "
                "worked. 'Optimise your titles' is not actionable; 'rewrite the 58-char "
                "title on /pricing to lead with the primary term' is.",
                weight=1.5,
                min_score=3,
            ),
            Dimension(
                "coverage",
                "Coverage balance",
                "All nine categories are addressed with genuine analysis rather than "
                "filler. A category padded with a single restated observation to satisfy "
                "the schema scores low.",
                weight=1.0,
                min_score=2,
            ),
            Dimension(
                "narrative",
                "Strategic narrative",
                "The synthesis explains what is holding this site back overall and what "
                "sequence of work fixes it — a coherent argument, not a summary of the "
                "category list.",
                weight=1.0,
                min_score=2,
            ),
        ],
        markers=[
            Marker(
                "cites_real_urls",
                "Findings reference URLs that appear in the crawled page list, rather "
                "than invented or guessed paths.",
                kind="required",
            ),
            Marker(
                "fabricates_metrics",
                "The report states traffic, ranking, or backlink numbers that no crawl "
                "could produce (the audit only has crawl data, not analytics).",
                kind="forbidden",
            ),
            Marker(
                "refers_to_itself_as_ai",
                "The report refers to itself as AI-generated, mentions the model, or "
                "apologises for its limitations.",
                kind="forbidden",
            ),
            Marker(
                "contains_placeholder_text",
                "The report contains placeholder or template artifacts such as 'TODO', "
                "'lorem ipsum', 'example.com', or unfilled brackets.",
                kind="forbidden",
            ),
        ],
    )


def render_audit_artifact(report: Any) -> JudgeArtifact:
    """Render an ``AuditReport`` into the text the judge grades.

    Text-only: an audit has no images, so unlike the content rubric this passes
    no ``JudgeImage``. The rendering is flattened deliberately — the judge should
    grade the substance, not be impressed by JSON structure.
    """
    data = getattr(report, "structured_data", None)
    lines: list[str] = [
        f"URL: {getattr(report, 'url', '')}",
        f"Executive summary: {getattr(report, 'executive_summary', '')}",
    ]

    if data is None:
        lines.append("(no structured data on this report)")
        return JudgeArtifact(title="SEO Audit Report", body="\n".join(lines))

    lines += [
        f"Overall score: {data.overall_score} ({data.score_band})",
        f"Headline: {getattr(data, 'headline', '')}",
        f"Pages crawled: {data.pages_crawled} of {data.total_sitemap_urls} sitemap URLs",
        f"Key signals: {'; '.join(getattr(data, 'key_signals', []) or [])}",
        "",
        "CATEGORIES",
    ]
    for category in getattr(data, "categories", []) or []:
        lines.append(f"\n[{category.id}] {category.label} — {category.score}/100")
        lines.append(f"  {getattr(category, 'tooltip', '')}")
        for finding in getattr(category, "findings", []) or []:
            severity = getattr(finding, "severity", "") or getattr(finding, "status", "")
            lines.append(f"  - ({severity}) {getattr(finding, 'title', '')}")
            if detail := getattr(finding, "description", ""):
                lines.append(f"      {detail}")
            for url in (getattr(finding, "affected_urls", None) or [])[:5]:
                lines.append(f"      affected: {getattr(url, 'url', url)}")
            if fix := getattr(finding, "recommendation", ""):
                lines.append(f"      fix: {fix}")

    if priorities := getattr(data, "top_priorities", None):
        lines.append("\nTOP PRIORITIES")
        for i, priority in enumerate(priorities, 1):
            lines.append(f"  {i}. {getattr(priority, 'title', priority)}")
            if rationale := getattr(priority, "rationale", ""):
                lines.append(f"     why: {rationale}")

    if wins := getattr(data, "wins", None):
        lines.append("\nWINS\n  " + "\n  ".join(str(w) for w in wins))

    if roadmap := getattr(data, "roadmap", None):
        lines.append("\nROADMAP")
        for phase in roadmap:
            lines.append(f"  - {getattr(phase, 'label', phase)}")

    if narrative := getattr(data, "strategic_narrative", ""):
        lines.append(f"\nSTRATEGIC NARRATIVE\n{narrative}")

    return JudgeArtifact(title="SEO Audit Report", body="\n".join(lines))
