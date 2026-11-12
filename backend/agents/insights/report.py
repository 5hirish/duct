"""The growth report — the one structured deliverable the insights agent writes.

A brief is prose the person re-reads (``agents/insights/brief.py``). A report
is the Analytics tab: the same agent, the same data tools, but the output is
blocks the app draws — a KPI strip, a time series, a ranked bar chart, a
table, signals and actions — each carrying its own rows. The app renders;
the backend never writes HTML (``backend/AGENTS.md``, "Code design rules").

Why inline rows rather than a ``data_source`` reference: the legacy
``dashboard_spec`` named a source table and the browser looked the rows up
in the brief it had just been handed. A report is stored on its own and
opened a day later, so every block has to carry what it draws. The model
fetched the rows through FetchData, so it quotes them; it never computes a
sum or a rate itself (``agents/insights/totals.py`` did), and the prompt says
so (``prompts/autonomous.REPORT_CONTRACT``).

Nothing here trusts the model to comply. A payload that is not JSON, or JSON
the schema refuses, comes back as problems the runner can hand the model for
one repair turn (``AutonomousInsightsRunner.run_report``); a count over a
limit is clamped, not refused, because losing a report over its thirteenth
block is the one outcome worse than a long report. Framework-free.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from agents.insights.brief import _front_matter
from service.artifact_store import GROWTH_REPORT_JSON, ArtifactVersion
from utils.strings import slugify

logger = logging.getLogger(__name__)

#: ``models.artifact.Artifact.kind`` for a report. Not "report": the app
#: renders that kind through the audit template, and not "brief", which is
#: prose. ``kind`` names what the artifact is.
ARTIFACT_KIND = "growth-report"

#: The ``format:`` a report's front matter declares, beside markdown and html.
REPORT_FORMAT = "report"

# Bounds the app's layout is drawn for. Over them, the extra is dropped with
# a problem noted, never the whole report.
MAX_BLOCKS = 12
MAX_ROWS = 60
MAX_KPIS = 6
MAX_ITEMS = 8

BlockType = Literal[
    "kpi_strip",
    "time_series",
    "bar_chart",
    "pie_chart",
    "table",
    "signal_list",
    "action_list",
]

#: What each block type draws, for the prompt and the app alike.
BLOCK_TYPES: tuple[str, ...] = (
    "kpi_strip", "time_series", "bar_chart", "pie_chart", "table", "signal_list", "action_list",
)


class Kpi(BaseModel):
    """One headline number, already formatted the way the reader should see it."""

    model_config = ConfigDict(extra="ignore")

    label: str
    value: str
    delta: str = ""           # "+12% vs the 30 days before", or empty
    tone: Literal["", "good", "bad", "neutral"] = ""
    source: str = ""          # the source as the reader knows it: "GA4", "Search Console"


class Signal(BaseModel):
    """A finding: what moved, what it costs or earns, and the one action."""

    model_config = ConfigDict(extra="ignore")

    id: str = ""
    kind: Literal["win", "risk", "watch"] = "watch"
    title: str
    impact: str = ""
    action: str = ""
    source: str = ""


class Action(BaseModel):
    """A next step with its size, its effort and how to check it worked."""

    model_config = ConfigDict(extra="ignore")

    id: str = ""
    title: str
    detail: str = ""
    size: str = ""            # "about 920 of 2,434 sessions, 38%"
    effort: str = ""          # "a GA4 setting, no code"
    check: str = ""           # how to tell in two weeks
    owner: str = ""


class ReportBlock(BaseModel):
    """One drawn section. ``rows`` feed a chart or table; ``kpis`` a strip;
    ``signals`` and ``actions`` their lists."""

    model_config = ConfigDict(extra="ignore")

    block_id: str
    block_type: BlockType
    title: str
    source: str = ""          # where the numbers came from, as the reader knows it
    window: str = ""          # "1–30 Oct 2026"
    insight_note: str = ""    # how to read it, ending in the takeaway
    rows: list[dict[str, Any]] = Field(default_factory=list)
    x_field: str = ""
    y_field: str = ""
    group_by: str = ""
    y_unit: str = ""          # "sessions", "clicks", "%", "€"
    kpis: list[Kpi] = Field(default_factory=list)
    signals: list[Signal] = Field(default_factory=list)
    actions: list[Action] = Field(default_factory=list)

    @field_validator("rows")
    @classmethod
    def _rows_are_dicts(cls, rows: list[Any]) -> list[dict[str, Any]]:
        return [r for r in rows if isinstance(r, dict)][:MAX_ROWS]

    @field_validator("kpis")
    @classmethod
    def _clamp_kpis(cls, kpis: list[Kpi]) -> list[Kpi]:
        return kpis[:MAX_KPIS]

    @field_validator("signals", "actions")
    @classmethod
    def _clamp_items(cls, items: list[Any]) -> list[Any]:
        return items[:MAX_ITEMS]


class SourceUsed(BaseModel):
    """One source the run reached for, and what came of it."""

    model_config = ConfigDict(extra="ignore")

    id: str
    label: str = ""
    status: Literal["read", "failed", "skipped", "empty"] = "read"
    window: str = ""
    note: str = ""


class GrowthReport(BaseModel):
    model_config = ConfigDict(extra="ignore")

    title: str
    date_from: str = ""
    date_to: str = ""
    verdict: str                 # the decision, two sentences with their numbers
    summary: str = ""
    takeaway: str = ""
    sources: list[SourceUsed] = Field(default_factory=list)
    blocks: list[ReportBlock] = Field(default_factory=list)
    could_not_check: list[str] = Field(default_factory=list)
    method_note: str = ""

    @field_validator("blocks")
    @classmethod
    def _clamp_blocks(cls, blocks: list[ReportBlock]) -> list[ReportBlock]:
        return blocks[:MAX_BLOCKS]

    @field_validator("could_not_check")
    @classmethod
    def _strings_only(cls, items: list[Any]) -> list[str]:
        return [str(i).strip() for i in items if str(i).strip()][:MAX_ITEMS]


@dataclass(frozen=True)
class ParsedReport:
    """A report the model wrote, or the reasons it could not be read."""

    report: GrowthReport | None
    title: str = ""
    problems: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.report is not None


_FENCE = re.compile(r"\A\s*```(?:json)?\s*\n(.*?)\n\s*```\s*\Z", re.DOTALL)
_TAGS = re.compile(r"</?duct_artifact>")


def _strip_code_fence(body: str) -> str:
    match = _FENCE.match(body)
    return match.group(1) if match else body


def _problem_lines(exc: ValidationError) -> list[str]:
    lines = []
    for err in exc.errors()[:12]:
        where = ".".join(str(p) for p in err.get("loc", ()))
        lines.append(f"{where or 'root'}: {err.get('msg', 'invalid')}")
    return lines


def parse_report(raw: str) -> ParsedReport:
    """Read one ``<duct_artifact>`` payload as a report. Never raises.

    The front-matter fence is optional, as it is for a brief; what follows it
    must be a JSON object, with or without a code fence around it.
    """
    # The runner hands over what sat between the tags; a caller that passes
    # the tags too (a stored transcript, a test) gets the same answer.
    text = _TAGS.sub("", raw or "")
    fields, body = _front_matter(text)
    title = (fields.get("title") or "").strip()
    text = _strip_code_fence(body.strip())
    if not text:
        return ParsedReport(None, title, ["the payload is empty"])
    try:
        data = json.loads(text)
    except ValueError as exc:
        return ParsedReport(None, title, [f"not valid JSON: {exc.msg} at character {exc.pos}"])
    if not isinstance(data, dict):
        return ParsedReport(None, title, ["the payload must be a JSON object"])
    if title and not data.get("title"):
        data["title"] = title
    try:
        report = GrowthReport.model_validate(data)
    except ValidationError as exc:
        return ParsedReport(None, title, _problem_lines(exc))
    return ParsedReport(report, report.title)


# ---------------------------------------------------------------------------
# The artifact version
# ---------------------------------------------------------------------------

def report_source_text(report: GrowthReport) -> str:
    """What the summariser and the finding extractor read: the words, with
    each number beside its claim, never the rows."""
    out = [report.title, f"WINDOW: {report.date_from} to {report.date_to}", "", report.verdict]
    if report.summary:
        out.append(report.summary)
    if report.takeaway:
        out.append(f"Takeaway: {report.takeaway}")
    for block in report.blocks:
        out.append("")
        out.append(f"## {block.title}" + (f" ({block.source}, {block.window})" if block.source else ""))
        for kpi in block.kpis:
            out.append(f"- {kpi.label}: {kpi.value}" + (f" ({kpi.delta})" if kpi.delta else ""))
        for sig in block.signals:
            out.append(f"- [{sig.kind}] {sig.title}. {sig.impact}" + (f" Action: {sig.action}" if sig.action else ""))
        for act in block.actions:
            bits = [act.title, act.detail, act.size, act.effort]
            out.append("- " + " ".join(b for b in bits if b))
        if block.insight_note:
            out.append(block.insight_note)
    if report.could_not_check:
        out.append("")
        out.append("## What could not be checked")
        out.extend(f"- {gap}" for gap in report.could_not_check)
    if report.method_note:
        out.append("")
        out.append(f"Method: {report.method_note}")
    return "\n".join(out)


def report_artifact_version(body: dict) -> ArtifactVersion:
    """ARTIFACT_VERSION adapter for a report — see service/artifact_store.py.

    The runner emits the validated report as ``payload.report`` (a dict), so
    the stream consumers and the store see the same object; it is not
    re-parsed from the raw tag here.
    """
    payload = body.get("payload") or {}
    version = int(body.get("version_id") or 1)
    label = str(body.get("label") or f"Version {version}")
    report = GrowthReport.model_validate(payload.get("report") or {})
    template = str(payload.get("template") or "")
    stem = slugify(f"growth-report-{template}" if template else report.title) or "growth-report"
    return ArtifactVersion(
        content_type=GROWTH_REPORT_JSON,
        title=report.title,
        slug_stem=stem,
        file_stem=stem,
        data=None,
        structured_json=report.model_dump(),
        meta={
            "label": label,
            "template": template,
            "date_from": report.date_from,
            "date_to": report.date_to,
            "sources": [s.model_dump() for s in report.sources],
            "blocks": len(report.blocks),
        },
        source_text=report_source_text(report),
        noun="growth report",
        summary_focus=(
            "the verdict and the headline numbers with their windows, the signals that "
            "moved, the actions it recommends, and what it says could not be checked"
        ),
    )


__all__ = [
    "ARTIFACT_KIND",
    "BLOCK_TYPES",
    "GrowthReport",
    "MAX_BLOCKS",
    "MAX_ROWS",
    "ParsedReport",
    "REPORT_FORMAT",
    "ReportBlock",
    "parse_report",
    "report_artifact_version",
    "report_source_text",
]
