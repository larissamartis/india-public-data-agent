"""Check LLM-written SQL before it runs.

The LLM can be wrong or be talked into writing something harmful, so this is plain code it
cannot argue with: one read-only SELECT, only the warehouse tables we allow, no functions that
read files or the network, and a row cap. The DuckDB connection is also opened read-only with
external access switched off, so this is the first of two locks, not the only one.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError, TokenError

DEFAULT_ROW_CAP = 1000

# Statement types that must never appear, looked up by name because sqlglot renames some
# classes between versions (AlterTable became Alter, for example).
_BLOCKED_NODES = tuple(
    getattr(exp, name)
    for name in (
        "Command",
        "Insert",
        "Update",
        "Delete",
        "Merge",
        "Create",
        "Drop",
        "Alter",
        "AlterTable",
        "Copy",
        "Attach",
        "Detach",
        "Pragma",
        "Set",
        "Use",
    )
    if hasattr(exp, name)
)

# Functions that can read files, URLs or settings, or change the session.
BLOCKED_FUNCTIONS = frozenset(
    {
        "read_csv",
        "read_csv_auto",
        "read_parquet",
        "parquet_scan",
        "read_json",
        "read_json_auto",
        "read_ndjson",
        "read_text",
        "read_blob",
        "read_xlsx",
        "glob",
        "sniff_csv",
        "query",
        "query_table",
        "getenv",
        "current_setting",
        "duckdb_settings",
        "duckdb_secrets",
        "duckdb_extensions",
        "sqlite_scan",
        "postgres_scan",
        "iceberg_scan",
        "delta_scan",
    }
)


@dataclass(frozen=True)
class GuardResult:
    ok: bool
    sql: str | None = None
    tables: tuple[str, ...] = ()
    errors: tuple[str, ...] = field(default_factory=tuple)


def _function_name(node: exp.Func) -> str:
    if isinstance(node, exp.Anonymous):
        return str(node.this).lower()
    return node.sql_name().lower()


def _cap_rows(tree: exp.Query, row_cap: int) -> exp.Query:
    if isinstance(tree, exp.Select):
        limit = tree.args.get("limit")
        current = limit.expression if limit is not None else None
        if isinstance(current, exp.Literal) and current.is_int and int(current.this) <= row_cap:
            return tree
        return tree.limit(row_cap)
    return exp.select("*").from_(tree.subquery("capped")).limit(row_cap)


def check_sql(sql: str, allowed_tables: set[str], row_cap: int = DEFAULT_ROW_CAP) -> GuardResult:
    """Return the SQL with a row cap if it is safe, otherwise the reasons it is not."""
    try:
        statements = [s for s in sqlglot.parse(sql, read="duckdb") if s is not None]
    except (ParseError, TokenError) as error:
        return GuardResult(ok=False, errors=(f"SQL does not parse: {error}",))

    if len(statements) != 1:
        return GuardResult(ok=False, errors=(f"Expected one statement, got {len(statements)}",))
    tree = statements[0]
    if not isinstance(tree, exp.Query):
        return GuardResult(ok=False, errors=("Only SELECT queries are allowed",))

    errors: list[str] = []
    for node in tree.find_all(*_BLOCKED_NODES):
        errors.append(f"Statement not allowed inside a query: {node.key}")

    for func in tree.find_all(exp.Func):
        name = _function_name(func)
        if name in BLOCKED_FUNCTIONS:
            errors.append(f"Function not allowed: {name}")

    cte_names = {cte.alias_or_name.lower() for cte in tree.find_all(exp.CTE)}
    allowed = {t.lower() for t in allowed_tables}
    used: set[str] = set()
    for table in tree.find_all(exp.Table):
        name = table.name.lower()
        if name in cte_names and not table.db:
            continue
        if not name or table.db or table.catalog:
            errors.append(f"Table reference not allowed: {table.sql(dialect='duckdb')}")
        elif name not in allowed:
            errors.append(f"Table not allowed: {name}")
        else:
            used.add(name)

    if errors:
        return GuardResult(ok=False, errors=tuple(dict.fromkeys(errors)))
    capped = _cap_rows(tree, row_cap)
    return GuardResult(ok=True, sql=capped.sql(dialect="duckdb"), tables=tuple(sorted(used)))
