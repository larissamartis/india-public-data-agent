"""RBI Handbook of Statistics on Indian States: tables with states as rows and years as columns.

RBI serves a CAPTCHA, so each table's XLSX is downloaded by hand and listed in the manifest
with a `dataset` name (for example `gsdp_current`) and the `unit` printed on the table.

The parser looks for the first row holding two or more financial-year labels (`2011-12`),
takes the column to their left that names the most states as the state column, and unpivots.
Rows with no numbers (titles, notes, sources) are skipped. A table whose years repeat across
columns (several measures side by side) is refused: it needs its own parser.
"""

from __future__ import annotations

import logging
import re
from io import BytesIO
from pathlib import Path

import httpx
import openpyxl

from bharat.contracts import load_source_contract
from bharat.ingest.bronze import save_bronze
from bharat.ingest.common import to_float
from bharat.ingest.manual import entries_for, fetch_files
from bharat.reference.states import UnknownStateError, normalise_name, resolve_state

log = logging.getLogger(__name__)

SOURCE = "rbi"
COLUMNS = {
    "dataset": "VARCHAR",
    "unit": "VARCHAR",
    "fy": "VARCHAR",
    "state_name": "VARCHAR",
    "value": "DOUBLE",
}
_FY = re.compile(r"\b(\d{4})\s*[-–/]\s*(\d{2})\b")
_FOOTNOTE_MARKS = "*#@$†^ "


class RbiFormatError(ValueError):
    pass


def fy_label(value: object) -> str | None:
    """'2011-12', '2011 - 12 (P)' -> '2011-12'; anything else, including dates, -> None."""
    if value is None or isinstance(value, int | float):
        return None
    match = _FY.search(str(value))
    if not match or int(match[2]) != (int(match[1]) + 1) % 100:
        return None
    return f"{match[1]}-{match[2]}"


def _is_place(value: object) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    name = value.strip(_FOOTNOTE_MARKS)
    if normalise_name(name) == "all india":
        return True
    try:
        resolve_state(name)
    except UnknownStateError:
        return False
    return True


def _cell(row: tuple, index: int) -> object:
    return row[index] if index < len(row) else None


def _find_year_header(rows: list[tuple]) -> tuple[int, dict[int, str]]:
    for index, row in enumerate(rows):
        year_cols = {i: fy for i, v in enumerate(row) if (fy := fy_label(v))}
        if len(year_cols) >= 2:
            return index, year_cols
    raise RbiFormatError("no header row with two or more year labels such as 2011-12")


def parse_state_by_year(content: bytes) -> list[dict]:
    """Rows of {state_name, fy, value} from the first sheet of a state-by-year table."""
    book = openpyxl.load_workbook(BytesIO(content), read_only=True, data_only=True)
    rows = [tuple(row) for row in book.worksheets[0].iter_rows(values_only=True)]

    header_index, year_cols = _find_year_header(rows)

    labels = list(year_cols.values())
    repeated = sorted({fy for fy in labels if labels.count(fy) > 1})
    if repeated:
        raise RbiFormatError(f"years {repeated} appear in more than one column")

    body = rows[header_index + 1 :]
    first_year_col = min(year_cols)
    scores = {col: sum(_is_place(_cell(row, col)) for row in body) for col in range(first_year_col)}
    if not scores or max(scores.values()) == 0:
        raise RbiFormatError("no column to the left of the years names any state")
    name_col = max(scores, key=scores.get)

    records = []
    for row in body:
        name = _cell(row, name_col)
        if not isinstance(name, str) or not name.strip():
            continue
        values = {fy: to_float(_cell(row, col)) for col, fy in year_cols.items()}
        if all(v is None for v in values.values()):
            continue
        state_name = " ".join(name.strip(_FOOTNOTE_MARKS).split())
        for fy, value in values.items():
            if value is not None:
                records.append({"state_name": state_name, "fy": fy, "value": value})
    if not records:
        raise RbiFormatError("the table has year columns but no numbers under them")
    return records


def run(out_dir: Path, *, client: httpx.Client | None = None) -> list[Path]:
    """Fetch and check every RBI file in the manifest, parse each, write one bronze table."""
    entries = entries_for(SOURCE)
    paths = fetch_files(entries, out_dir / "raw" / "manual" / SOURCE, client=client)
    rows: list[dict] = []
    for entry, path in zip(entries, paths, strict=True):
        if not entry.dataset or not entry.unit:
            raise RbiFormatError(f"{entry.name}: the manifest needs `dataset` and `unit`")
        try:
            records = parse_state_by_year(path.read_bytes())
        except RbiFormatError as error:
            raise RbiFormatError(f"{entry.name}: {error}") from error
        log.info("%s (%s): %s rows", entry.name, entry.dataset, len(records))
        ref = f"{entry.original_url}#sha256={entry.sha256}"
        for record in records:
            record.update(dataset=entry.dataset, unit=entry.unit, _source_ref=ref)
        rows.extend(records)
    return [save_bronze(rows, COLUMNS, load_source_contract("rbi_state_annual"), out_dir)]
