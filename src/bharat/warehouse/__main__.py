"""Warehouse helpers: `python -m bharat.warehouse prepare|fixtures|report|summary`.

- prepare: fill in sources not loaded yet and write the state reference files for dbt.
- fixtures: write the tiny made-up bronze folder CI builds on.
- report: turn dbt's run_results.json into notices on the GitHub run page, so failures can be
  read without signing in to see the log.
- summary: row counts and coverage from the built serving database.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

import duckdb

from bharat.warehouse.fixtures import write_fixtures
from bharat.warehouse.prepare import prepare

MARTS = (
    "fct_state_metric",
    "fct_national_metric",
    "fct_lsa_metric",
    "dim_state",
    "dim_metric",
    "dim_source",
    "dim_period",
    "coverage",
    "revisions",
)


def _annotate(level: str, title: str, message: str) -> None:
    if os.environ.get("GITHUB_ACTIONS") == "true":
        text = message.replace("%", "%25").replace("\r", "").replace("\n", "%0A")
        print(f"::{level} title={title}::{text}", flush=True)


def report(run_results: Path, log: Path = Path("dbt/logs/dbt.log")) -> int:
    """Post every failed or erroring dbt node; return 1 if there was any.

    When dbt stopped before running anything (a parse or compilation error, for example in
    a metric definition), there are no results, so the error lines from dbt's log are posted.
    """
    if not run_results.exists():
        lines = (
            log.read_text(encoding="utf-8", errors="replace").splitlines() if log.exists() else []
        )
        start = next((i for i, line in enumerate(lines) if "Error" in line), None)
        detail = "\n".join(lines[start : start + 25]) if start is not None else "no dbt log"
        _annotate("error", "dbt did not run", detail[:3000])
        print(detail)
        return 1
    results = json.loads(run_results.read_text(encoding="utf-8"))["results"]
    bad = [r for r in results if r["status"] in {"error", "fail", "runtime error"}]
    warned = [r for r in results if r["status"] == "warn"]
    for result in bad + warned:
        level = "warning" if result["status"] == "warn" else "error"
        message = (result.get("message") or "").strip()[:3000]
        _annotate(level, f"dbt {result['status']}: {result['unique_id']}", message or "no message")
    passed = len(results) - len(bad) - len(warned)
    _annotate(
        "notice" if not bad else "error",
        "dbt build",
        f"{passed} passed, {len(warned)} warned, {len(bad)} failed",
    )
    print(f"dbt: {passed} passed, {len(warned)} warned, {len(bad)} failed")
    return 1 if bad else 0


def summary(database: Path) -> str:
    con = duckdb.connect(str(database), read_only=True)
    try:
        lines = []
        for table in MARTS:
            count = con.execute(f"select count(*) from {table}").fetchall()[0][0]
            lines.append(f"{table}: {count:,} rows")
        coverage = con.execute(
            """
            select metric_id, count(distinct state_code) as states,
                   min(first_period) as first_period, max(last_period) as last_period
            from coverage group by metric_id order by metric_id
            """
        ).fetchall()
        lines.append("coverage (metric: states, first to last period):")
        lines += [f"  {m}: {s} states, {a} to {b}" for m, s, a, b in coverage]
        return "\n".join(lines)
    finally:
        con.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m bharat.warehouse")
    parser.add_argument("command", choices=["prepare", "fixtures", "report", "summary"])
    parser.add_argument("--bronze", type=Path, default=Path("data/bronze"))
    parser.add_argument("--run-results", type=Path, default=Path("dbt/target/run_results.json"))
    parser.add_argument("--database", type=Path, default=Path("data/serving/serving.duckdb"))
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    if args.command == "fixtures":
        paths = write_fixtures(args.bronze)
        print(f"wrote {len(paths)} fixture tables to {args.bronze}")
    elif args.command == "prepare":
        counts = prepare(args.bronze, args.database)
        print(f"prepared {args.bronze}: {counts}")
    elif args.command == "report":
        return report(args.run_results)
    else:
        text = summary(args.database)
        print(text)
        _annotate("notice", "warehouse", text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
