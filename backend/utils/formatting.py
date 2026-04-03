"""Number and currency formatting helpers."""

from __future__ import annotations


def money(value: float, currency_code: str) -> str:
    symbol = "$" if currency_code == "USD" else f"{currency_code} "
    return f"{symbol}{value:,.2f}"


def number(value: float) -> str:
    return f"{value:,.0f}"


def percent(value: float) -> str:
    return f"{value * 100:.1f}%"


def roas(value: float) -> str:
    return f"{value:.2f}x"


def safe_divide(a: float, b: float) -> float:
    return a / b if b else 0.0
