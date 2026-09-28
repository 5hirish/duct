"""Totals and weighted rates for a fetched entity, computed by Duct, not the model.

A replay of a real brief reasoned correctly and added wrong: 2,504 sessions
where the rows summed to 2,681. The prompt already said "totals before rows";
the model still did the adding, and a language model adding 250 numbers is
the one step in a brief most likely to be wrong and least likely to be caught.
The catalog already declares what the arithmetic needs (every metric's
``agg: sum|avg``, and for an average its ratio or its weight), so the sum is
Duct's job, on every provider, in scheduled briefs too, with no sandbox.

Two rules the arithmetic keeps:

* **An average is never averaged.** The mean of 250 per-page bounce rates is
  not the site's bounce rate. A ratio metric (CPA, ROAS, CTR) is its
  numerator's total over its denominator's, from the catalog's ``ratio``;
  anything else is the mean weighted by its catalog ``weight`` (bounce rate by
  sessions, position by impressions). The difference matters: CPA weighted by
  conversions drops every row that spent and converted nothing, which is the
  spend a CPA exists to show. An average whose entry names neither gets no
  total at all.
* **Say what the total covers.** Search Console's fetcher already sums every
  row of the window before it lists the top few hundred, so its totals are the
  window's. Every other fetcher's rows are what the total is over, and a
  report the source says it cut (``truncated``) says so, so a partial sum is
  never quoted as the whole.

Framework-free: ``fetchers.fetch_entity`` calls :func:`summarise` on every
``ok`` pull. docs/engineering/2026-09-27-insights-code-execution-design.md
(phase 1).
"""

from __future__ import annotations

from typing import Any

from agents.insights.catalog.base import _CATALOGS

AGG_SUM = "sum"
AGG_AVG = "avg"

# Money and rates are quoted to cents and basis points; a total that prints
# 17 decimal places reads as a different number from the one in the table.
_MONEY_DECIMALS = 2
_RATE_DECIMALS = 4

TOTALS_NOTE = (
    "Quote totals and rates from `totals` and `rates`, and a slice of them (one channel, "
    "one device) from `subtotals`, never by adding or averaging rows yourself. What "
    "they cover is in `totals_cover`."
)

# A dimension with at most this many values gets subtotals: channel, device,
# match type. "How did organic do" is a question about one channel's slice of
# a report, and without its subtotal the model is back to adding rows. Pages
# and queries run to hundreds of values; their subtotals would be the rows.
SUBTOTAL_MAX_GROUPS = 12


def entity_fields(entity_id: str) -> dict[str, dict]:
    """The catalog's field map for one entity, or ``{}`` when it is unknown."""
    for catalog in _CATALOGS.values():
        for entity in catalog.get("entities", []):
            if entity.get("entity_id") == entity_id:
                return entity.get("fields", {})
    return {}


def _number(value: Any) -> float | None:
    # bool is an int in Python; a flag summed as 0/1 would be a silent lie.
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _tidy(value: float, *, decimals: int) -> float | int:
    return int(value) if float(value).is_integer() else round(value, decimals)


def _sum(rows: list[dict], field: str) -> float | int | None:
    values = [v for v in (_number(r.get(field)) for r in rows) if v is not None]
    if not values:
        return None
    return _tidy(sum(values), decimals=_MONEY_DECIMALS)


def _weighted(rows: list[dict], field: str, weight: str) -> float | None:
    """sum(value × weight) / sum(weight), over rows that carry both."""
    num = den = 0.0
    for row in rows:
        value, w = _number(row.get(field)), _number(row.get(weight))
        if value is None or w is None:
            continue
        num += value * w
        den += w
    return round(num / den, _RATE_DECIMALS) if den else None


def _ratio(
    totals: dict, rows: list[dict], source_totals: dict, numerator: str, denominator: str
) -> float | None:
    """Total over total. Read from ``totals`` when the catalog sums the field,
    straight off the rows when it does not (Ads rows carry impressions and
    conversion value on every entity; not every entity declares them)."""
    def total(field: str) -> float | None:
        if field in totals:
            return float(totals[field])
        whole = _number(source_totals.get(field))
        return whole if whole is not None else _sum(rows, field)

    num, den = total(numerator), total(denominator)
    if num is None or not den:
        return None
    return round(num / den, _RATE_DECIMALS)


