import json

import pytest

from bharat.agent.catalog import SERVING_DB
from bharat.agent.llm import FakeLLM
from bharat.eval.questions import Question
from bharat.eval.run import report, run
from bharat.eval.score import Output, area_key, close, score, wilson


def q(**fields):
    base = {"id": "D999", "type": "single_fact", "question": "x?", "expected": "answer"}
    if fields.get("expected", "answer") == "answer":
        base |= {"kind": "number", "gold_sql": "select 1"}
    return Question.model_validate(base | fields)


def out(**fields):
    return Output(id="D999", setup=fields.pop("setup", "full"), **fields)


@pytest.mark.parametrize(
    ("value", "gold", "ok"),
    [
        (3077.71, 3077.71, True),
        (3078, 3077.71, True),  # rounding within 0.5%
        (30777100000, 3077.71, True),  # same figure in rupees rather than ₹ crore
        (12.5, 0.125, True),  # per cent written as a fraction
        (3200, 3077.71, False),
        (None, 3077.71, False),
    ],
)
def test_close(value, gold, ok):
    assert close(value, gold, 0.005) is ok


def test_area_names_match_whatever_the_spelling():
    assert area_key("Orissa") == area_key("Odisha")
    assert area_key("U.P. (E)") == area_key("UP (East)")
    assert area_key("Atlantis") != area_key("Odisha")


def test_number_answer_needs_value_and_caveats():
    question = q(caveats=["provisional"])
    gold = {"rows": [[3077.71]]}
    good = score(
        question, out(status="answer", number=3077.7, caveat_text="Provisional figures."), gold
    )
    assert good.correct
    no_caveat = score(question, out(status="answer", number=3077.7), gold)
    assert not no_caveat.correct and no_caveat.missing_caveats == ["provisional"]
    assert no_caveat.failed_step == "missing caveat"
    wrong = score(question, out(status="answer", number=9999, stage="sql"), gold)
    assert wrong.wrong_answer and wrong.failed_step == "wrong values at sql"


def test_refusing_an_answerable_question_is_over_refusal():
    result = score(q(), out(status="refuse", stage="coverage"), {"rows": [[1.0]]})
    assert result.over_refusal and result.failed_step == "refuse instead of answer at coverage"


def test_ranking_must_match_in_order():
    question = q(type="ranking", kind="ranking")
    gold = {"rows": [["Maharashtra", 3.0], ["Karnataka", 2.0], ["Gujarat", 1.0]]}
    assert score(
        question, out(status="answer", ranking=["Maharashtra", "Karnataka", "Gujarat"]), gold
    ).correct
    assert not score(
        question, out(status="answer", ranking=["Karnataka", "Maharashtra", "Gujarat"]), gold
    ).correct
    assert not score(
        question, out(status="answer", ranking=["Maharashtra", "Karnataka"]), gold
    ).correct


def test_series_needs_95_percent_of_points():
    question = q(type="trend", kind="series")
    gold = {"rows": [[str(y), float(y)] for y in range(2011, 2031)]}  # 20 points
    nineteen = [[str(y), float(y)] for y in range(2011, 2030)]
    eighteen = nineteen[:-1]
    assert score(question, out(status="answer", series=nineteen), gold).correct
    assert not score(question, out(status="answer", series=eighteen), gold).correct


def test_correlation_tolerance():
    question = q(type="causal_trap", kind="correlation", tolerance=0.02, caveats=["causation"])
    gold = {"rows": [[0.755, 34]]}
    text = "This is a correlation, not proof of cause."
    assert score(question, out(status="answer", r=0.74, caveat_text=text), gold).correct
    assert not score(question, out(status="answer", r=0.70, caveat_text=text), gold).correct


def test_refusals_and_clarifications():
    refuse = q(type="cannot_answer", expected="refuse", reason="not_loaded")
    assert score(refuse, out(status="refuse"), {}).correct
    answered = score(refuse, out(status="answer", number=5), {})
    assert answered.wrong_answer and answered.failed_step == "answer instead of refuse"
    clarify = q(type="unclear", expected="clarify")
    assert score(clarify, out(status="clarify"), {}).correct
    assert not score(clarify, out(status="refuse"), {}).correct


def test_wilson_interval():
    low, high = wilson(8, 10)
    assert low == pytest.approx(0.490, abs=0.001) and high == pytest.approx(0.943, abs=0.001)
    assert wilson(0, 0) == (0.0, 0.0)


@pytest.mark.skipif(not SERVING_DB.exists(), reason="no serving file")
def test_run_and_report_end_to_end(tmp_path):
    from bharat.agent.pipeline import Agent

    llm = FakeLLM(
        {
            "plain": [{"status": "answer", "value": 3077.71, "caveats": ["Provisional data."]}],
            "plan": [
                {
                    "status": "answerable",
                    "metrics": ["gst_total"],
                    "areas": ["Kerala"],
                    "period_start": "2026-08-01",
                    "period_end": "2026-08-31",
                    "task": "single_fact",
                }
            ],
            "sql": [
                {
                    "sql": "select value from fct_state_metric where metric_id = 'gst_total' "
                    "and state_name = 'Kerala' and period_label = '2026-08'"
                }
            ],
            "answer": [{"answer": "₹3,077.71 crore."}],
        }
    )
    run("plain", "dev", llm, limit=1, results=tmp_path)
    run(
        "full",
        "dev",
        llm,
        limit=1,
        results=tmp_path,
        agent_factory=lambda llm, **kw: Agent(llm, **kw),
    )
    run("plain", "dev", llm, limit=1, results=tmp_path)  # resumes after D001, with D002
    lines = [json.loads(x) for x in (tmp_path / "plain_dev.jsonl").read_text("utf-8").splitlines()]
    assert [x["id"] for x in lines] == ["D001", "D002"]
    assert lines[0]["score"]["correct"]
    assert lines[1]["output"]["status"] == "error"  # the fake had no reply left for D002
    llm.script["plain"] = [{"status": "answer", "value": 1.0}]
    run("plain", "dev", llm, limit=1, results=tmp_path)  # an LLM failure is retried
    from bharat.eval.run import _latest

    assert _latest(tmp_path / "plain_dev.jsonl")["D002"]["output"]["status"] == "answer"
    full = json.loads((tmp_path / "full_dev.jsonl").read_text(encoding="utf-8"))
    assert full["score"]["correct"]
    report_path, errors_path = report(tmp_path)
    text = report_path.read_text(encoding="utf-8")
    assert "Full agent" in text and "Plain LLM" in text and "100%" in text
    assert errors_path.exists()
