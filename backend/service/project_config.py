"""Project onboarding config and KPI option filtering rules."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ConfigOption:
    value: str
    label: str


INDUSTRY_OPTIONS: tuple[ConfigOption, ...] = (
    ConfigOption(value="E-commerce & Retail", label="E-commerce & Retail"),
    ConfigOption(value="SaaS & Software", label="SaaS & Software"),
    ConfigOption(value="Financial Services", label="Financial Services"),
    ConfigOption(value="Healthcare", label="Healthcare"),
    ConfigOption(value="Education", label="Education"),
    ConfigOption(value="Professional Services", label="Professional Services"),
    ConfigOption(value="Marketing & Advertising", label="Marketing & Advertising"),
    ConfigOption(value="Real Estate", label="Real Estate"),
    ConfigOption(value="Travel & Hospitality", label="Travel & Hospitality"),
    ConfigOption(value="Other", label="Other"),
)

BUSINESS_MODEL_OPTIONS: tuple[ConfigOption, ...] = (
    ConfigOption(value="B2B", label="B2B"),
    ConfigOption(value="B2C", label="B2C"),
    ConfigOption(value="Marketplace", label="Marketplace"),
    ConfigOption(value="PLG", label="PLG"),
    ConfigOption(value="Agency", label="Agency"),
    ConfigOption(value="Hybrid", label="Hybrid"),
)

NORTH_STAR_OPTIONS: tuple[ConfigOption, ...] = (
    ConfigOption(value="Weekly active users", label="Weekly active users"),
    ConfigOption(value="Monthly active customers", label="Monthly active customers"),
    ConfigOption(value="Qualified leads", label="Qualified leads"),
    ConfigOption(value="Pipeline created", label="Pipeline created"),
    ConfigOption(value="Net new revenue", label="Net new revenue"),
    ConfigOption(value="Retention rate", label="Retention rate"),
    ConfigOption(value="Bookings", label="Bookings"),
    ConfigOption(value="Custom", label="Custom"),
)

GROWTH_STAGE_OPTIONS: tuple[ConfigOption, ...] = (
    ConfigOption(value="0_pre_customer", label="No customers or active users yet"),
    ConfigOption(value="1_first_users", label="First active users/customers (1-10)"),
    ConfigOption(value="2_early_revenue", label="Early repeat usage or revenue (10-100 customers)"),
    ConfigOption(
        value="3_repeatable_growth",
        label="Repeatable growth motion (100+ customers or steady MoM growth)",
    ),
    ConfigOption(
        value="4_scaling",
        label="Scaling across channels or segments with predictable performance",
    ),
)


def _normalize_key(value: str) -> str:
    return value.strip().lower()


def _option_values(options: tuple[ConfigOption, ...]) -> set[str]:
    return {option.value for option in options}


ALL_NORTH_STAR_VALUES = _option_values(NORTH_STAR_OPTIONS)
ALL_GROWTH_STAGE_VALUES = _option_values(GROWTH_STAGE_OPTIONS)


def _build_option_subset(
    options: tuple[ConfigOption, ...],
    allowed_values: set[str],
) -> list[ConfigOption]:
    return [option for option in options if option.value in allowed_values]


# Rule precedence:
# 1) exact match (industry + business model)
# 2) industry wildcard or business model wildcard
# 3) broad fallback
NORTH_STAR_RULES: dict[tuple[str, str], set[str]] = {
    ("e-commerce & retail", "*"): {
        "Monthly active customers",
        "Net new revenue",
        "Retention rate",
        "Bookings",
        "Custom",
    },
    ("saas & software", "*"): {
        "Weekly active users",
        "Monthly active customers",
        "Qualified leads",
        "Pipeline created",
        "Net new revenue",
        "Retention rate",
        "Custom",
    },
    ("financial services", "*"): {
        "Qualified leads",
        "Pipeline created",
        "Net new revenue",
        "Retention rate",
        "Bookings",
        "Custom",
    },
    ("healthcare", "*"): {
        "Qualified leads",
        "Pipeline created",
        "Retention rate",
        "Bookings",
        "Custom",
    },
    ("education", "*"): {
        "Weekly active users",
        "Monthly active customers",
        "Retention rate",
        "Bookings",
        "Custom",
    },
    ("professional services", "*"): {
        "Qualified leads",
        "Pipeline created",
        "Net new revenue",
        "Bookings",
        "Custom",
    },
    ("marketing & advertising", "*"): {
        "Qualified leads",
        "Pipeline created",
        "Net new revenue",
        "Retention rate",
        "Custom",
    },
    ("real estate", "*"): {
        "Qualified leads",
        "Pipeline created",
        "Net new revenue",
        "Bookings",
        "Custom",
    },
    ("travel & hospitality", "*"): {
        "Monthly active customers",
        "Net new revenue",
        "Retention rate",
        "Bookings",
        "Custom",
    },
    ("*", "b2b"): {
        "Qualified leads",
        "Pipeline created",
        "Net new revenue",
        "Retention rate",
        "Bookings",
        "Custom",
    },
    ("*", "b2c"): {
        "Weekly active users",
        "Monthly active customers",
        "Net new revenue",
        "Retention rate",
        "Bookings",
        "Custom",
    },
    ("*", "marketplace"): {
        "Weekly active users",
        "Monthly active customers",
        "Net new revenue",
        "Retention rate",
        "Bookings",
        "Custom",
    },
    ("*", "plg"): {
        "Weekly active users",
        "Monthly active customers",
        "Retention rate",
        "Net new revenue",
        "Custom",
    },
    ("*", "agency"): {
        "Qualified leads",
        "Pipeline created",
        "Net new revenue",
        "Bookings",
        "Custom",
    },
    ("*", "hybrid"): set(ALL_NORTH_STAR_VALUES),
    ("*", "*"): set(ALL_NORTH_STAR_VALUES),
}

GROWTH_STAGE_RULES: dict[tuple[str, str], set[str]] = {
    ("*", "agency"): {
        "1_first_users",
        "2_early_revenue",
        "3_repeatable_growth",
        "4_scaling",
    },
    ("real estate", "*"): {
        "1_first_users",
        "2_early_revenue",
        "3_repeatable_growth",
        "4_scaling",
    },
    ("financial services", "*"): {
        "1_first_users",
        "2_early_revenue",
        "3_repeatable_growth",
        "4_scaling",
    },
    ("*", "*"): set(ALL_GROWTH_STAGE_VALUES),
}


def _resolve_allowed_values(
    *,
    rules: dict[tuple[str, str], set[str]],
    valid_values: set[str],
    industry: str,
    business_model: str,
) -> set[str]:
    normalized_industry = _normalize_key(industry) if industry else ""
    normalized_business_model = _normalize_key(business_model) if business_model else ""
    candidates = (
        (normalized_industry, normalized_business_model),
        (normalized_industry, "*"),
        ("*", normalized_business_model),
        ("*", "*"),
    )
    for candidate in candidates:
        values = rules.get(candidate)
        if not values:
            continue
        filtered = {value for value in values if value in valid_values}
        if filtered:
            return filtered
    return set(valid_values)


def get_project_config(*, industry: str = "", business_model: str = "") -> dict[str, list[ConfigOption]]:
    """Return onboarding options with KPI filters based on selected profile context."""
    allowed_north_stars = _resolve_allowed_values(
        rules=NORTH_STAR_RULES,
        valid_values=ALL_NORTH_STAR_VALUES,
        industry=industry,
        business_model=business_model,
    )
    allowed_growth_stages = _resolve_allowed_values(
        rules=GROWTH_STAGE_RULES,
        valid_values=ALL_GROWTH_STAGE_VALUES,
        industry=industry,
        business_model=business_model,
    )

    return {
        "industry_options": list(INDUSTRY_OPTIONS),
        "business_model_options": list(BUSINESS_MODEL_OPTIONS),
        "north_star_metric_options": _build_option_subset(NORTH_STAR_OPTIONS, allowed_north_stars),
        "growth_stage_milestone_options": _build_option_subset(GROWTH_STAGE_OPTIONS, allowed_growth_stages),
    }
