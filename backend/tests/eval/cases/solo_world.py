"""Solo's accounts, simulated day by day, so an eval can ask them anything.

Solo is the fictional budgeting app for freelancers every product screenshot
is drawn from (``app/src/lib/__fixtures__/solo-story.mjs``); nothing here is
a real company, account or number. A replay bundle answers only the exact
pulls its session made, keyed on the dates that model typed. A new model picks
its own windows, so a gate built on bundles scores seed misses, not briefs.
This answers **any** window, from daily series, so the four weeks before the
last four are consistent with them and every total a brief quotes has one
right value.

It is installed under the real ``fetch_entity`` (see :meth:`SoloWorld.install`):
the envelope, window resolution, Duct's totals and the payload cut are
production code, and only the vendor call and the credential lookup are
replaced. Offline, deterministic, no randomness: the "noise" is a hash of the
row and the day.

One story is planted, the one a good brief finds: from 14 days before the
run, the freelance tax guide slipped from position ~3 to ~6 in Search
Console, and its organic sessions fell by 45% with it. Everything else moves
only with the week.
"""

from __future__ import annotations

import hashlib
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from datetime import date, timedelta
from typing import Any, Callable, Iterator

SITE = "https://solobudget.app"
ADS_ACCOUNT = "493-221-0815"
GA4_PROPERTY = "properties/318224410"

#: Days before the run the tax guide's ranking slipped.
SHIFT_DAYS = 14
HISTORY_DAYS = 400
PRICE_EUR = 7.99

BOUND = {
    "ga4": (GA4_PROPERTY, "Solo · web"),
    "gsc": ("sc-domain:solobudget.app", "solobudget.app"),
    "google_ads": (ADS_ACCOUNT, "Solo · EU"),
}
NOT_CONNECTED = ("mixpanel", "clarity", "growthbook")

# Weekday traffic shape, Monday first: freelancers budget on Mondays.
_WEEK = (1.18, 1.08, 1.02, 0.98, 0.9, 0.78, 0.86)


def _noise(*parts: object) -> float:
    """±6%, fixed for a given row and day."""
    digest = hashlib.sha256("|".join(map(str, parts)).encode()).digest()
    return 0.94 + (digest[0] / 255) * 0.12


@dataclass(frozen=True)
class Page:
    path: str
    sessions: dict[str, float]  # channel -> sessions/day
    conv_rate: float
    bounce: float
    duration_s: float
    impressions: float = 0.0    # Search Console, per day
    position: float = 0.0
    shifted: bool = False       # the planted slip
    queries: tuple[str, ...] = ()


_TAIL = tuple(
    Page(
        f"/blog/{slug}",
        {"Organic Search": 1 + (i * 7) % 9, "Direct": (i % 3) / 2},
        conv_rate=0.002, bounce=0.74, duration_s=80,
        impressions=40 + (i * 37) % 260, position=8 + (i * 5) % 22,
    )
    for i, slug in enumerate(
        f"{a}-{b}" for a in ("budget", "invoice", "tax", "savings", "cashflow", "pricing")
        for b in ("tips", "checklist", "mistakes", "for-designers", "for-developers", "2026")
    )
)

PAGES: tuple[Page, ...] = (
    Page("/", {"Organic Search": 60, "Paid Search": 25, "Direct": 45, "Referral": 8},
         conv_rate=0.015, bounce=0.42, duration_s=55, impressions=900, position=1.4,
         queries=("solo budget app", "solo app freelancers")),
    Page("/pricing", {"Organic Search": 22, "Paid Search": 30, "Direct": 15, "Referral": 3},
         conv_rate=0.06, bounce=0.35, duration_s=70, impressions=700, position=4.5,
         queries=("solo budget pricing",)),
    Page("/blog/freelance-tax-guide", {"Organic Search": 95, "Direct": 3, "Referral": 6},
         conv_rate=0.004, bounce=0.71, duration_s=140, impressions=2600, position=3.1,
         shifted=True, queries=("freelance tax guide", "self employed tax deductions",
                                "quarterly tax freelancer")),
    Page("/blog/invoice-template", {"Organic Search": 40, "Direct": 4, "Referral": 2},
         conv_rate=0.006, bounce=0.66, duration_s=95, impressions=2100, position=5.8,
         queries=("invoice template free", "freelance invoice template")),
    Page("/features/receipts", {"Organic Search": 12, "Paid Search": 14, "Direct": 5},
         conv_rate=0.02, bounce=0.48, duration_s=60, impressions=500, position=6.2,
         queries=("receipt scanner app",)),
    Page("/signup", {"Direct": 20, "Paid Search": 6, "Organic Search": 4},
         conv_rate=0.25, bounce=0.2, duration_s=45),
    *_TAIL,
)

