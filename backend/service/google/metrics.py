"""Build ``MetricValue`` / ``ComparisonMetric`` instances for Google Ads brief payloads."""

from __future__ import annotations

from briefs.schemas.google_ads_brief import ComparisonMetric, DeltaValue, MetricValue

from utils.formatting import money, number, percent, roas, safe_divide


def metric_value(value: float, kind: str, currency_code: str) -> MetricValue:
    if kind == "money":
        formatted = money(value, currency_code)
    elif kind == "percent":
        formatted = percent(value)
    elif kind == "roas":
        formatted = roas(value)
    else:
        formatted = number(value)
    return MetricValue(value=value, formatted=formatted)


def delta_value(current: float, previous: float, kind: str, currency_code: str) -> DeltaValue:
    absolute = current - previous
    percent_delta = safe_divide(absolute, previous) if previous else 0.0
    if absolute > 0:
        direction = "up"
    elif absolute < 0:
        direction = "down"
    else:
        direction = "flat"
    if kind == "money":
        absolute_text = money(abs(absolute), currency_code)
    elif kind == "percent":
        absolute_text = percent(abs(absolute))
    elif kind == "roas":
        absolute_text = roas(abs(absolute))
    else:
        absolute_text = number(abs(absolute))
    sign = "+" if absolute > 0 else "-" if absolute < 0 else ""
    percent_text = f"{abs(percent_delta) * 100:.1f}%"
    formatted = f"{sign}{absolute_text} ({sign}{percent_text})" if sign else "Flat"
    return DeltaValue(
        absolute=absolute,
        percent=percent_delta,
        direction=direction,
        formatted=formatted,
    )


def comparison_metric(
    current: float, previous: float, kind: str, currency_code: str
) -> ComparisonMetric:
    return ComparisonMetric(
        current=metric_value(current, kind, currency_code),
        previous=metric_value(previous, kind, currency_code),
        delta=delta_value(current, previous, kind, currency_code),
    )
