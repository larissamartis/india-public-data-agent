"""The agent: a fixed sequence of steps. The LLM does language work; code does what must be right.

  0 cache        code  same question + same data version -> saved answer
  1 plan         LLM   JSON plan; unknown metric ids are rejected
  2 coverage     code  refuse (saying what is available) or proceed
  3 SQL          LLM   with worked examples from the dev split only
  4 guard        code  sqlglot guard, read-only DB, metric and averaging checks; 2 repairs
  5 maths        code  correlation (Pearson, Spearman, n)
  6 answer       LLM   about 80 words, from the result table only
  7 number check code  every number must come from the results; 1 retry, then a template
  8 caveats      code  rule-based
  9 chart        code  bar, line or scatter

Questions are untrusted input; steps 2, 4 and 7 are code and cannot be argued with.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path

import duckdb

from bharat.agent.catalog import (
    AGENT_TABLES,
    BASE_SCHEMA,
    BASE_TABLES,
    SCHEMA,
    Catalog,
    connect,
)
from bharat.agent.gate import Area, GateResult, check
from bharat.agent.llm import LLMBase, LLMError
from bharat.agent.number_check import extract_numbers, unsupported_numbers
from bharat.agent.plan import PLAN_SYSTEM, Plan, PlanError, parse_plan
from bharat.agent.sql_guard import check_sql
from bharat.agent.support import (
    CAVEAT_TEXT,
    AnswerCache,
    caveat_ids,
    chart_for,
    correlation,
    worked_examples,
)
from bharat.eval.gold import indian

MAX_REPAIRS = 2
MAX_ROWS_TO_LLM = 40
UNRELIABLE = "I couldn't answer that reliably from the data, so I won't guess."


@dataclass
class AgentResult:
    question: str
    status: str  # 'answer', 'refuse', 'clarify' or 'error'
    answer: str
    reason: str | None = None
    columns: list[str] = field(default_factory=list)
    rows: list[list] = field(default_factory=list)
    stats: dict | None = None
    sql: str | None = None
    caveats: list[dict] = field(default_factory=list)
    sources: list[dict] = field(default_factory=list)
    chart: dict | None = None
    plan: dict | None = None
    trace: list[dict] = field(default_factory=list)
    llm_calls: int = 0
    fallbacks: int = 0
    seconds: float = 0.0
    data_version: str = ""
    cached: bool = False
    template_answer: bool = False


def _no_gate(plan: Plan) -> GateResult:
    """The ablation: only the LLM's own plan decides; names are passed on as written."""
    if plan.status == "unclear":
        return GateResult("clarify", message=plan.clarifying_question or "Could you clarify?")
    if plan.status == "cannot_answer":
        return GateResult("refuse", reason=plan.reason or "not_loaded", message=plan.interpretation)
    return GateResult("proceed", areas=[Area(name, "as written") for name in plan.areas])


