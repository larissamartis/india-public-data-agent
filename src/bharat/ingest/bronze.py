"""Write a source's rows to a bronze Parquet file, but only if they keep their contract."""

from __future__ import annotations

import json
import logging
import tempfile
from datetime import UTC, date, datetime
from pathlib import Path

import duckdb

from bharat.contracts import Contract, enforce_contract

log = logging.getLogger(__name__)

LOAD_COLUMNS = {"_source_ref": "VARCHAR", "_retrieved_at": "TIMESTAMP"}


def _sql_text(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def save_bronze(
    rows: list[dict],
    columns: dict[str, str],
    contract: Contract,
    out_dir: Path,
    *,
    previous_row_count: int | None = None,
    today: date | None = None,
) -> Path:
    """Load rows with fixed column types, check the contract, then write Parquet.

    Each row must carry `_source_ref` (the file or API call it came from); `_retrieved_at`
    is added here. Raises ContractError, and writes nothing, if any rule is broken.
    """
    retrieved_at = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
    all_columns = {**columns, **LOAD_COLUMNS}
    table = contract.table
    out_path = out_dir / "bronze" / f"{table}.parquet"

    con = duckdb.connect()
    try:
        definition = ", ".join(f'"{name}" {kind}' for name, kind in all_columns.items())
        con.execute(f'create table "{table}" ({definition})')
        if rows:
            with tempfile.TemporaryDirectory() as tmp:
                ndjson = Path(tmp) / "rows.ndjson"
                with ndjson.open("w", encoding="utf-8") as handle:
                    for row in rows:
                        record = {name: row.get(name) for name in all_columns}
                        record["_retrieved_at"] = retrieved_at
                        handle.write(json.dumps(record, default=str) + "\n")
                spec = (
                    "{"
                    + ", ".join(f"{_sql_text(n)}: {_sql_text(k)}" for n, k in all_columns.items())
                    + "}"
                )
                con.execute(
                    f'insert into "{table}" select * from read_json('
                    f"{_sql_text(ndjson.as_posix())}, format = 'newline_delimited', "
                    f"columns = {spec})"
                )
        enforce_contract(con, contract, previous_row_count=previous_row_count, today=today)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        con.execute(f'copy "{table}" to {_sql_text(out_path.as_posix())} (format parquet)')
    finally:
        con.close()
    log.info("wrote %s rows to %s", len(rows), out_path)
    return out_path
