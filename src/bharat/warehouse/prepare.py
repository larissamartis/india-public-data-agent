"""Get the bronze folder ready for dbt.

- Every source dbt reads must exist, so a source that has not been loaded yet gets an empty
  file with its contract's columns. The warehouse then simply has no rows for it, and the
  coverage table shows that.
- State names are matched here, in Python, with the same rules every loader's contract used,
  so SQL never re-implements name matching. `ref_state_name` maps each name exactly as printed
  to its LGD code (0 for India / All India); `ref_state` is the official list.
"""

from __future__ import annotations

import logging
from pathlib import Path

import duckdb

from bharat.contracts import load_source_contract
from bharat.ingest.bronze import LOAD_COLUMNS
from bharat.reference.states import load_states, normalise_name, resolve_state

log = logging.getLogger(__name__)

# Every bronze table the warehouse reads, by contract name.
BRONZE_TABLES = (
    "gst_state_monthly",
    "gst_other_monthly",
    "rbi_state_annual",
    "population_projection",
    "trai_wireless_lsa",
    "mospi_cpi",
    "mospi_plfs",
    "mospi_asi",
)
NATIONAL_CODE = 0


def _path(bronze: Path, table: str) -> Path:
    return bronze / f"{table}.parquet"


def _write(con: duckdb.DuckDBPyConnection, table: str, columns: dict[str, str], rows, path: Path):
    definition = ", ".join(f'"{name}" {kind}' for name, kind in columns.items())
    con.execute(f'create or replace table "{table}" ({definition})')
    if rows:
        marks = ", ".join("?" for _ in columns)
        con.executemany(f'insert into "{table}" values ({marks})', rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    con.execute(f"copy \"{table}\" to '{path.as_posix()}' (format parquet)")


def write_missing(bronze: Path) -> list[str]:
    """Write an empty file, with the contract's columns, for each table not loaded yet."""
    missing = []
    con = duckdb.connect()
    try:
        for table in BRONZE_TABLES:
            if _path(bronze, table).exists():
                continue
            contract = load_source_contract(table)
            columns = {name: rule.type for name, rule in contract.columns.items()}
            _write(con, table, {**columns, **LOAD_COLUMNS}, [], _path(bronze, table))
            missing.append(table)
    finally:
        con.close()
    for table in missing:
        log.warning("%s not loaded; using an empty table", table)
    return missing


def state_name_rows(bronze: Path) -> list[tuple[str, int]]:
    """(name as printed, LGD code) for every state name in every bronze file."""
    names: set[str] = set()
    exempt: set[str] = set()
    for table in BRONZE_TABLES:
        path = _path(bronze, table)
        if not path.exists():
            continue
        for column, rule in load_source_contract(table).columns.items():
            if not rule.state_name:
                continue
            exempt |= {normalise_name(n) for n in rule.allow_names}
            quoted = f'"{column}"'
            found = duckdb.sql(
                f"select distinct {quoted} from '{path.as_posix()}' where {quoted} is not null"
            ).fetchall()
            names |= {row[0] for row in found}
    rows = []
    for name in sorted(names):
        code = NATIONAL_CODE if normalise_name(name) in exempt else resolve_state(name).code
        rows.append((name, code))
    return rows


def prepare(bronze: Path) -> dict[str, int]:
    """Fill in missing tables and write the two reference files. Returns row counts."""
    missing = write_missing(bronze)
    states = [(s.code, s.name, s.kind, s.valid_from, s.valid_to) for s in load_states()] + [
        (NATIONAL_CODE, "India", "country", None, None)
    ]
    names = state_name_rows(bronze)
    con = duckdb.connect()
    try:
        _write(
            con,
            "ref_state",
            {
                "state_code": "INTEGER",
                "state_name": "VARCHAR",
                "kind": "VARCHAR",
                "valid_from": "DATE",
                "valid_to": "DATE",
            },
            states,
            _path(bronze, "ref_state"),
        )
        _write(
            con,
            "ref_state_name",
            {"name_as_printed": "VARCHAR", "state_code": "INTEGER"},
            names,
            _path(bronze, "ref_state_name"),
        )
    finally:
        con.close()
    return {"missing_tables": len(missing), "states": len(states), "names": len(names)}
