"""Run one source's ingest: `python -m bharat.ingest gst` (or mospi-cpi, rbi, npci and so on).

Hand-downloaded sources (rbi, npci, trai, nfhs, population) can also be previewed with
`--inspect`, which shows the first rows of each file instead of loading them.

On GitHub Actions it also writes short notices (row counts, periods, any contract failure,
previews) that show on the run page.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

import duckdb

from bharat.contracts import ContractError
from bharat.ingest import gst, manual, mospi, rbi

SOURCES = {
    "gst": lambda out: gst.run(out),
    "mospi-cpi": lambda out: [mospi.run("mospi_cpi", out)],
    "mospi-plfs": lambda out: [mospi.run("mospi_plfs", out)],
    "mospi-asi": lambda out: [mospi.run("mospi_asi", out)],
    "rbi": lambda out: rbi.run(out),
}
# Hand-downloaded sources. Those without a parser yet can only be inspected.
MANUAL_SOURCES = ("rbi", "npci", "trai", "nfhs", "population")


def _inspect(source: str, out: Path) -> list[str]:
    entries = manual.entries_for(source)
    paths = manual.fetch_files(entries, out / "raw" / "manual" / source)
    return [manual.inspect_file(path) for path in paths]


def _annotate(level: str, title: str, message: str) -> None:
    if os.environ.get("GITHUB_ACTIONS") == "true":
        text = message.replace("%", "%25").replace("\r", "").replace("\n", "%0A")
        print(f"::{level} title={title}::{text}", flush=True)


def _summarise(path: Path) -> str:
    rel = f"'{path.as_posix()}'"
    count = duckdb.sql(f"select count(*) from {rel}").fetchall()[0][0]
    columns = [c[0] for c in duckdb.sql(f"describe select * from {rel}").fetchall()]
    parts = [f"{path.name}: {count} rows"]
    for column in ("state", "state_name"):
        if column in columns:
            names = duckdb.sql(f"select count(distinct {column}) from {rel}").fetchall()[0][0]
            parts.append(f"{names} distinct {column}")
    for column in ("month", "year"):
        if column in columns:
            low, high = duckdb.sql(f"select min({column}), max({column}) from {rel}").fetchall()[0]
            parts.append(f"{column} {low} to {high}")
    return "; ".join(parts)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m bharat.ingest")
    parser.add_argument("source", choices=sorted({*SOURCES, *MANUAL_SOURCES}))
    parser.add_argument("--out", type=Path, default=Path("data"))
    parser.add_argument("--inspect", action="store_true", help="preview hand-downloaded files")
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    if args.inspect or args.source not in SOURCES:
        if args.source not in MANUAL_SOURCES:
            parser.error(f"--inspect is for hand-downloaded sources: {', '.join(MANUAL_SOURCES)}")
        if not args.inspect:
            print(f"{args.source} has no parser yet; previewing its files instead")
        try:
            previews = _inspect(args.source, args.out)
        except manual.ManualFileError as error:
            _annotate("error", f"{args.source} files", str(error))
            print(error, file=sys.stderr)
            return 1
        for preview in previews:
            print(preview)
            _annotate("notice", f"{args.source} preview", preview)
        return 0
    try:
        paths = SOURCES[args.source](args.out)
    except (ContractError, manual.ManualFileError) as error:
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
