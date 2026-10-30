"""What the agent knows about the warehouse: tables, metrics, coverage and the data version.

The connection is the second lock behind the SQL guard: read-only, with external access
(files, URLs, extensions) switched off and the configuration locked, so even SQL that slipped
past the guard could not read or change anything else.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

import duckdb

SERVING_DB = Path(__file__).resolve().parents[3] / "data" / "serving" / "serving.duckdb"

AGENT_TABLES = frozenset(
    {
        "fct_state_metric",
        "fct_national_metric",
        "fct_lsa_metric",
        "dim_state",
        "dim_metric",
        "dim_source",
        "dim_period",
        "coverage",
    }
)

SCHEMA = """\
fct_state_metric(metric_id, state_code, state_name, period_type, period_label, period_start,
  period_end, value, unit, source_id, source_ref, name_as_printed, note)
  One row per metric, state or UTs and period. state_name uses official names
  ('Jammu and Kashmir', 'Odisha', 'Puducherry', 'Uttarakhand', 'Delhi',
  'Dadra and Nagar Haveli and Daman and Diu' with state_code 38 from 2020).
fct_national_metric(metric_id, period_type, period_label, period_start, period_end, value, unit,
  source_id, source_ref)  All-India figures as published (bank tables and population only).
fct_lsa_metric(metric_id, service_area, period_type, period_label, period_start, period_end,
  value, unit, source_id, source_ref)  Telecom by TRAI service area, not by state.
dim_state(state_code, state_name, kind, valid_from, valid_to)
dim_metric(metric_id, label, unit, grain, source_id, combine_rule, description, caveat)
coverage(metric_id, state_code, state_name, period_type, periods, first_period, last_period)

period_label formats: month '2026-08' (GST); fy '2023-24' (RBI income, 1 April to 31 March);
end_march '2025-03-31' (RBI banking, a stock on that day); year_jul1 '2025' (population on
1 July). A financial-year total of a monthly metric is the sum over period_start from
1 April to 31 March. Money is in ₹ crore unless dim_metric says otherwise; population is in
persons. Never average a metric whose combine_rule is 'recompute' across states: rebuild it
from its parts (for example weight per-capita figures by population).
"""

# The ablation without the metrics layer sees the tidy tables only: no metric definitions,
# units, grains, combine rules or coverage.
BASE_TABLES = frozenset({"fct_state_metric", "fct_national_metric", "fct_lsa_metric", "dim_state"})
BASE_SCHEMA = "\n".join(
    line
    for line in SCHEMA.split("\n\n")[0].splitlines()
    if not line.startswith(("dim_metric", "coverage"))
)


def connect(path: Path = SERVING_DB) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(
        str(path),
        read_only=True,
        config={"enable_external_access": False, "autoload_known_extensions": False},
    )
    # A second connection in the same process shares the database, which may be locked already.
    if not con.execute("select current_setting('lock_configuration')").fetchall()[0][0]:
        con.execute("set lock_configuration = true")
    return con


@dataclass(frozen=True)
class Metric:
    metric_id: str
    label: str
    unit: str
    grain: str
    source_id: str
    combine_rule: str
    description: str
    caveat: str


@dataclass(frozen=True)
class Coverage:
    metric_id: str
    state_code: int
    state_name: str
    first: date
    last: date


class Catalog:
    def __init__(self, con: duckdb.DuckDBPyConnection):
        self.con = con
        self.metrics = {
            row[0]: Metric(*row)
            for row in con.execute(
                "select metric_id, label, unit, grain, source_id, combine_rule, description,"
                " coalesce(caveat, '') from dim_metric order by metric_id"
            ).fetchall()
        }
        self.coverage = [
            Coverage(*row)
            for row in con.execute(
                "select metric_id, state_code, state_name, first_period, last_period from coverage"
            ).fetchall()
        ]
        self.lsa_range = con.execute(
            "select min(period_end), max(period_end) from fct_lsa_metric"
        ).fetchall()[0]
        self.service_areas = sorted(
            r[0] for r in con.execute("select distinct service_area from fct_lsa_metric").fetchall()
        )
        built = con.execute("select built_at, git_sha from build_info").fetchall()[0]
        self.data_version = f"{built[0]}|{built[1]}"
        self.sources = {
            row[0]: row[1:]
            for row in con.execute(
                "select source_id, name, publisher, url from dim_source"
            ).fetchall()
        }

    def range_of(self, metric_id: str) -> tuple[date, date] | None:
        if metric_id == "wireless_subscribers":
            return self.lsa_range if self.lsa_range[0] else None
        spans = [c for c in self.coverage if c.metric_id == metric_id]
        if not spans:
            return None
        return min(c.first for c in spans), max(c.last for c in spans)

    def metric_table(self) -> str:
        lines = []
        for m in self.metrics.values():
            span = self.range_of(m.metric_id)
            when = f"{span[0]} to {span[1]}" if span else "no data"
            lines.append(
                f"- {m.metric_id}: {m.label} [{m.unit}; {m.grain}; {m.combine_rule}] {when}"
            )
        return "\n".join(lines)

    def metric_ids(self) -> str:
        """Bare metric ids, as the ablation without the metrics layer sees them."""
        return "\n".join(f"- {m}" for m in self.metrics)

    def available_summary(self) -> str:
        """One line per source, for refusals that say what *is* available."""
        by_source: dict[str, list[str]] = {}
        for m in self.metrics.values():
            by_source.setdefault(m.source_id, []).append(m.label)
        parts = []
        for source_id, labels in by_source.items():
            name = self.sources.get(source_id, (source_id,))[0]
            parts.append(f"{name}: {', '.join(labels)}")
        return "; ".join(parts)
