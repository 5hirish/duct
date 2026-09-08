"""The project drafted from a crawl, in its two layers.

Layer one is deterministic and these pin the heuristics that matter: the site
name comes off ``og:site_name`` or the short segment of the title, empty
values are omitted rather than written as blanks, and social hosts map to the
channel keys the project already uses. Layer two is one structured call, so
the tests pin what happens *around* the model — a value outside the option
list is dropped, never coerced; research competitors ride in; a model that
fails yields no event rather than an empty one.

No network, no model.
"""

from __future__ import annotations

import pytest

from agents.audit.draft import (
    LAYER_CRAWL,
    LAYER_INFERRED,
    PROVENANCE_CRAWL,
    PROVENANCE_INFERRED,
    DraftInference,
    crawl_draft,
    infer_project_draft,
    seed_business_context,
    site_name,
    social_channels,
)
from agents.audit.schema import (
    AuditResearchContext,
    CompetitorSignals,
    CrawlPlan,
    CrawlResult,
    DraftPersona,
    PageSignals,
)
from agents.core.context import BusinessContext

ROOT = "https://acme.example"


def _crawl(**root_fields) -> CrawlResult:
    root = PageSignals(url=ROOT, page_type="landing_page", **root_fields)
    return CrawlResult(plan=CrawlPlan(root_url=ROOT, landing_pages=[ROOT]), pages=[root])


# ---------------------------------------------------------------------------
# Layer 1
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("page", "expected"),
    [
        (PageSignals(url=ROOT, og_site_name="Acme", title="Meal plans | Acme"), "Acme"),
        (PageSignals(url=ROOT, title="Meal plans for busy families | Acme"), "Acme"),
        (PageSignals(url=ROOT, title="Acme – Meal plans for busy families"), "Acme"),
        (PageSignals(url=ROOT, title="Acme"), "Acme"),
        (PageSignals(url=ROOT, title=""), ""),
    ],
)
def test_the_site_name_is_the_short_segment_or_what_the_site_declares(page, expected):
    assert site_name(page) == expected


def test_layer_one_reads_the_root_page_and_omits_what_it_does_not_have():
    draft = crawl_draft(
        _crawl(
            title="Meal plans for busy families | Acme",
            meta_description="Weeknight dinners, planned.",
            favicon=f"{ROOT}/favicon.ico",
            h2s=["Plans", "Pricing", "Recipes"],
            external_links=["https://www.instagram.com/acme", "https://x.com/acme", "https://example.org"],
        )
    )
    assert draft["layer"] == LAYER_CRAWL
    fields = draft["fields"]
    assert fields["name"] == {"value": "Acme", "provenance": PROVENANCE_CRAWL}
    assert fields["company_name"]["value"] == "Acme"
    assert fields["pitch"]["value"] == "Weeknight dinners, planned."
    assert fields["favicon"]["value"].endswith("/favicon.ico")
    assert fields["website_url"]["value"] == ROOT
    assert fields["active_channels"]["value"] == ["instagram", "x"]
    assert all(f["provenance"] == PROVENANCE_CRAWL for f in fields.values())


def test_layer_one_never_writes_a_blank():
    fields = crawl_draft(_crawl(title="", meta_description=""))["fields"]
    assert set(fields) == {"website_url"}, "nothing to say → nothing said, so a merge cannot erase what the user typed"


def test_social_channels_are_deduped_and_www_insensitive():
    crawl = _crawl(external_links=["https://www.linkedin.com/company/acme", "https://linkedin.com/in/x", "https://youtube.com/@acme"])
    assert social_channels(crawl) == ["linkedin", "youtube"]


def test_seeding_fills_only_what_the_user_left_empty():
    crawl = _crawl(title="Acme", meta_description="Weeknight dinners, planned.")
    seeded = seed_business_context(BusinessContext(business_name="What I typed"), crawl)
    assert seeded.business_name == "What I typed"
    assert seeded.business_description == "Weeknight dinners, planned."


# ---------------------------------------------------------------------------
# Layer 2
# ---------------------------------------------------------------------------


class _Structured:
    def __init__(self, answer):
        self.answer = answer

    async def ainvoke(self, _prompt):
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer


class _Llm:
    def __init__(self, answer):
        self.answer = answer
        self.prompt_seen = ""

    def with_structured_output(self, _schema):
        return _Structured(self.answer)


async def test_layer_two_keeps_only_values_the_selects_accept():
    answer = DraftInference(
        industry="SaaS & Software",
        business_model="Subscription boxes",  # not an option → dropped, not "Other"
        brand_voice="Technical",
        personas=[DraftPersona(name="Marketing lead", description="wants signups"), DraftPersona(name="", description="nameless")],
    )
    draft = await infer_project_draft(_Llm(answer), _crawl(title="Acme"))
    assert draft["layer"] == LAYER_INFERRED
    fields = draft["fields"]
    assert fields["industry"] == {"value": "SaaS & Software", "provenance": PROVENANCE_INFERRED}
    assert "business_model" not in fields
    assert fields["brand_voice"]["value"] == "Technical"
    assert fields["personas"]["value"] == [
        {"name": "Marketing lead", "description": "wants signups", "priority": "primary"}
    ]


async def test_layer_two_takes_competitors_from_the_research_pass():
    research = AuditResearchContext(
        competitors=[
            CompetitorSignals(domain="mealbox.example", differentiators="cheaper"),
            CompetitorSignals(domain="", differentiators="ignored — no domain"),
        ],
        brand_voice="Friendly",
    )
    draft = await infer_project_draft(_Llm(DraftInference()), _crawl(title="Acme"), research)
    fields = draft["fields"]
    assert fields["compare_against"]["value"] == "mealbox.example"
    assert fields["competitors"]["value"] == [{"name": "mealbox.example", "differentiator": "cheaper"}]
    assert fields["brand_voice"]["value"] == "Friendly", "research's reading fills in when the classifier said nothing"


async def test_a_failed_inference_yields_no_event_rather_than_an_empty_one():
    assert await infer_project_draft(_Llm(RuntimeError("model down")), _crawl(title="Acme")) is None
