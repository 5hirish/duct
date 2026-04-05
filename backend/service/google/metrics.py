"""Build ``MetricValue`` / ``ComparisonMetric`` instances for Google Ads brief payloads."""

from __future__ import annotations

from service.google.schema import (
    ComparisonMetric,
    DeltaDirection,
    DeltaValue,
    MetricFormatKind,
    MetricValue,
)

from utils.formatting import money, multiplier, number, percent, safe_divide


def metric_value(value: float, kind: MetricFormatKind, currency_code: str) -> MetricValue:
    match kind:
        case MetricFormatKind.CURRENCY:
            formatted = money(value, currency_code)
        case MetricFormatKind.PERCENT:
            formatted = percent(value)
        case MetricFormatKind.MULTIPLIER:
            formatted = multiplier(value)
        case MetricFormatKind.NUMBER:
            formatted = number(value)
    return MetricValue(value=value, formatted=formatted)


def delta_value(
    current: float, previous: float, kind: MetricFormatKind, currency_code: str
) -> DeltaValue:
    absolute = current - previous
    percent_delta = safe_divide(absolute, previous) if previous else 0.0
    if absolute > 0:
        direction = DeltaDirection.UP
    elif absolute < 0:
        direction = DeltaDirection.DOWN
    else:
        direction = DeltaDirection.FLAT
    match kind:
        case MetricFormatKind.CURRENCY:
            absolute_text = money(abs(absolute), currency_code)
        case MetricFormatKind.PERCENT:
            absolute_text = percent(abs(absolute))
        case MetricFormatKind.MULTIPLIER:
            absolute_text = multiplier(abs(absolute))
        case MetricFormatKind.NUMBER:
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
    current: float, previous: float, kind: MetricFormatKind, currency_code: str
) -> ComparisonMetric:
    return ComparisonMetric(
        current=metric_value(current, kind, currency_code),
        previous=metric_value(previous, kind, currency_code),
        delta=delta_value(current, previous, kind, currency_code),
    )
