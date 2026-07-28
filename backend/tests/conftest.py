"""Shared pytest fixtures for backend agent tests.

``tests`` is a package (see tests/__init__.py) so the evaluation harness in
``tests.eval`` imports cleanly from individual test modules.
"""

import pytest

from agents.audit.schema import AuditBusinessContext


@pytest.fixture
def acme_business_context():
    return AuditBusinessContext(
        business_name="Acme CRM",
        business_goals="Improve organic search visibility and drive signups.",
    )


@pytest.fixture
def maxaura_business_context():
    return AuditBusinessContext(
        business_name="MaxAura",
        business_description="AI-powered grooming and self-improvement tools for men",
        business_goals="Rank for looksmaxxing, grooming, and self-improvement keywords",
        target_keywords=["looksmaxxing", "grooming tips for men", "face care routine", "jawline exercises"],
        competitors=["rmrs.com", "artofmanliness.com", "tiege.com"],
        audience_segment="men aged 18–35 interested in self-improvement and aesthetics",
        industry="health & beauty / men's grooming",
    )


@pytest.fixture
def duct_business_context():
    return AuditBusinessContext(
        business_name="Duct",
        business_description="AI-powered SEO audit and organic growth intelligence for marketers",
        business_goals="Rank for SEO audit, AIO, and organic growth keywords",
        target_keywords=["SEO audit tool", "AI SEO", "organic growth platform"],
        competitors=["semrush.com", "ahrefs.com", "searchatlas.com"],
        industry="SaaS / marketing technology",
    )
