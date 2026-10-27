"""Projected population by state, 2011-2036, from the Technical Group's November 2019 report.

Table 11 ("Projected Total Population by Sex as on 1st July") runs over several PDF pages.
Each page shows three areas side by side, each with Persons, Male and Females columns in
thousands, and one row per year.

Reading the page as plain text is not safe: where one area's numbers sit slightly lower than
its neighbours', text extraction lists them after the neighbour's, which would swap two
states. So the parser works from word positions. The printed column-number row
(`1 2 3 ... 10`, or `1 11 12 ... 19` on later pages) gives each column's x position; every
number is placed in the nearest column and the nearest year row.

Checks: each year has all three numbers for every area, Persons = Male + Females (to within
rounding), and the states and UTs add up to India.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from statistics import median

import httpx

from bharat.contracts import load_source_contract
from bharat.ingest.bronze import save_bronze
from bharat.ingest.manual import entries_for, fetch_files

log = logging.getLogger(__name__)

SOURCE = "population"
COLUMNS = {
    "year": "INTEGER",
    "state_name": "VARCHAR",
    "name_as_printed": "VARCHAR",
    "persons_thousand": "BIGINT",
    "male_thousand": "BIGINT",
    "female_thousand": "BIGINT",
}
_TABLE_11 = re.compile(r"TABLE\s*[–-]\s*11\b")
_TITLE = "Total Population by Sex as on 1st July"
_YEAR = re.compile(r"20[1-3]\d")
_UT_MARK = re.compile(r"\(\s*UT\s*\)|\*", re.I)
ROUNDING = 2  # thousands; Persons may differ from Male + Females by rounding
TOTAL_TOLERANCE = 0.01


class PopulationFormatError(ValueError):
    pass


def _centre(word: dict) -> float:
    return (word["x0"] + word["x1"]) / 2


def _lines(words: list[dict], tolerance: float = 2.0) -> list[list[dict]]:
    lines: list[list[dict]] = []
    for word in sorted(words, key=lambda w: (w["top"], w["x0"])):
        if lines and abs(word["top"] - lines[-1][0]["top"]) <= tolerance:
            lines[-1].append(word)
        else:
            lines.append([word])
    return [sorted(line, key=lambda w: w["x0"]) for line in lines]


def _is_index_line(line: list[dict]) -> bool:
    """The printed column numbers: '1' for Year, then a run of consecutive numbers."""
    texts = [w["text"] for w in line]
    if len(texts) < 4 or texts[0] != "1" or not all(t.isdigit() for t in texts):
        return False
    rest = [int(t) for t in texts[1:]]
    return rest == list(range(rest[0], rest[0] + len(rest))) and len(rest) % 3 == 0


def _number(text: str) -> int | None:
    digits = text.replace(",", "")
    return int(digits) if digits.isdigit() else None


_MEASURE_WORDS = {"persons", "person", "male", "males", "females", "female"}
_TITLE_WORDS = {"table", "projected", "territories", "territories*", "union", "('000)", "(‘000)"}


def _texts(line: list[dict]) -> set[str]:
    return {w["text"].lower() for w in line}


def _nearest(value: float, options: list[float]) -> int:
    return min(range(len(options)), key=lambda i: abs(options[i] - value))


def clean_name(printed: str) -> str:
    name = " ".join(_UT_MARK.sub(" ", printed).split())
    return "India" if name.lower() == "india" else name


def parse_table_page(words: list[dict]) -> list[dict]:
    """Rows of {year, name_as_printed, state_name, persons/male/female} from one page."""
    lines = _lines(words)
    index = next((line for line in lines if _is_index_line(line)), None)
    if index is None:
        raise PopulationFormatError("no column-number row such as '1 2 3 ... 10'")
    year_x = _centre(index[0])
    col_x = [_centre(w) for w in index[1:]]
    groups = len(col_x) // 3
    group_x = [sum(col_x[3 * g : 3 * g + 3]) / 3 for g in range(groups)]

    # The Persons / Male / Females header row, and the last title line above it; area names
    # sit between the two. Titles wrap differently from page to page.
    persons = next((ln for ln in lines if _texts(ln) & _MEASURE_WORDS), None)
    if persons is None:
        raise PopulationFormatError("no 'Persons / Male / Females' header row")
    bottom = persons[0]["top"]
    titles = [ln for ln in lines if ln[0]["top"] < bottom and _texts(ln) & _TITLE_WORDS]
    if not titles:
        raise PopulationFormatError("no title line above the 'Persons' header")
    top = titles[-1][0]["top"]
    names: list[list[str]] = [[] for _ in range(groups)]
    for line in lines:
        if top < line[0]["top"] < bottom:
            for word in line:
                if word["text"].lower() != "year":
                    names[_nearest(_centre(word), group_x)].append(word["text"])
    printed = [" ".join(n) for n in names]
    if not all(printed):
        raise PopulationFormatError(f"could not read all {groups} area names: {printed}")

    below = [w for w in words if w["top"] > index[0]["bottom"]]
    years = sorted(
        (
            w
            for w in below
            if _YEAR.fullmatch(w["text"]) and abs(_centre(w) - year_x) < abs(_centre(w) - col_x[0])
        ),
        key=lambda w: w["top"],
    )
    if len(years) < 2:
        raise PopulationFormatError("fewer than two year rows")
    year_tops = [w["top"] for w in years]
    gap = median(b - a for a, b in zip(year_tops, year_tops[1:], strict=False))
    year_ids = {id(w) for w in years}

    values: dict[tuple[int, int], int] = {}
    for word in below:
        number = _number(word["text"])
        if id(word) in year_ids or number is None:
            continue
        row = _nearest(word["top"], year_tops)
        if abs(word["top"] - year_tops[row]) > 0.75 * gap:
            continue  # page number or footnote, not in any year row
        key = (row, _nearest(_centre(word), col_x))
        if key in values:
            raise PopulationFormatError(
                f"two numbers fall in year {years[row]['text']}, column {key[1] + 2}"
            )
        values[key] = number

    records = []
    for row, year_word in enumerate(years):
        for g in range(groups):
            triple = [values.get((row, 3 * g + i)) for i in range(3)]
            if None in triple:
                raise PopulationFormatError(f"{printed[g]} {year_word['text']}: missing numbers")
            total, male, female = triple
            if abs(total - male - female) > ROUNDING:
                raise PopulationFormatError(
                    f"{printed[g]} {year_word['text']}: persons {total} is not male {male} "
                    f"+ females {female}"
                )
            records.append(
                {
                    "year": int(year_word["text"]),
                    "name_as_printed": printed[g],
                    "state_name": clean_name(printed[g]),
                    "persons_thousand": total,
                    "male_thousand": male,
                    "female_thousand": female,
                }
            )
    return records


def check_totals(records: list[dict]) -> list[str]:
    """Years where the states and UTs do not add up to India within the tolerance."""
    problems = []
    for year in sorted({r["year"] for r in records}):
        rows = [r for r in records if r["year"] == year]
        india = [r["persons_thousand"] for r in rows if r["state_name"] == "India"]
        if not india:
            problems.append(f"{year}: no India row")
            continue
        states = sum(r["persons_thousand"] for r in rows if r["state_name"] != "India")
        gap = abs(states - india[0]) / india[0]
        if gap > TOTAL_TOLERANCE:
            problems.append(f"{year}: states add to {states:,}, India is {india[0]:,}")
    return problems


def _pdf_pages(path: Path) -> list[tuple[str, list[dict]]]:
    import pdfplumber

    with pdfplumber.open(path) as pdf:
        return [(page.extract_text() or "", page.extract_words()) for page in pdf.pages]


def parse_report(pages: list[tuple[str, list[dict]]]) -> list[dict]:
    records: list[dict] = []
    table_pages = 0
    for number, (text, words) in enumerate(pages, start=1):
        head = text[:400]
        if not (_TABLE_11.search(head) and _TITLE in " ".join(head.split())):
            continue
        table_pages += 1
        try:
            records.extend(parse_table_page(words))
        except PopulationFormatError as error:
            # Show the page's opening lines so a layout change can be fixed without a rerun.
            opening = " | ".join(line.strip() for line in text.splitlines()[:8])
            raise PopulationFormatError(
                f"page {number}: {error}. Page starts: {opening}"
            ) from error
    if not table_pages:
        raise PopulationFormatError("no Table 11 pages found")
    seen: set[tuple[str, int]] = set()
    for record in records:
        key = (record["state_name"], record["year"])
        if key in seen:
            raise PopulationFormatError(f"{key[0]} {key[1]} appears on two pages")
        seen.add(key)
    problems = check_totals(records)
    if problems:
        raise PopulationFormatError("totals do not match India: " + "; ".join(problems[:5]))
    log.info("Table 11: %s pages, %s rows", table_pages, len(records))
    return records


def run(out_dir: Path, *, client: httpx.Client | None = None) -> list[Path]:
    entries = entries_for(SOURCE)
    paths = fetch_files(entries, out_dir / "raw" / "manual" / SOURCE, client=client)
    rows: list[dict] = []
    for entry, path in zip(entries, paths, strict=True):
        records = parse_report(_pdf_pages(path))
        ref = f"{entry.original_url}#sha256={entry.sha256}"
        for record in records:
            record["_source_ref"] = ref
        rows.extend(records)
    return [save_bronze(rows, COLUMNS, load_source_contract("population_projection"), out_dir)]
