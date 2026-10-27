"""RBI Handbook of Statistics on Indian States: tables with states as rows and periods as columns.

RBI serves a CAPTCHA, so each table's XLSX is downloaded by hand and listed in the manifest
with a `dataset` name (for example `gsdp_current`) and the `unit` printed on the table.

Layouts seen in the 2024-25 edition (Dec 2025):
- Tables are split across sheets, `T_19(i)` and `T_19(ii)`, each with its own header row.
- Income tables label columns with financial years (`2011-12`): a flow over the year.
- Banking tables label columns with bare years (`2025`) under the note "As at end-March":
  a stock on 31 March of that year. Bare years without that note are refused.
- Banking tables put region subtotals (`NORTHERN REGION`) among the states; they are skipped.

On each sheet the parser finds the first row with two or more period labels, takes the
column to their left that names the most states, and unpivots. Rows with no numbers (notes,
sources) are skipped. A period that appears twice for the same state is refused.
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
    "period": "VARCHAR",
    "period_type": "VARCHAR",
    "state_name": "VARCHAR",
    "value": "DOUBLE",
}
FY = "fy"
END_MARCH = "end_march"
_FY = re.compile(r"\b(\d{4})\s*[-–/]\s*(\d{2})\b")
_YEAR = re.compile(r"^(19|20)\d{2}$")
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


def year_label(value: object) -> str | None:
    """2025, 2025.0 or '2025' -> '2025'; anything else -> None."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, float):
        if not value.is_integer():
            return None
        value = int(value)
    text = str(value).strip()
    return text if _YEAR.match(text) else None


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


def _is_region(name: str) -> bool:
    return normalise_name(name).endswith(" region")


def _cell(row: tuple, index: int) -> object:
    return row[index] if index < len(row) else None


def _find_header(rows: list[tuple]) -> tuple[int, dict[int, str], str]:
    """Index of the header row, its period columns and their type."""
    for index, row in enumerate(rows):
        years = {i: fy for i, v in enumerate(row) if (fy := fy_label(v))}
        if len(years) >= 2:
            return index, years, FY
        bare = {i: y for i, v in enumerate(row) if (y := year_label(v))}
        if len(bare) >= 2:
            above = " ".join(str(v) for r in rows[:index] for v in r if isinstance(v, str))
            if "end-march" not in above.lower().replace(" ", ""):
                raise RbiFormatError(
                    "columns are bare years but the table does not say 'As at end-March'"
                )
            return index, {i: f"{y}-03-31" for i, y in bare.items()}, END_MARCH
    raise RbiFormatError("no header row with two or more periods such as 2011-12 or 2025")


def _parse_sheet(rows: list[tuple]) -> list[dict]:
    header_index, period_cols, period_type = _find_header(rows)
    labels = list(period_cols.values())
    repeated = sorted({p for p in labels if labels.count(p) > 1})
    if repeated:
        raise RbiFormatError(f"periods {repeated} appear in more than one column")

    body = rows[header_index + 1 :]
    first = min(period_cols)
    scores = {col: sum(_is_place(_cell(row, col)) for row in body) for col in range(first)}
    if not scores or max(scores.values()) == 0:
        raise RbiFormatError("no column to the left of the periods names any state")
    name_col = max(scores, key=scores.get)

    records = []
    for row in body:
        name = _cell(row, name_col)
        if not isinstance(name, str) or not name.strip() or _is_region(name):
            continue
        values = {p: to_float(_cell(row, col)) for col, p in period_cols.items()}
        if all(v is None for v in values.values()):
            continue
        state_name = " ".join(name.strip(_FOOTNOTE_MARKS).split())
        for period, value in values.items():
            if value is not None:
                records.append(
                    {
                        "state_name": state_name,
                        "period": period,
                        "period_type": period_type,
                        "value": value,
                    }
                )
    return records


def parse_state_by_period(content: bytes) -> list[dict]:
    """Rows of {state_name, period, period_type, value} from every sheet of a table."""
    book = openpyxl.load_workbook(BytesIO(content), read_only=True, data_only=True)
    records: list[dict] = []
    for sheet in book.worksheets:
        rows = [tuple(row) for row in sheet.iter_rows(values_only=True)]
        try:
            records.extend(_parse_sheet(rows))
        except RbiFormatError as error:
            raise RbiFormatError(f"sheet {sheet.title}: {error}") from error
    if not records:
        raise RbiFormatError("the table has period columns but no numbers under them")
    if len({r["period_type"] for r in records}) > 1:
        raise RbiFormatError("sheets mix financial years and end-March years")
    seen: set[tuple[str, str]] = set()
    for record in records:
        key = (record["state_name"], record["period"])
        if key in seen:
            raise RbiFormatError(f"{key[0]} {key[1]} appears more than once")
        seen.add(key)
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
            records = parse_state_by_period(path.read_bytes())
        except RbiFormatError as error:
            raise RbiFormatError(f"{entry.name}: {error}") from error
        log.info("%s (%s): %s rows", entry.name, entry.dataset, len(records))
        ref = f"{entry.original_url}#sha256={entry.sha256}"
        for record in records:
            record.update(dataset=entry.dataset, unit=entry.unit, _source_ref=ref)
        rows.extend(records)
    return [save_bronze(rows, COLUMNS, load_source_contract("rbi_state_annual"), out_dir)]
