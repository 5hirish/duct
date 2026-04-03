#!/usr/bin/env python3
"""Convert a manual Google Ads export into a stable raw JSON file.

This MVP intentionally supports manual exports first because that is the
fastest way to validate report shape before dealing with API auth complexity.
"""

from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


COLUMN_ALIASES = {
    "campaign_name": ["campaign", "campaign name"],
    "campaign_id": ["campaign id"],
    "channel_type": ["advertising channel type", "channel type"],
    "status": ["status", "campaign status"],
    "clicks": ["clicks"],
    "impressions": ["impressions"],
    "spend": ["cost", "spend"],
    "ctr": ["ctr"],
    "average_cpc": ["avg. cpc", "average cpc"],
    "conversions": ["conversions"],
    "cost_per_conversion": ["cost / conv.", "cost per conversion"],
    "conversion_value": ["conv. value", "conversion value"],
    "roas": ["conv. value / cost", "roas"],
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Convert Google Ads export to raw JSON.")
    parser.add_argument("--input-csv", help="Path to manual campaign export CSV.")
    parser.add_argument("--input-json", help="Path to already structured JSON export.")
    parser.add_argument("--output", required=True, help="Path to write raw JSON.")
    parser.add_argument("--account-name", default="Demo Google Ads Account")
    parser.add_argument("--account-id", default="")
    parser.add_argument("--currency-code", default="USD")
    parser.add_argument("--window-current", default="last_7_days")
    parser.add_argument("--window-previous", default="previous_7_days")
    return parser.parse_args()


def read_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def normalize_header(name: str) -> str:
    return " ".join(name.strip().lower().replace("_", " ").split())


def lookup_value(row: Dict[str, str], field_name: str) -> Optional[str]:
    normalized = {normalize_header(key): value for key, value in row.items()}
    for alias in COLUMN_ALIASES[field_name]:
        if alias in normalized:
            return normalized[alias]
    return None


def parse_number(value: Optional[str]) -> float:
    if value is None:
        return 0.0
    text = str(value).strip().replace(",", "").replace("$", "").replace("%", "")
    if not text or text == "--":
        return 0.0
    return float(text)


def parse_csv_rows(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for raw_row in reader:
            campaign_name = lookup_value(raw_row, "campaign_name")
            if not campaign_name:
                continue
            rows.append(
                {
                    "campaign_name": campaign_name,
                    "campaign_id": lookup_value(raw_row, "campaign_id"),
                    "channel_type": lookup_value(raw_row, "channel_type"),
                    "status": lookup_value(raw_row, "status"),
                    "clicks": int(parse_number(lookup_value(raw_row, "clicks"))),
                    "impressions": int(parse_number(lookup_value(raw_row, "impressions"))),
                    "spend": parse_number(lookup_value(raw_row, "spend")),
                    "ctr": parse_number(lookup_value(raw_row, "ctr")) / 100.0,
                    "average_cpc": parse_number(lookup_value(raw_row, "average_cpc")),
                    "conversions": parse_number(lookup_value(raw_row, "conversions")),
                    "cost_per_conversion": parse_number(
                        lookup_value(raw_row, "cost_per_conversion")
                    ),
                    "conversion_value": parse_number(lookup_value(raw_row, "conversion_value")),
                    "roas": parse_number(lookup_value(raw_row, "roas")),
                }
            )
    return rows


def build_payload(args: argparse.Namespace, rows: Iterable[Dict[str, Any]], source_file: str) -> Dict[str, Any]:
    return {
        "source_metadata": {
            "source": "google_ads_manual_export",
            "export_type": "campaign_performance",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "window_current": args.window_current,
            "window_previous": args.window_previous,
            "currency_code": args.currency_code,
            "account_name": args.account_name,
            "account_id": args.account_id or None,
            "source_file": source_file,
            "notes": [
                "Manual export MVP path",
                "Google Ads only",
            ],
        },
        "rows": list(rows),
    }


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")


def main() -> None:
    args = parse_args()
    if not args.input_csv and not args.input_json:
        raise SystemExit("Provide either --input-csv or --input-json.")

    if args.input_json:
        input_path = Path(args.input_json)
        payload = read_json(input_path)
        if "source_metadata" not in payload or "rows" not in payload:
            raise SystemExit("Input JSON must already contain source_metadata and rows.")
    else:
        input_path = Path(args.input_csv)
        rows = parse_csv_rows(input_path)
        payload = build_payload(args, rows, str(input_path))

    write_json(Path(args.output), payload)


if __name__ == "__main__":
    main()
