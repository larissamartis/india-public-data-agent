"""Score one setup's structured output against a question's gold answer.

Every setup (plain LLM, agent without the metrics layer, full agent) produces the same
block: status, a number / ranking / series / correlation, caveat text and the answer.

- Numbers match within the question's relative tolerance. A unit slip by a power of ten
  that Indian figures invite (lakh, crore, per cent as a fraction) is forgiven for every
  setup alike, because the question is whether the figure is right, not its unit.
- Rankings must name the same areas in the same order.
- Trends need at least 95% of the gold points within tolerance.
- Correlations must be within the question's absolute tolerance.
- Refusals and clarifications are judged by status.
- Required caveats are matched by keyword (eval/caveats.yaml); a sample is checked by hand.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

from bharat.eval.questions import Question, load_caveats
from bharat.ingest.trai import service_area
from bharat.reference.states import UnknownStateError, resolve_state

SCALES = (1.0, 1e-2, 1e2, 1e-3, 1e3, 1e-5, 1e5, 1e-7, 1e7)
SERIES_SHARE = 0.95


@dataclass
class Output:
    """What a setup said, in the shape the scorer reads."""

    id: str
    setup: str
    status: str  # 'answer', 'refuse', 'clarify' or 'error'
    answer: str = ""
    number: float | None = None
    ranking: list[str] = field(default_factory=list)
    series: list[list] = field(default_factory=list)
    r: float | None = None
    caveat_text: str = ""
    sql: str | None = None
    llm_calls: int = 0
    fallbacks: int = 0
    seconds: float = 0.0
    stage: str | None = None  # where the agent stopped: plan, coverage, sql, answer, llm


@dataclass
class Score:
    id: str
    setup: str
    type: str
    expected: str
    status: str
    correct: bool
    values_ok: bool | None
    caveats_ok: bool
    wrong_answer: bool
    over_refusal: bool
    missing_caveats: list[str]
    failed_step: str | None


def close(value: float | None, gold: float, tolerance: float) -> bool:
    if value is None or not isinstance(value, int | float) or not math.isfinite(value):
        return False
    if gold == 0:
        return abs(value) < 1e-9
    return any(abs(value * s - gold) / abs(gold) <= tolerance for s in SCALES)


def area_key(name: str) -> str:
    text = str(name).strip()
    try:
        return f"state:{resolve_state(text).code}"
    except UnknownStateError:
        pass
    lsa = service_area(text)
    if lsa:
        return f"lsa:{lsa}"
    return re.sub(r"[^a-z0-9]", "", text.lower())


def _label(text) -> str:
    return re.sub(r"[^0-9a-z]", "", str(text).lower())


def values_correct(q: Question, out: Output, rows: list[list]) -> bool:
    if q.kind == "number":
        return close(out.number, rows[0][0], q.tolerance)
    if q.kind == "ranking":
        gold = [area_key(r[0]) for r in rows]
        return [area_key(n) for n in out.ranking[: len(gold)]] == gold and len(out.ranking) >= len(
            gold
        )
    if q.kind == "series":
        given = {_label(p[0]): p[1] for p in out.series if len(p) >= 2}
        hits = sum(close(given.get(_label(label)), value, q.tolerance) for label, value, *_ in rows)
        return hits >= SERIES_SHARE * len(rows)
    if q.kind == "correlation":
        return out.r is not None and abs(out.r - rows[0][0]) <= q.tolerance
    return False


def caveats_present(q: Question, text: str, catalogue: dict | None = None) -> list[str]:
    """Required caveats whose keywords do not appear in the text."""
    catalogue = catalogue or load_caveats()["caveats"]
    lowered = text.lower()
    return [c for c in q.caveats if not any(k.lower() in lowered for k in catalogue[c]["keywords"])]


def score(q: Question, out: Output, gold: dict) -> Score:
    missing = caveats_present(q, f"{out.answer}\n{out.caveat_text}")
    values_ok = None
    if q.expected == "answer":
        values_ok = out.status == "answer" and values_correct(q, out, gold["rows"])
        correct = bool(values_ok) and not missing
        wrong = out.status == "answer" and not values_ok
        over = out.status in ("refuse", "clarify", "error")
    elif q.expected == "refuse":
        correct = out.status == "refuse" and not missing
        wrong = out.status == "answer"
        over = False
    else:
        correct = out.status == "clarify"
        wrong = out.status == "answer"
        over = False
    failed = None if correct else _failure(q, out, values_ok, missing)
    return Score(
        id=q.id,
        setup=out.setup,
        type=q.type,
        expected=q.expected,
        status=out.status,
        correct=correct,
        values_ok=values_ok,
        caveats_ok=not missing,
        wrong_answer=wrong,
        over_refusal=over,
        missing_caveats=missing,
        failed_step=failed,
    )


def _failure(q: Question, out: Output, values_ok: bool | None, missing: list[str]) -> str:
    """One label per failure, naming the pipeline step where the agent went wrong."""
    where = f" at {out.stage}" if out.stage else ""
    if q.expected == "answer":
        if out.status != "answer":
            return f"{out.status} instead of answer{where}"
        if not values_ok:
            return "wrong values" if out.setup == "plain" else f"wrong values{where}"
        return "missing caveat"
    if out.status != q.expected:
        return f"{out.status} instead of {q.expected}{where}"
    return "missing caveat"


def wilson(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95% Wilson score interval for a proportion."""
    if n == 0:
        return 0.0, 0.0
    p = successes / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return max(0.0, centre - half), min(1.0, centre + half)