# After the slip: the tax guide ranks ~6 instead of ~3, shows a little less,
# and its organic sessions fall by 45%.
_SHIFT_SESSIONS = 0.55
_SHIFT_IMPRESSIONS = 0.88
_SHIFTED_POSITION = 6.4

_SOURCE = {
    "Organic Search": (("google / organic", 0.9), ("bing / organic", 0.1)),
    "Paid Search": (("google / cpc", 1.0),),
    "Direct": (("(direct) / (none)", 1.0),),
    "Referral": (("producthunt.com / referral", 0.6), ("indiehackers.com / referral", 0.4)),
}


@dataclass(frozen=True)
class Campaign:
    cid: str
    name: str
    spend: float        # €/day
    cpc: float
    ctr: float
    cvr: float          # conversions per click
    value_per_conv: float
    status: str = "ENABLED"


CAMPAIGNS: tuple[Campaign, ...] = (
    Campaign("20114", "Solo · Search · Brand EU", 38.0, 0.62, 0.21, 0.071, 24.0),
    Campaign("20115", "Solo · Performance Max · Freelancers", 96.0, 0.88, 0.019, 0.045, 21.0),
    Campaign("20116", "Solo · Brand · Legacy", 9.0, 0.71, 0.12, 0.05, 24.0, status="PAUSED"),
)

_DEVICES = (("MOBILE", 0.62), ("DESKTOP", 0.33), ("TABLET", 0.05))
_COUNTRIES = (("2724", 0.4), ("2276", 0.35), ("2250", 0.25))  # ES, DE, FR
_TERMS = (
    ("solo budget app", "EXACT", 0.3), ("budgeting app freelancers", "PHRASE", 0.22),
    ("freelance budget tool", "BROAD", 0.14), ("expense tracker self employed", "BROAD", 0.12),
    ("solo app", "EXACT", 0.1), ("invoice and budget app", "PHRASE", 0.07),
    ("best budgeting app", "BROAD", 0.05),
)


