"""A tiny, made-up bronze folder so CI can build and test the whole warehouse on every push.

The numbers are invented but consistent (states add up to the national row), and they
exercise the awkward rules: ₹ lakh to ₹ crore, financial years, end-March stocks, and
Dadra and Nagar Haveli standing for the merged UT from 2020. Never used for real answers.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import duckdb

from bharat.contracts import load_source_contract
from bharat.ingest.bronze import LOAD_COLUMNS
from bharat.warehouse.prepare import _path, _write

FIXTURES: dict[str, list[dict]] = {
    "gst_state_monthly": [
        {
            "fy": "2026-27",
            "month": "2026-07-01",
            "state_code_src": "32",
            "state_name": "Kerala",
            "cgst": 600.0,
            "sgst": 700.0,
            "igst": 1200.0,
            "total": 2500.0,
        },
        {
            "fy": "2026-27",
            "month": "2026-08-01",
            "state_code_src": "32",
            "state_name": "Kerala",
            "cgst": 620.0,
            "sgst": 710.0,
            "igst": 1170.0,
            "total": 2500.0,
        },
        {
            "fy": "2026-27",
            "month": "2026-07-01",
            "state_code_src": "30",
            "state_name": "Goa",
            "cgst": 100.0,
            "sgst": 120.0,
            "igst": 180.0,
            "total": 400.0,
        },
    ],
    "rbi_state_annual": [
        {
            "dataset": "gsdp_current",
            "unit": "₹ lakh",
            "period": "2023-24",
            "period_type": "fy",
            "state_name": "Kerala",
            "value": 120000000.0,
        },
        {
            "dataset": "gsdp_current",
            "unit": "₹ lakh",
            "period": "2023-24",
            "period_type": "fy",
            "state_name": "Goa",
            "value": 10000000.0,
        },
        {
            "dataset": "scb_deposits",
            "unit": "₹ crore",
            "period": "2025-03-31",
            "period_type": "end_march",
            "state_name": "Kerala",
            "value": 900000.0,
        },
        {
            "dataset": "scb_deposits",
            "unit": "₹ crore",
            "period": "2025-03-31",
            "period_type": "end_march",
            "state_name": "Goa",
            "value": 100000.0,
        },
        {
            "dataset": "scb_deposits",
            "unit": "₹ crore",
            "period": "2025-03-31",
            "period_type": "end_march",
            "state_name": "ALL INDIA",
            "value": 1000000.0,
        },
        {
            "dataset": "scb_deposits",
            "unit": "₹ crore",
            "period": "2021-03-31",
            "period_type": "end_march",
            "state_name": "Dadra & Nagar Haveli",
            "value": 5000.0,
        },
        {
            "dataset": "scb_deposits",
            "unit": "₹ crore",
            "period": "2021-03-31",
            "period_type": "end_march",
            "state_name": "ALL INDIA",
            "value": 5000.0,
        },
    ],
    "population_projection": [
        {
            "year": 2025,
            "state_name": "India",
            "name_as_printed": "INDIA",
            "persons_thousand": 1000,
            "male_thousand": 510,
            "female_thousand": 490,
        },
        {
            "year": 2025,
            "state_name": "KERALA",
            "name_as_printed": "KERALA",
            "persons_thousand": 600,
            "male_thousand": 300,
            "female_thousand": 300,
        },
        {
            "year": 2025,
            "state_name": "GOA",
            "name_as_printed": "GOA",
            "persons_thousand": 400,
            "male_thousand": 210,
            "female_thousand": 190,
        },
    ],
    "trai_wireless_lsa": [
        {
            "as_of": "2026-09-30",
            "service_area": "Delhi",
            "name_as_printed": "Delhi",
            "wireless_subscribers": 79000000,
        },
        {
            "as_of": "2026-09-30",
            "service_area": "Mumbai",
            "name_as_printed": "Mumbai",
            "wireless_subscribers": 41000000,
        },
    ],
}


def write_fixtures(bronze: Path) -> list[Path]:
    retrieved = datetime.now(UTC).replace(tzinfo=None)
    paths = []
    con = duckdb.connect()
    try:
        for table, records in FIXTURES.items():
            contract = load_source_contract(table)
            columns = {name: rule.type for name, rule in contract.columns.items()}
            rows = [
                tuple(record.get(name) for name in columns) + ("fixture", retrieved)
                for record in records
            ]
            path = _path(bronze, table)
            _write(con, table, {**columns, **LOAD_COLUMNS}, rows, path)
            paths.append(path)
    finally:
        con.close()
    return paths
