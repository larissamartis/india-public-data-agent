"""Check a loaded DuckDB table against its source's YAML contract.

A contract is a promise about a source: its columns and types, its key, sensible value ranges,
state names that match the reference list, a stable row count and recent data. If a source
breaks a promise, the build stops and says which file and which rule, instead of letting a
bad number reach an answer.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from importlib import resources
from pathlib import Path

import duckdb
import yaml
from pydantic import BaseModel, ConfigDict, Field

from bharat.reference.states import UnknownStateError, normalise_name, resolve_state

_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_SAMPLE = 5


class ColumnRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str
    not_null: bool = False
    min: float | None = None
    max: float | None = None
    allowed: list[str] | None = None
    state_name: bool = False
    # Names that are fine in a state column without being states, such as "All India".
    allow_names: list[str] = Field(default_factory=list)


class Freshness(BaseModel):
    model_config = ConfigDict(extra="forbid")

    column: str
    max_age_days: int


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str
    table: str
    key: list[str] = Field(default_factory=list)
    columns: dict[str, ColumnRule]
    row_count_tolerance: float = 0.2
    freshness: Freshness | None = None


@dataclass(frozen=True)
class Violation:
    rule: str
    column: str | None
    detail: str

    def __str__(self) -> str:
        where = f" [{self.column}]" if self.column else ""
        return f"{self.rule}{where}: {self.detail}"


class ContractError(Exception):
    def __init__(self, source: str, violations: list[Violation]):
        self.source = source
        self.violations = violations
        lines = "\n".join(f"  - {v}" for v in violations)
        super().__init__(f"Contract failed for {source}:\n{lines}")


def load_contract(path: str | Path) -> Contract:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return Contract.model_validate(data)


def load_source_contract(name: str) -> Contract:
    """Load a contract shipped with the package, from contracts/sources/<name>.yml."""
    text = (
        resources.files("bharat.contracts")
        .joinpath("sources", f"{name}.yml")
        .read_text(encoding="utf-8")
    )
    return Contract.model_validate(yaml.safe_load(text))


def _quote(name: str) -> str:
    if not _IDENTIFIER.match(name):
        raise ValueError(f"Not a plain identifier: {name!r}")
    return f'"{name}"'


def _as_date(value: date | datetime) -> date:
    return value.date() if isinstance(value, datetime) else value


def check_contract(
    con: duckdb.DuckDBPyConnection,
    contract: Contract,
    *,
    previous_row_count: int | None = None,
    today: date | None = None,
) -> list[Violation]:
    """Return every broken rule; an empty list means the table keeps its contract."""
    table = _quote(contract.table)
    actual = dict(
        con.execute(
            "select column_name, data_type from information_schema.columns where table_name = ?",
            [contract.table],
        ).fetchall()
    )
    if not actual:
        return [Violation("table_exists", None, f"table {contract.table} not found")]

    violations: list[Violation] = []
    usable: dict[str, ColumnRule] = {}
    for name, rule in contract.columns.items():
        if name not in actual:
            violations.append(Violation("column_present", name, "missing column"))
        elif actual[name].upper() != rule.type.upper():
            violations.append(
                Violation("column_type", name, f"expected {rule.type}, found {actual[name]}")
            )
        else:
            usable[name] = rule
    # Columns starting with "_" are load details (source file, download time), not source data.
    extra = {n for n in actual.keys() - contract.columns.keys() if not n.startswith("_")}
    for name in sorted(extra):
        violations.append(Violation("unexpected_column", name, "column not in contract"))

    row_count = con.execute(f"select count(*) from {table}").fetchone()[0]
    if row_count == 0:
        violations.append(Violation("row_count", None, "table is empty"))
    elif previous_row_count:
        change = abs(row_count - previous_row_count) / previous_row_count
        if change > contract.row_count_tolerance:
            violations.append(
                Violation(
                    "row_count",
                    None,
                    f"{row_count} rows vs {previous_row_count} last build "
                    f"({change:.0%} change, limit {contract.row_count_tolerance:.0%})",
                )
            )

    for name, rule in usable.items():
        violations.extend(_check_column(con, table, name, rule, today))

    if contract.key and all(k in usable for k in contract.key):
        cols = ", ".join(_quote(k) for k in contract.key)
        dupes = con.execute(
            f"select count(*) from (select 1 from {table} group by {cols} having count(*) > 1)"
        ).fetchone()[0]
        if dupes:
            violations.append(
                Violation(
                    "unique_key", None, f"{dupes} duplicate keys on ({', '.join(contract.key)})"
                )
            )

    if contract.freshness and contract.freshness.column in usable:
        violations.extend(_check_freshness(con, table, contract.freshness, today or date.today()))

    return violations


def _check_column(
    con: duckdb.DuckDBPyConnection, table: str, name: str, rule: ColumnRule, today: date | None
) -> list[Violation]:
    col = _quote(name)
    found: list[Violation] = []

    if rule.not_null:
        nulls = con.execute(f"select count(*) from {table} where {col} is null").fetchone()[0]
        if nulls:
            found.append(Violation("not_null", name, f"{nulls} null values"))

    if rule.min is not None:
        n, worst = con.execute(
            f"select count(*), min({col}) from {table} where {col} < ?", [rule.min]
        ).fetchone()
        if n:
            found.append(Violation("min", name, f"{n} values below {rule.min} (lowest {worst})"))

    if rule.max is not None:
        n, worst = con.execute(
            f"select count(*), max({col}) from {table} where {col} > ?", [rule.max]
        ).fetchone()
        if n:
            found.append(Violation("max", name, f"{n} values above {rule.max} (highest {worst})"))

    if rule.allowed is not None:
        bad = [
            r[0]
            for r in con.execute(
                f"select distinct {col} from {table} "
                f"where {col} is not null and not list_contains(?, {col}) order by 1",
                [rule.allowed],
            ).fetchall()
        ]
        if bad:
            found.append(Violation("allowed", name, f"unexpected values {bad[:_SAMPLE]}"))

    if rule.state_name:
        names = [
            r[0]
            for r in con.execute(
                f"select distinct {col} from {table} where {col} is not null order by 1"
            ).fetchall()
        ]
        exempt = {normalise_name(n) for n in rule.allow_names}
        unknown = []
        for value in names:
            if normalise_name(value) in exempt:
                continue
            try:
                resolve_state(value)
            except UnknownStateError:
                unknown.append(value)
        if unknown:
            found.append(Violation("state_name", name, f"unmatched names {unknown[:_SAMPLE]}"))

    return found


def _check_freshness(
    con: duckdb.DuckDBPyConnection, table: str, rule: Freshness, today: date
) -> list[Violation]:
    latest = con.execute(f"select max({_quote(rule.column)}) from {table}").fetchone()[0]
    if latest is None:
        return [Violation("freshness", rule.column, "no dates found")]
    age = (today - _as_date(latest)).days
    if age > rule.max_age_days:
        return [
            Violation(
                "freshness",
                rule.column,
                f"latest {_as_date(latest).isoformat()} is {age} days old "
                f"(limit {rule.max_age_days})",
            )
        ]
    return []


def enforce_contract(
    con: duckdb.DuckDBPyConnection,
    contract: Contract,
    *,
    previous_row_count: int | None = None,
    today: date | None = None,
) -> None:
    """Raise ContractError listing every broken rule."""
    violations = check_contract(con, contract, previous_row_count=previous_row_count, today=today)
    if violations:
        raise ContractError(contract.source, violations)