def _previous_totals(rows: list[dict]) -> dict[str, float | int]:
    """Totals of each row's ``previous`` period, when every row carries one
    (Google Ads campaigns do), so the comparison is Duct's sum too."""
    slices = [r.get("previous") for r in rows]
    if not slices or not all(isinstance(s, dict) for s in slices):
        return {}
    out: dict[str, float | int] = {}
    for key in slices[0]:
        total = _sum(slices, key)
        if total is not None:
            out[key] = total
    return out


def summarise(entity_id: str, data: Any) -> dict[str, Any]:
    """``totals``, ``rates``, ``totals_cover`` and a ``note`` for one pull's data.

    Empty when the pull is not rows the catalog describes — a summary-shaped
    connector (Mixpanel, Clarity) has already done its own arithmetic.
    """
    fields = entity_fields(entity_id)
    rows = data.get("rows") if isinstance(data, dict) else None
    if not fields or not isinstance(rows, list) or not rows:
        return {}
    rows = [r for r in rows if isinstance(r, dict)]
    source_totals = data.get("totals") if isinstance(data.get("totals"), dict) else {}

    totals: dict[str, float | int] = {}
    rates: dict[str, dict] = {}
    for name, meta in fields.items():
        if meta.get("type") != "metric":
            continue
        if meta.get("agg") == AGG_SUM:
            # The fetcher's own total covers rows it did not list; ours cannot.
            total = _number(source_totals.get(name))
            value = _tidy(total, decimals=_MONEY_DECIMALS) if total is not None else _sum(rows, name)
            if value is not None:
                totals[name] = value
    for name, meta in fields.items():
        if meta.get("type") != "metric" or meta.get("agg") != AGG_AVG:
            continue
        if meta.get("ratio"):
            numerator, denominator = meta["ratio"]
            value = _ratio(totals, rows, source_totals, numerator, denominator)
            if value is not None:
                rates[name] = {"value": value, "ratio": f"{numerator} / {denominator}"}
        elif meta.get("weight"):
            value = _weighted(rows, name, meta["weight"])
            if value is not None:
                rates[name] = {"value": value, "weighted_by": meta["weight"]}

    if not totals and not rates:
        return {}
    out: dict[str, Any] = {"totals": totals, "totals_cover": _cover(data, rows, source_totals)}
    if rates:
        out["rates"] = rates
    subtotals = _subtotals(fields, rows, sums=[n for n in totals if not source_totals])
    if subtotals:
        out["subtotals"] = subtotals
    previous = _previous_totals(rows)
    if previous:
        out["previous_totals"] = previous
    out["note"] = TOTALS_NOTE
    return out


def _subtotals(fields: dict[str, dict], rows: list[dict], *, sums: list[str]) -> dict[str, dict]:
    """``{dimension: {value: {metric: sum}}}`` for each low-cardinality dimension.

    Only sums, and only where Duct's totals are over the same rows: when the
    source totalled the whole window (Search Console), a slice of the listed
    rows would not add up to it. A dimension that splits nothing (one row per
    value, like campaign on the campaign report) is the rows again and is left
    out.
    """
    out: dict[str, dict] = {}
    for dim, meta in fields.items():
        if meta.get("type") != "dimension" or not sums:
            continue
        groups: dict[str, list[dict]] = {}
        for row in rows:
            value = row.get(dim)
            if isinstance(value, str) and value:
                groups.setdefault(value, []).append(row)
        if not 1 < len(groups) <= SUBTOTAL_MAX_GROUPS or len(groups) == len(rows):
            continue
        out[dim] = {
            value: {name: total for name in sums if (total := _sum(members, name)) is not None}
            for value, members in sorted(groups.items(), key=lambda kv: -len(kv[1]))
        }
    return out


def _cover(data: dict, rows: list[dict], source_totals: dict) -> str:
    """What the totals are over, in words the model can repeat."""
    listed = len(rows)
    available = _number(source_totals.get("rows_available"))
    if source_totals:
        whole = f"{int(available):,} rows" if available is not None else "every row"
        return (
            f"sums and ratios: the whole window ({whole}), not just the {listed:,} listed; "
            f"weighted averages: the {listed:,} rows listed"
        )
    if data.get("truncated"):
        return (
            f"the {listed:,} rows returned; the source cut this report, so the window "
            "has more and these totals are a floor"
        )
    return f"all {listed:,} rows returned"
