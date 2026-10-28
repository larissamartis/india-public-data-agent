"""Step 1: the LLM's plan for a question, as a checked structure."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationError

Task = Literal[
    "single_fact", "ranking", "change", "scaled", "combine", "trend", "group", "correlation"
]
REASONS = (
    "not_loaded",
    "out_of_range",
    "not_published",
    "wrong_area",
    "wrong_grain",
    "causal_claim",
)


class Plan(BaseModel):
    model_config = ConfigDict(extra="ignore")

    status: Literal["answerable", "cannot_answer", "unclear"]
    interpretation: str = ""
    metrics: list[str] = []
    areas: list[str] = []
    period_start: date | None = None
    period_end: date | None = None
    task: Task = "single_fact"
    causal: bool = False
    reason: str | None = None
    clarifying_question: str | None = None


class PlanError(ValueError):
    pass


def parse_plan(reply: dict) -> Plan:
    try:
        plan = Plan.model_validate(reply)
    except ValidationError as error:
        raise PlanError(f"the plan does not match the expected shape: {error}") from error
    if plan.period_start and plan.period_end and plan.period_start > plan.period_end:
        plan.period_start, plan.period_end = plan.period_end, plan.period_start
    return plan


PLAN_SYSTEM = """\
You plan answers to questions about India's public state-level data. You never answer the
question yourself. Reply with one JSON object only.

The warehouse holds exactly these metrics (id: label [unit; grain; combine rule] coverage):
{metrics}

Telecom figures are by TRAI service area, not by state. Service areas: {service_areas}.

JSON fields:
- status: "answerable" if the metrics above can answer it, "cannot_answer" if they cannot,
  "unclear" if the question is too vague to know what is wanted.
- interpretation: one sentence saying exactly what will be computed.
- metrics: metric ids from the list above that are needed (no others).
- areas: states or UTs as written in the question, "India", or service areas. Empty list
  means all states.
- period_start, period_end: ISO dates covering every period needed (a month is its first to
  last day; a financial year 2023-24 is 2023-04-01 to 2024-03-31; end-March 2025 is
  2025-03-31; a population year 2026 is 2026-01-01 to 2026-12-31).
- task: single_fact, ranking, change, scaled, combine, trend, group or correlation.
- causal: true if the question asks whether one thing caused or drove another.
- reason (only when cannot_answer): not_loaded (data not in the warehouse), out_of_range
  (outside the years held), not_published, wrong_area (district, city, or a state that the
  data does not report separately), wrong_grain (for example a month for end-March data).
- clarifying_question (only when unclear): one short question back to the user.
"""