class Agent:
    def __init__(
        self,
        llm: LLMBase,
        con: duckdb.DuckDBPyConnection | None = None,
        cache_dir: Path | None = None,
        today: date | None = None,
        metrics_layer: bool = True,
    ):
        """`metrics_layer=False` is the ablation: no metric definitions, coverage gate,
        caveat rules or ratio check; the SQL guard and number check stay on."""
        self.llm = llm
        self.con = con or connect()
        self.catalog = Catalog(self.con)
        self.cache = AnswerCache(cache_dir)
        self.today = today
        self.metrics_layer = metrics_layer
        self.tables = AGENT_TABLES if metrics_layer else BASE_TABLES

    # ------------------------------------------------------------------ public

    def ask(self, question: str) -> AgentResult:
        started = time.monotonic()
        calls_before = len(self.llm.calls)
        cached = self.cache.get(question, self.catalog.data_version)
        if cached:
            result = AgentResult(**cached)
            result.cached = True
            return result
        result = AgentResult(question, "error", UNRELIABLE, data_version=self.catalog.data_version)
        try:
            self._run(question, result)
        except LLMError as error:
            result.status, result.answer = "error", UNRELIABLE
            result.trace.append({"step": "llm", "error": str(error)})
        new_calls = self.llm.calls[calls_before:]
        result.llm_calls = len(new_calls)
        result.fallbacks = sum(c.fallback for c in new_calls)
        result.seconds = round(time.monotonic() - started, 2)
        if result.status != "error":
            self.cache.put(question, self.catalog.data_version, asdict(result))
        return result

    # ------------------------------------------------------------------ steps

    def _run(self, question: str, result: AgentResult) -> None:
        plan = self._plan(question, result)
        if plan is None:
            return
        gate = check(plan, self.catalog, today=self.today) if self.metrics_layer else _no_gate(plan)
        result.trace.append({"step": "coverage", "status": gate.status, "reason": gate.reason})
        if gate.status != "proceed":
            result.status = "clarify" if gate.status == "clarify" else "refuse"
            result.reason, result.answer = gate.reason, gate.message
            result.caveats = [{"id": c, "text": CAVEAT_TEXT[c]} for c in sorted(gate.caveats)]
            return

        executed = self._sql(question, plan, gate, result)
        if executed is None:
            return
        columns, rows = executed
        result.columns, result.rows = columns, [list(r) for r in rows]

        if plan.task == "correlation":
            result.stats = correlation(rows)
            result.trace.append({"step": "maths", "stats": result.stats})

        result.answer, result.template_answer = self._answer(question, plan, columns, rows, result)
        result.status = "answer"
        chart = chart_for(plan.task, columns, rows, plan.interpretation or question)
        result.chart = asdict(chart) if chart else None
        if not self.metrics_layer:
            return  # no caveat rules or source lookup without the metrics layer

        jk = (
            any(a.state_code == 1 for a in gate.areas)
            and bool(plan.period_start and plan.period_start < date(2019, 10, 31))
            and any(self.catalog.metrics[m].source_id == "rbi" for m in plan.metrics)
        )
        ids = caveat_ids(
            plan.metrics,
            {m: self.catalog.metrics[m].combine_rule for m in plan.metrics},
            plan.task,
            plan.causal,
            result.sql or "",
            gate.caveats,
            jk,
        )
        result.caveats = [{"id": c, "text": CAVEAT_TEXT[c]} for c in ids]
        result.sources = self._sources(plan.metrics)

    def _plan(self, question: str, result: AgentResult) -> Plan | None:
        system = PLAN_SYSTEM.format(
            metrics=self.catalog.metric_table()
            if self.metrics_layer
            else self.catalog.metric_ids(),
            service_areas=", ".join(self.catalog.service_areas),
        )
        reply = self.llm.complete_json("plan", system, f"Question: {question}")
        try:
            plan = parse_plan(reply)
        except PlanError as error:
            result.trace.append({"step": "plan", "error": str(error)})
            return None
        result.plan = plan.model_dump(mode="json")
        result.trace.append({"step": "plan", "plan": result.plan})
        return plan

    def _sql_prompt(self, question: str, plan: Plan, gate: GateResult) -> tuple[str, str]:
        examples = "\n\n".join(
            f"Question: {q}\nSQL:\n{sql}" for q, sql in worked_examples(plan.task)
        )
        areas = (
            "; ".join(
                f"{a.name} ({a.kind}{', state_code ' + str(a.state_code) if a.state_code else ''})"
                for a in gate.areas
            )
            or "all states and UTs"
        )
        shapes = {
            "trend": "rows of (period_label, value) in time order",
            "ranking": "rows of (name, value) in rank order, limited to the number asked for",
            "correlation": "one row per state of (state_name, x, y), where x and y are the two "
            "measures; do not compute the correlation in SQL",
        }
        shape = shapes.get(plan.task, "one row with one column named value")
        if self.metrics_layer:
            tables = f"{SCHEMA}\nMetrics:\n{self.catalog.metric_table()}"
        else:
            tables = f"{BASE_SCHEMA}\nmetric_id values:\n{self.catalog.metric_ids()}"
        system = (
            "You write one DuckDB SELECT statement over these tables only:\n"
            f"{tables}\n\n"
            "Worked examples:\n\n"
            f"{examples}\n\n"
            'Reply with JSON: {"sql": "..."}. Use only the metrics in the plan.'
        )
        user = (
            f"Question: {question}\n"
            f"Plan: {plan.interpretation}\n"
            f"Metrics: {', '.join(plan.metrics)}\n"
            f"Areas: {areas}\n"
            f"Periods: {plan.period_start} to {plan.period_end}\n"
            f"Return {shape}."
        )
        return system, user

    def _sql(
        self, question: str, plan: Plan, gate: GateResult, result: AgentResult
    ) -> tuple[list[str], list[tuple]] | None:
        system, user = self._sql_prompt(question, plan, gate)
        feedback = ""
        for attempt in range(MAX_REPAIRS + 1):
            reply = self.llm.complete_json("sql", system, user + feedback)
            sql = str(reply.get("sql", ""))
            problem, columns, rows, safe_sql = self._run_sql(sql, plan)
            result.trace.append(
                {"step": "sql", "attempt": attempt + 1, "sql": sql, "problem": problem}
            )
            if not problem:
                result.sql = safe_sql
                return columns, rows
            feedback = (
                f"\n\nYour previous SQL was rejected: {problem}\nPrevious SQL:\n{sql}\nFix it."
            )
        result.status, result.answer = "error", UNRELIABLE
        return None

    def _run_sql(self, sql: str, plan: Plan):
        guard = check_sql(sql, self.tables)
        if not guard.ok:
            return f"guard: {'; '.join(guard.errors)}", [], [], None
        if self.metrics_layer:
            used = {m for m in re.findall(r"'([a-z_]+)'", sql) if m in self.catalog.metrics}
            extra = used - set(plan.metrics)
            if extra:
                return f"uses metrics not in the plan: {sorted(extra)}", [], [], None
            ratios = [m for m in used if self.catalog.metrics[m].combine_rule == "recompute"]
            if ratios and re.search(r"\bavg\s*\(", sql, re.I):
                return (
                    f"averages ratio metrics {ratios}; rebuild them from their parts",
                    [],
                    [],
                    None,
                )
        try:
            cursor = self.con.execute(guard.sql)
            rows = cursor.fetchall()
            columns = [d[0] for d in cursor.description]
        except duckdb.Error as error:
            return f"database error: {error}", [], [], None
        if not rows or all(v is None for row in rows for v in row):
            return "the query returned no rows", [], [], None
        return None, columns, rows, guard.sql

    def _answer(self, question, plan, columns, rows, result) -> tuple[str, bool]:
        table = "\n".join(
            [" | ".join(columns)] + [" | ".join(str(v) for v in r) for r in rows[:MAX_ROWS_TO_LLM]]
        )
        known = [m for m in plan.metrics if m in self.catalog.metrics] if self.metrics_layer else []
        units = ", ".join(f"{m}: {self.catalog.metrics[m].unit}" for m in known) or "not given"
        stats = f"\nComputed statistics: {json.dumps(result.stats)}" if result.stats else ""
        system = (
            "You write a short, plain-English answer (at most 80 words) for a general reader, "
            "using only the figures in the result table and statistics given. Do not add facts "
            "or numbers that are not there. Use Indian units (lakh, crore) where natural. Do "
            'not claim causes. Reply with JSON: {"answer": "..."}.'
        )
        user = f"Question: {question}\nUnits: {units}\nResult:\n{table}{stats}"
        values = [v for r in rows for v in r if isinstance(v, int | float)]
        if result.stats:
            values += [v for v in result.stats.values() if isinstance(v, int | float)]
        allowed = [m.value for m in extract_numbers(question)] + [len(rows), 100, 1000, 100000]
        feedback = ""
        for attempt in range(2):
            text = str(self.llm.complete_json("answer", system, user + feedback).get("answer", ""))
            bad = unsupported_numbers(text, values, allowed)
            result.trace.append(
                {"step": "number_check", "attempt": attempt + 1, "unsupported": bad}
            )
            if text and not bad:
                return text, False
            feedback = (
                f"\n\nThese numbers are not in the result: {bad}. Rewrite using only the "
                "result's figures."
            )
        return self._template(plan, columns, rows, result), True

    def _template(self, plan, columns, rows, result) -> str:
        first = self.catalog.metrics.get(plan.metrics[0]) if plan.metrics else None
        unit = first.unit if first and self.metrics_layer else ""
        if result.stats and result.stats.get("pearson") is not None:
            s = result.stats
            return (
                f"Across {s['n']} states, the correlation is {s['pearson']:.2f} "
                f"(Spearman {s['spearman']:.2f})."
            )
        lines = []
        for row in rows[:10]:
            *labels, value = row
            shown = indian(value) if isinstance(value, int | float) else str(value)
            lines.append(f"{' '.join(str(x) for x in labels)}: {shown} {unit}".strip())
        return "; ".join(lines)

    def _sources(self, metric_ids: list[str]) -> list[dict]:
        seen = []
        for source_id in dict.fromkeys(self.catalog.metrics[m].source_id for m in metric_ids):
            name, publisher, url = self.catalog.sources[source_id]
            seen.append({"source_id": source_id, "name": name, "publisher": publisher, "url": url})
        return seen