@dataclass
class SoloWorld:
    """Daily series for Solo, anchored on the day the eval runs."""

    today: date = field(default_factory=date.today)

    # --- time ---------------------------------------------------------------

    def days(self, date_from: str, date_to: str) -> list[date]:
        start, end = date.fromisoformat(date_from), date.fromisoformat(date_to)
        first = self.today - timedelta(days=HISTORY_DAYS)
        last = self.today - timedelta(days=1)  # today has not closed
        start, end = max(start, first), min(end, last)
        return [start + timedelta(days=i) for i in range((end - start).days + 1)] if start <= end else []

    def shifted(self, day: date) -> bool:
        return day >= self.today - timedelta(days=SHIFT_DAYS)

    # --- GA4 ----------------------------------------------------------------

    def _page_day(self, page: Page, channel: str, day: date) -> float:
        base = page.sessions.get(channel, 0.0)
        if page.shifted and channel == "Organic Search" and self.shifted(day):
            base *= _SHIFT_SESSIONS
        return base * _WEEK[day.weekday()] * _noise(page.path, channel, day)

    def ga4_landing_pages(self, date_from: str, date_to: str) -> dict:
        days = self.days(date_from, date_to)
        rows = []
        for page in PAGES:
            for channel in page.sessions:
                for source, share in _SOURCE[channel]:
                    sessions = round(sum(self._page_day(page, channel, d) for d in days) * share)
                    if not sessions:
                        continue
                    conversions = round(sessions * page.conv_rate, 1)
                    rows.append({
                        "page_path": page.path,
                        "channel": channel,
                        "session_source_medium": source,
                        "sessions": sessions,
                        "bounce_rate": round(page.bounce * _noise("b", page.path, channel), 4),
                        "engagement_rate": round(1 - page.bounce * _noise("b", page.path, channel), 4),
                        "average_session_duration": round(page.duration_s * _noise("t", page.path), 1),
                        "conversions": conversions,
                        "total_revenue": round(conversions * PRICE_EUR, 2),
                    })
        rows.sort(key=lambda r: -r["sessions"])
        return {
            "report_type": "ga4_landing_pages",
            "date_range": f"{date_from} to {date_to}",
            "row_count": len(rows),
            "truncated": False,
            "rows": rows,
        }

    def ga4_conversion_paths(self, date_from: str, date_to: str) -> dict:
        grouped: dict[tuple[str, str], dict[str, float]] = {}
        for row in self.ga4_landing_pages(date_from, date_to)["rows"]:
            bucket = grouped.setdefault((row["session_source_medium"], row["channel"]),
                                        {"sessions": 0, "conversions": 0.0, "total_revenue": 0.0})
            for key in bucket:
                bucket[key] += row[key]
        rows = [
            {"session_source_medium": sm, "session_default_channel_group": ch,
             "conversions": round(v["conversions"], 1), "total_revenue": round(v["total_revenue"], 2),
             "sessions": int(v["sessions"]), "engaged_sessions": int(v["sessions"] * 0.4)}
            for (sm, ch), v in grouped.items()
        ]
        rows.sort(key=lambda r: -r["conversions"])
        return {"report_type": "ga4_conversion_paths", "date_range": f"{date_from} to {date_to}",
                "row_count": len(rows), "rows": rows}

    # --- Search Console -----------------------------------------------------

    def _gsc_day(self, page: Page, day: date) -> tuple[float, float, float]:
        """(clicks, impressions, position) for one page on one day."""
        slipped = page.shifted and self.shifted(day)
        impressions = page.impressions * (_SHIFT_IMPRESSIONS if slipped else 1.0)
        impressions *= _WEEK[day.weekday()] * _noise("imp", page.path, day)
        position = _SHIFTED_POSITION if slipped else page.position
        clicks = self._page_day(page, "Organic Search", day) * 0.96
        return clicks, impressions, position

    def _gsc_rows(self, date_from: str, date_to: str, *, by: str) -> list[dict]:
        days = self.days(date_from, date_to)
        rows = []
        for page in PAGES:
            if not page.impressions:
                continue
            clicks = imp = weighted = 0.0
            for d in days:
                c, i, p = self._gsc_day(page, d)
                clicks, imp, weighted = clicks + c, imp + i, weighted + p * i
            if not imp:
                continue
            if by == "page":
                rows.append(self._gsc_row({"page": SITE + page.path}, clicks, imp, weighted))
                continue
            queries = page.queries or (page.path.rsplit("/", 1)[-1].replace("-", " "),)
            for n, query in enumerate(queries):
                share = 1 / (n + 1.6)
                total = sum(1 / (k + 1.6) for k in range(len(queries)))
                dims = {"query": query} | ({"page": SITE + page.path} if by == "query_page" else {})
                rows.append(self._gsc_row(dims, clicks * share / total, imp * share / total, weighted * share / total))
        rows.sort(key=lambda r: -r["impressions"])
        return rows

    @staticmethod
    def _gsc_row(dims: dict, clicks: float, impressions: float, weighted: float) -> dict:
        clicks, impressions = round(clicks), round(impressions)
        return dims | {
            "clicks": clicks,
            "impressions": impressions,
            "ctr": round(clicks / impressions, 4) if impressions else 0.0,
            "avg_position": round(weighted / impressions, 1) if impressions else 0.0,
        }

    def gsc(self, report_type: str, by: str) -> Callable[[str, str], dict]:
        def fetch(date_from: str, date_to: str) -> dict:
            rows = self._gsc_rows(date_from, date_to, by=by)
            listed = rows[:30]
            total_imp = sum(r["impressions"] for r in rows)
            return {
                "report_type": report_type,
                "date_range": f"{date_from} to {date_to}",
                "row_count": len(listed),
                "totals": {"rows_available": len(rows), "clicks": sum(r["clicks"] for r in rows),
                           "impressions": total_imp},
                "truncated": len(rows) > len(listed),
                "impressions_coverage": round(sum(r["impressions"] for r in listed) / total_imp, 3)
                if total_imp else 1.0,
                "data_state": "all (the last 2-3 days are not yet final)",
                "rows": listed,
            }
        return fetch

    # --- Google Ads ---------------------------------------------------------

    def _campaign_window(self, camp: Campaign, days: list[date], share: float = 1.0) -> dict:
        # A paused campaign spent until it was paused, 45 days ago.
        paused = self.today - timedelta(days=45) if camp.status == "PAUSED" else None
        spend = share * sum(
            camp.spend * _WEEK[d.weekday()] * _noise(camp.cid, d)
            for d in days if paused is None or d < paused
        )
        clicks = round(spend / camp.cpc)
        impressions = round(clicks / camp.ctr) if camp.ctr else 0
        conversions = round(clicks * camp.cvr, 1)
        value = round(conversions * camp.value_per_conv, 2)
        spend = round(spend, 2)
        return {
            "clicks": clicks, "impressions": impressions, "spend": spend,
            "ctr": round(clicks / impressions, 4) if impressions else 0.0,
            "conversions": conversions,
            "cost_per_conversion": round(spend / conversions, 2) if conversions else 0.0,
            "conversion_value": value,
            "roas": round(value / spend, 2) if spend else 0.0,
        }

    def _previous(self, date_from: str, date_to: str) -> tuple[str, str]:
        start, end = date.fromisoformat(date_from), date.fromisoformat(date_to)
        length = (end - start).days + 1
        return (start - timedelta(days=length)).isoformat(), (start - timedelta(days=1)).isoformat()

    def campaign_performance(self, date_from: str, date_to: str) -> dict:
        days = self.days(date_from, date_to)
        prev_days = self.days(*self._previous(date_from, date_to))
        rows = []
        for camp in CAMPAIGNS:
            cur, prev = self._campaign_window(camp, days), self._campaign_window(camp, prev_days)
            rows.append({"campaign_name": camp.name, "campaign_id": camp.cid, "channel_type": "SEARCH"
                         if "Search" in camp.name else "PERFORMANCE_MAX", "status": camp.status, **cur,
                         "average_cpc": round(cur["spend"] / cur["clicks"], 2) if cur["clicks"] else 0.0,
                         "previous": {k: float(prev[k]) for k in
                                      ("clicks", "impressions", "spend", "conversions", "conversion_value")}})
        rows.sort(key=lambda r: -r["spend"])
        prev_from, prev_to = self._previous(date_from, date_to)
        return {"source_metadata": {"source": "google_ads_api", "export_type": "campaign_performance",
                                    "window_current": f"{date_from} to {date_to}",
                                    "window_previous": f"{prev_from} to {prev_to}", "currency_code": "EUR",
                                    "account_name": BOUND["google_ads"][1], "account_id": ADS_ACCOUNT},
                "rows": rows}

    def _split(self, report_type: str, splits: tuple, dims: Callable[[Campaign, tuple], dict]):
        def fetch(date_from: str, date_to: str) -> dict:
            days = self.days(date_from, date_to)
            rows = [dims(camp, part) | {"campaign_name": camp.name, "campaign_id": camp.cid}
                    | self._campaign_window(camp, days, part[-1])
                    for camp in CAMPAIGNS for part in splits]
            rows = [r for r in rows if r["spend"]]
            rows.sort(key=lambda r: -r["spend"])
            return {"report_type": report_type, "date_range": f"{date_from} to {date_to}",
                    "row_count": len(rows), "rows": rows}
        return fetch

    # --- wiring -------------------------------------------------------------

    def fetchers(self) -> dict[str, Callable[[str, str], dict]]:
        return {
            "ga4_landing_pages": self.ga4_landing_pages,
            "ga4_conversion_paths": self.ga4_conversion_paths,
            "gsc_page_performance": self.gsc("gsc_page_performance", "page"),
            "gsc_query_performance": self.gsc("gsc_query_performance", "query"),
            "gsc_query_page": self.gsc("gsc_query_page", "query_page"),
            "campaign_performance": self.campaign_performance,
            "device_performance": self._split("device_performance", _DEVICES,
                                              lambda c, p: {"device": p[0]}),
            "geo_performance": self._split("geo_performance", _COUNTRIES,
                                           lambda c, p: {"country_criterion_id": p[0],
                                                         "location_type": "LOCATION_OF_PRESENCE"}),
            "ad_group_performance": self._split(
                "ad_group_performance", (("Core", 0.6), ("Competitor", 0.4)),
                lambda c, p: {"ad_group_name": f"{c.name.split(' · ')[-1]} · {p[0]}",
                              "ad_group_id": f"{c.cid}{len(p[0])}", "status": "ENABLED"}),
            "search_terms": self._split("search_terms", tuple((t, m, s) for t, m, s in _TERMS),
                                        lambda c, p: {"search_term": p[0], "match_type": p[1]}),
        }

    def data_sources(self) -> list[dict]:
        """What ListDataSources and the ``<data_sources>`` block report."""
        rows = [{"connector_id": cid, "status": "bound", "account_id": acc, "account_name": name}
                for cid, (acc, name) in BOUND.items()]
        rows += [{"connector_id": cid, "status": "not_connected", "auth_kind": "manual"}
                 for cid in NOT_CONNECTED]
        return rows

    @contextmanager
    def install(self) -> Iterator["SoloWorld"]:
        """Answer every connector read from this world, for the life of the block.

        Replaced: each fetch spec's vendor call, and the three credential and
        binding lookups. Kept: everything ``fetch_entity`` does around them.
        """
        from agents.insights import fetchers
        import service.connector_access as access

        answers = self.fetchers()
        specs = {
            entity_id: replace(spec, call=_adapter(answers[entity_id]))
            for entity_id, spec in fetchers.fetch_specs().items()
            if entity_id in answers
        }
        # Every other entity keeps its spec: its connector is unbound here, so
        # fetch_entity answers not_connected before the call would ever run.
        specs |= {k: v for k, v in fetchers.fetch_specs().items() if k not in specs}
        saved = {
            (fetchers, "_specs"): fetchers._specs,
            (access, "get_data_source"): access.get_data_source,
            (access, "resolve_read_credentials"): access.resolve_read_credentials,
            (access, "list_data_sources"): access.list_data_sources,
        }
        sources = {s["connector_id"]: s for s in self.data_sources()}

        def get_data_source(_db, connector_id, **_kw):
            src = sources.get(connector_id)
            return _Source(src) if src else None

        fetchers._specs = specs
        access.get_data_source = get_data_source
        access.resolve_read_credentials = lambda _db, **kw: (
            {"refresh_token": "synthetic"} if kw.get("connector_type") in BOUND else {}
        )
        access.list_data_sources = lambda _db, **_kw: [_Source(s) for s in self.data_sources()]
        try:
            yield self
        finally:
            for (module, name), value in saved.items():
                setattr(module, name, value)


def _adapter(fetch: Callable[[str, str], dict]) -> Callable[[str, str, str, dict], dict]:
    return lambda _account_id, date_from, date_to, _creds: fetch(date_from, date_to)


class _Source:
    """Quacks like connector_access's DataSource for the three readers above."""

    def __init__(self, row: dict[str, Any]) -> None:
        self._row = row
        self.connector_id = row["connector_id"]
        self.status = row["status"]
        self.account_id = row.get("account_id", "")
        self.account_name = row.get("account_name", "")

    def as_dict(self) -> dict[str, Any]:
        return dict(self._row)
