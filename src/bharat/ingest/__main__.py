"""Run one source's ingest: `python -m bharat.ingest gst` (or mospi-cpi, mospi-plfs, mospi-asi).

On GitHub Actions it also writes short notices (row counts, periods, any contract failure)
that show on the run page.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

import duckdb

from bharat.contracts import ContractError
from bharat.ingest import gst, mospi

SOURCES = {
    "gst": lambda out: gst.run(out),
    "mospi-cpi": lambda out: [mospi.run("mospi_cpi", out)],
    "mospi-plfs": lambda out: [mospi.run("mospi_plfs", out)],
    "mospi-asi": lambda out: [mospi.run("mospi_asi", out)],
}


def _annotate(level: str, title: str, message: str) -> None:
    if os.environ.get("GITHUB_ACTIONS") == "true":
        text = message.replace("%", "%25").replace("\r", "").replace("\n", "%0A")
        print(f"::{level} title={title}::{text}", flush=True)


def _summarise(path: Path) -> str:
    rel = f"'{path.as_posix()}'"
    count = duckdb.sql(f"select count(*) from {rel}").fetchone()[0]
    columns = [c[0] for c in duckdb.sql(f"describe select * from {rel}").fetchall()]
    parts = [f"{path.name}: {count} rows"]
    for column in ("state", "state_name"):
        if column in columns:
            names = duckdb.sql(f"select count(distinct {column}) from {rel}").fetchone()[0]
            parts.append(f"{names} distinct {column}")
    for column in ("month", "year"):
        if column in columns:
            low, high = duckdb.sql(f"select min({column}), max({column}) from {rel}").fetchone()
            parts.append(f"{column} {low} to {high}")
    return "; ".join(parts)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m bharat.ingest")
    parser.add_argument("source", choices=sorted(SOURCES))
    parser.add_argument("--out", type=Path, default=Path("data"))
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    try:
        paths = SOURCES[args.source](args.out)
    except ContractError as error:
        _annotate("error", f"{args.source} contract", str(error))
        print(error, file=sys.stderr)
        return 1
    except Exception as error:
        _annotate("error", f"{args.source} failed", f"{type(error).__name__}: {error}")
        raise
    for path in paths:
        summary = _summarise(path)
        print(summary)
        _annotate("notice", f"{args.source} loaded", summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
