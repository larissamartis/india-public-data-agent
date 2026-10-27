"""TRAI monthly telecom subscription report: wireless (mobile) subscribers by service area.

Annexure-II of the monthly press release lists, for each of the 22 licensed service areas
(LSAs), every operator's subscribers for the previous and the current month, then the total
for both months and the net addition. Operators with no service in an area leave blank cells,
so the parser reads only the last three numbers on each row (total last month, total this
month, net addition) and checks that the third is the difference of the first two. The LSA
rows must also add up to the report's Total row.

LSAs are not states: several cover more than one state (Bihar includes Jharkhand, for
example) and Delhi, Mumbai and Kolkata are metro areas. They are stored as service areas;
any mapping to states happens in the warehouse, with that caveat attached.
"""

from __future__ import annotations

import calendar
import logging
import re
from datetime import date
from pathlib import Path

import httpx

from bharat.contracts import load_source_contract
from bharat.ingest.bronze import save_bronze
from bharat.ingest.manual import entries_for, fetch_files

log = logging.getLogger(__name__)

SOURCE = "trai"
COLUMNS = {
    "as_of": "DATE",
    "service_area": "VARCHAR",
    "name_as_printed": "VARCHAR",
    "wireless_subscribers": "BIGINT",
}
# The 22 licensed service areas and the spellings seen in TRAI reports.
SERVICE_AREAS = {
    "Andhra Pradesh": [],
    "Assam": [],
    "Bihar": [],
    "Delhi": [],
    "Gujarat": [],
    "Haryana": [],
    "Himachal Pradesh": [],
    "Jammu & Kashmir": ["J & K", "J&K"],
    "Karnataka": [],
    "Kerala": [],
    "Kolkata": [],
    "Madhya Pradesh": [],
    "Maharashtra": [],
    "Mumbai": [],
    "North East": [],
    "Odisha": ["Orissa"],
    "Punjab": [],
    "Rajasthan": [],
    "Tamil Nadu": [],
    "UP (East)": ["U.P. (E)", "U.P.(E)", "Uttar Pradesh (East)", "UP East"],
    "UP (West)": ["U.P. (W)", "U.P.(W)", "Uttar Pradesh (West)", "UP West"],
    "West Bengal": [],
}
_MONTHS = {name.lower(): i for i, name in enumerate(calendar.month_abbr) if name} | {"sept": 9}
_MONTH_LABEL = re.compile(r"\b([A-Za-z]{3,4})-(\d{2})\b")
_NUMBER = re.compile(r"\(\s*[\d,]+\s*\)|\d[\d,]*")
# The name ends where the first number starts; "(W)" in "U.P. (W)" is not a number.
_ROW = re.compile(r"^([A-Za-z][A-Za-z .&()]*?)\s+(?=\d|\(\s*\d)")


class TraiFormatError(ValueError):
    pass


def _key(name: str) -> str:
    return re.sub(r"[^a-z]", "", name.lower().replace("&", "and"))


_LOOKUP = {
    _key(alias): area for area, aliases in SERVICE_AREAS.items() for alias in [area, *aliases]
}


def service_area(name: str) -> str | None:
    return _LOOKUP.get(_key(name))


def _value(text: str) -> int:
    digits = int(re.sub(r"[^\d]", "", text))
    return -digits if text.startswith("(") else digits


def month_end(label: str) -> date:
    """'Sept-26' -> 2026-09-30."""
    match = _MONTH_LABEL.fullmatch(label.strip())
    month = _MONTHS.get(match[1].lower()) if match else None
    if not month:
        raise TraiFormatError(f"not a month label: {label!r}")
    year = 2000 + int(match[2])
    return date(year, month, calendar.monthrange(year, month)[1])


def parse_annexure_ii(text: str) -> list[dict]:
    """Rows of {as_of, service_area, name_as_printed, wireless_subscribers} for both months."""
    lines = [" ".join(line.split()) for line in text.splitlines()]
    labels: list[str] = []
    for line in lines:
        found = _MONTH_LABEL.findall(line)
        if len(found) >= 2 and all(m.lower() in _MONTHS for m, _ in found):
            labels = list(dict.fromkeys(f"{m}-{y}" for m, y in found))
            break
    if len(labels) != 2:
        raise TraiFormatError(f"expected two month labels in the header, found {labels}")
    previous, current = (month_end(label) for label in labels)

    records: list[dict] = []
    totals: tuple[int, int] | None = None
    for line in lines:
        match = _ROW.match(line)
        if not match:
            continue
        name = match[1].strip()
        numbers = [_value(n) for n in _NUMBER.findall(line[len(name) :])]
        if len(numbers) < 3:
            continue
        before, after, net = numbers[-3:]
        if after - before != net:
            raise TraiFormatError(f"{name}: {after:,} - {before:,} is not the net addition {net:,}")
        if _key(name) == "total":
            totals = (before, after)
            break
        area = service_area(name)
        if area is None:
            raise TraiFormatError(f"unknown service area {name!r}")
        for as_of, value in ((previous, before), (current, after)):
            records.append(
                {
                    "as_of": as_of,
                    "service_area": area,
                    "name_as_printed": name,
                    "wireless_subscribers": value,
                }
            )

    areas = {r["service_area"] for r in records}
    if len(areas) != len(SERVICE_AREAS) or len(records) != 2 * len(SERVICE_AREAS):
        missing = sorted(set(SERVICE_AREAS) - areas)
        raise TraiFormatError(f"expected each of 22 service areas once; missing {missing}")
    if totals is None:
        raise TraiFormatError("no Total row")
    for as_of, total in zip((previous, current), totals, strict=True):
        added = sum(r["wireless_subscribers"] for r in records if r["as_of"] == as_of)
        if added != total:
            raise TraiFormatError(f"{as_of}: service areas add to {added:,}, Total is {total:,}")
    return records


def _pdf_texts(path: Path) -> list[str]:
    import pdfplumber

    with pdfplumber.open(path) as pdf:
        return [page.extract_text() or "" for page in pdf.pages]


def find_annexure_ii(pages: list[str]) -> str:
    for text in pages:
        flat = " ".join(text.split())
        if re.search(r"Annexure[\s-]*II\b", flat) and "Wireless (Mobile) Subscriber Base" in flat:
            return text
    raise TraiFormatError("no 'Wireless (Mobile) Subscriber Base Annexure-II' page")


def run(out_dir: Path, *, client: httpx.Client | None = None) -> list[Path]:
    entries = entries_for(SOURCE)
    paths = fetch_files(entries, out_dir / "raw" / "manual" / SOURCE, client=client)
    rows: list[dict] = []
    for entry, path in zip(entries, paths, strict=True):
        try:
            records = parse_annexure_ii(find_annexure_ii(_pdf_texts(path)))
        except TraiFormatError as error:
            raise TraiFormatError(f"{entry.name}: {error}") from error
        ref = f"{entry.original_url}#sha256={entry.sha256}"
        for record in records:
            record["_source_ref"] = ref
        rows.extend(records)
    seen: dict[tuple[str, date], int] = {}
    unique = []
    for row in rows:  # consecutive reports both carry the month they share
        key = (row["service_area"], row["as_of"])
        if key in seen:
            if seen[key] != row["wireless_subscribers"]:
                log.warning(
                    "%s %s revised from %s to %s", *key, seen[key], row["wireless_subscribers"]
                )
            continue
        seen[key] = row["wireless_subscribers"]
        unique.append(row)
    return [save_bronze(unique, COLUMNS, load_source_contract("trai_wireless_lsa"), out_dir)]
