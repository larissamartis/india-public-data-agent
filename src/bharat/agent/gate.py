"""Step 2: the coverage gate. Plain code decides whether the plan can be answered.

It catches what an LLM tends to get wrong: names that are not states (cities, districts),
states that did not exist yet, a state asked of data published only by telecom service area,
periods outside the data, data held only at another grain, and cause-and-effect questions.
When it refuses, it says what *is* available.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from bharat.agent.catalog import Catalog
from bharat.agent.plan import REASONS, Plan
from bharat.ingest.trai import service_area
from bharat.reference.states import UnknownStateError, normalise_name, resolve_state

MERGED_DNH = 38
MERGER_DAY = date(2020, 1, 26)
LADAKH = 37
NATIONAL = {"india", "all india"}


@dataclass
class Area:
    name: str  # canonical: state name, 'India' or a service area
    kind: str  # 'state', 'national' or 'service_area'
    state_code: int | None = None


@dataclass
class GateResult:
    status: str  # 'proceed', 'refuse' or 'clarify'
    reason: str | None = None
    message: str = ""
    areas: list[Area] = field(default_factory=list)
    caveats: set[str] = field(default_factory=set)


def _refuse(reason: str, message: str, caveats: set[str] | None = None) -> GateResult:
    return GateResult("refuse", reason, message, caveats=caveats or set())


def check(plan: Plan, catalog: Catalog, today: date | None = None) -> GateResult:
    today = today or date.today()
    available = f"The warehouse holds: {catalog.available_summary()}."

    if plan.status == "unclear":
        question = plan.clarifying_question or "Which measure, state and period do you mean?"
        return GateResult("clarify", message=question)
    if plan.causal and plan.task != "correlation":
        return _refuse(
            "causal_claim",
            "The data can show whether two measures move together across states, but not "
            "what caused what.",
            {"causation"},
        )
    if plan.status == "cannot_answer":
        reason = plan.reason if plan.reason in REASONS else "not_loaded"
        return _refuse(reason, f"{plan.interpretation} {available}".strip())

    unknown = [m for m in plan.metrics if m not in catalog.metrics]
    if unknown or not plan.metrics:
        return _refuse("not_loaded", f"That data is not in the warehouse. {available}")

    telecom = "wireless_subscribers" in plan.metrics
    caveats: set[str] = set()
    areas: list[Area] = []
    when = plan.period_end or plan.period_start
    for name in plan.areas:
        if normalise_name(name) in NATIONAL:
            areas.append(Area("India", "national", 0))
            continue
        if telecom:
            lsa = service_area(name)
            if lsa is None:
                return _refuse(
                    "wrong_area",
                    f"Telecom figures are published by TRAI service area, and {name} is not "
                    f"reported separately. Service areas: {', '.join(catalog.service_areas)}.",
                    {"service_area"},
                )
            try:  # also a state, for questions that mix telecom with state data
                code: int | None = resolve_state(name).code
            except UnknownStateError:
                code = None
            areas.append(Area(lsa, "service_area", code))
            continue
        try:
            state = resolve_state(name)
        except UnknownStateError:
            return _refuse(
                "wrong_area",
                f"'{name}' is not a state or UT in the data; figures are published for states "
                "and UTs only, not districts or cities.",
            )
        code, canonical = state.code, state.name
        if code in (25, 26) and plan.period_start and plan.period_start >= MERGER_DAY:
            code, canonical = MERGED_DNH, resolve_state("DNHDD").name
            caveats.add("dnh_merged")
        if state.valid_from and when and when < state.valid_from:
            caveats.add("ladakh_in_jk" if code == LADAKH else "state_formed")
        areas.append(Area(canonical, "state", code))

    for metric_id in plan.metrics:
        span = catalog.range_of(metric_id)
        if span is None:
            return _refuse("not_loaded", f"No figures are loaded for that measure. {available}")
        first, last = span
        label = catalog.metrics[metric_id].label
        if plan.period_end and plan.period_end < first:
            return _refuse(
                "out_of_range",
                f"{label} is available from {first} to {last}.",
                caveats & {"state_formed"},
            )
        if plan.period_start and plan.period_start > last:
            reason = "not_published" if plan.period_start <= today else "out_of_range"
            return _refuse(reason, f"{label} is available from {first} to {last}.")

    missing = _missing_rows(plan, areas, catalog)
    if missing:
        metric_id, area = missing
        metric = catalog.metrics[metric_id]
        if area and area.state_code == LADAKH and "ladakh_in_jk" in caveats:
            return _refuse(
                "wrong_area",
                "Ladakh became a separate UT in October 2019; earlier figures are included "
                "in Jammu and Kashmir.",
                {"ladakh_in_jk"},
            )
        if metric.grain in ("end_march", "year_jul1"):
            return _refuse(
                "wrong_grain",
                f"{metric.label} is published only for {metric.grain.replace('_', ' ')} dates.",
            )
        where = f" for {area.name}" if area else ""
        return _refuse(
            "not_published", f"No {metric.label} figure is published{where} for that period."
        )

    if telecom:
        caveats.add("service_area")
    return GateResult("proceed", areas=areas, caveats=caveats)


def _missing_rows(
    plan: Plan, areas: list[Area], catalog: Catalog
) -> tuple[str, Area | None] | None:
    """The first (metric, area) with no rows in the requested period, if any."""
    if not plan.period_start or not plan.period_end:
        return None
    targets = areas or [None]
    for metric_id in plan.metrics:
        for area in targets:
            if metric_id == "wireless_subscribers":
                sql = "select count(*) from fct_lsa_metric where period_end between ? and ?"
                args: list = [plan.period_start, plan.period_end]
                if area:
                    sql += " and service_area = ?"
                    args.append(area.name)
            elif area and area.kind == "national":
                sql = (
                    "select count(*) from fct_national_metric"
                    " where metric_id = ? and period_end between ? and ?"
                )
                args = [metric_id, plan.period_start, plan.period_end]
            else:
                if area and area.state_code is None:
                    continue  # a service area with no matching state: nothing to check
                sql = (
                    "select count(*) from fct_state_metric"
                    " where metric_id = ? and period_end between ? and ?"
                )
                args = [metric_id, plan.period_start, plan.period_end]
                if area:
                    sql += " and state_code = ?"
                    args.append(area.state_code)
            if catalog.con.execute(sql, args).fetchall()[0][0] == 0:
                return metric_id, area
    return None
