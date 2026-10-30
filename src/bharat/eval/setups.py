"""The three setups compared in the benchmark, each turned into the scorer's Output.

- plain: the LLM answers from its own knowledge, with no data.
- no_metrics: the agent on the tidy tables without the metrics layer (no metric
  definitions, coverage gate, caveat rules or ratio check; SQL guard and number check on).
- full: the agent as designed.
All three use the same LLM client and model.
"""

from __future__ import annotations

from bharat.agent.llm import LLMBase, LLMError
from bharat.agent.pipeline import Agent, AgentResult
from bharat.eval.questions import Question
from bharat.eval.score import Output

PLAIN_SYSTEM = """\
You answer questions about India's states using only what you already know. Reply with one
JSON object:
{"status": "answer" | "refuse" | "clarify",
 "answer": "a short answer in plain English",
 "value": a single number if the answer is one number, else null,
 "ranking": ["names in order"] if the answer is a ranking, else [],
 "series": [{"label": "period", "value": number}] if the answer is a series, else [],
 "r": a correlation coefficient if asked for one, else null,
 "caveats": ["limitations a careful analyst would state"]}
Use "refuse" if the figure cannot be known or is not published, and "clarify" if the
question is too vague. Money is in ₹ crore unless the question asks per person (₹);
population in persons; percentages as numbers such as 12.5.
"""


def _number(value) -> float | None:
    try:
        return float(value) if value is not None and value != "" else None
    except (TypeError, ValueError):
        return None


def plain(llm: LLMBase, q: Question) -> Output:
    calls_before = len(llm.calls)
    try:
        reply = llm.complete_json("plain", PLAIN_SYSTEM, f"Question: {q.question}")
    except LLMError as error:
        return Output(q.id, "plain", "error", answer=str(error), stage="llm")
    status = (
        reply.get("status") if reply.get("status") in ("answer", "refuse", "clarify") else "answer"
    )
    series = [
        [str(p.get("label", "")), _number(p.get("value"))]
        for p in reply.get("series") or []
        if isinstance(p, dict)
    ]
    calls = llm.calls[calls_before:]
    return Output(
        q.id,
        "plain",
        status,
        answer=str(reply.get("answer", "")),
        number=_number(reply.get("value")),
        ranking=[str(n) for n in reply.get("ranking") or []],
        series=series,
        r=_number(reply.get("r")),
        caveat_text="\n".join(str(c) for c in reply.get("caveats") or []),
        llm_calls=len(calls),
        fallbacks=sum(c.fallback for c in calls),
        seconds=round(sum(c.seconds for c in calls), 2),
    )


def _stage(result: AgentResult) -> str | None:
    steps = [t for t in result.trace if "step" in t]
    if not steps:
        return None
    last = steps[-1]
    if last["step"] == "coverage" and result.status in ("refuse", "clarify"):
        plan = result.plan or {}
        return "plan" if plan.get("status") in ("cannot_answer", "unclear") else "coverage"
    if last["step"] == "number_check" and result.template_answer:
        return "answer"
    return last["step"]


def from_agent(setup: str, q: Question, result: AgentResult) -> Output:
    rows = result.rows or []
    numbers = [v for v in (rows[0] if rows else []) if isinstance(v, int | float)]
    r = None
    if result.stats and result.stats.get("pearson") is not None:
        r = result.stats["pearson"]
    elif result.columns and result.columns[0].lower() in ("r", "corr", "correlation") and numbers:
        r = numbers[0]
    return Output(
        q.id,
        setup,
        result.status,
        answer=result.answer,
        number=numbers[0] if numbers else None,
        ranking=[next((str(v) for v in row if isinstance(v, str)), "") for row in rows],
        series=[
            [str(row[0]), next((v for v in row[1:] if isinstance(v, int | float)), None)]
            for row in rows
            if row
        ],
        r=r,
        caveat_text="\n".join(c["text"] for c in result.caveats),
        sql=result.sql,
        llm_calls=result.llm_calls,
        fallbacks=result.fallbacks,
        seconds=result.seconds,
        stage=_stage(result),
    )


def run_agent(agent: Agent, setup: str, q: Question) -> Output:
    return from_agent(setup, q, agent.ask(q.question))
