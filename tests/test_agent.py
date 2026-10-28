"""The agent pipeline, run on the committed serving file with a scripted fake LLM."""

import json
from datetime import date

import httpx
import pytest

from bharat.agent.catalog import SERVING_DB, connect
from bharat.agent.gate import check
from bharat.agent.llm import FakeLLM, OpenAICompatibleLLM, Provider, parse_json
from bharat.agent.pipeline import Agent
from bharat.agent.plan import Plan
from bharat.agent.support import correlation, worked_examples
from bharat.eval.questions import load_questions

pytestmark = pytest.mark.skipif(not SERVING_DB.exists(), reason="no serving file")
TODAY = date(2026, 10, 28)

KERALA_AUG = {
    "status": "answerable",
    "interpretation": "Kerala's total GST collection in August 2026.",
    "metrics": ["gst_total"],
    "areas": ["Kerala"],
    "period_start": "2026-08-01",
    "period_end": "2026-08-31",
    "task": "single_fact",
}
KERALA_SQL = {
    "sql": "select value from fct_state_metric where metric_id = 'gst_total' "
    "and state_name = 'Kerala' and period_label = '2026-08'"
}


@pytest.fixture(scope="module")
def con():
    connection = connect()
    yield connection
    connection.close()


def agent(con, script, tmp_path=None):
    return Agent(FakeLLM(script), con=con, cache_dir=tmp_path, today=TODAY)


def plan(**fields):
    return Plan.model_validate({"status": "answerable", "task": "single_fact", **fields})


def test_single_fact_end_to_end(con):
    result = agent(
        con,
        {
            "plan": [KERALA_AUG],
            "sql": [KERALA_SQL],
            "answer": [{"answer": "Kerala collected ₹3,077.71 crore of GST in August 2026."}],
        },
    ).ask("What was Kerala's total GST collection in August 2026?")
    assert result.status == "answer"
    assert result.rows == [[pytest.approx(3077.71, abs=0.01)]]
    assert [c["id"] for c in result.caveats] == ["provisional"]
    assert result.sources[0]["source_id"] == "gst"
    assert result.llm_calls == 3 and not result.template_answer


def test_rejected_sql_is_repaired(con):
    result = agent(
        con,
        {
            "plan": [KERALA_AUG],
            "sql": [{"sql": "select * from secrets"}, KERALA_SQL],
            "answer": [{"answer": "₹3,077.71 crore."}],
        },
    ).ask("Kerala GST August 2026?")
    attempts = [t for t in result.trace if t["step"] == "sql"]
    assert len(attempts) == 2 and "guard" in attempts[0]["problem"]
    assert result.status == "answer"


def test_sql_that_never_works_gives_up(con):
    bad = {"sql": "drop table fct_state_metric"}
    result = agent(con, {"plan": [KERALA_AUG], "sql": [bad, bad, bad]}).ask("Kerala GST?")
    assert result.status == "error" and "won't guess" in result.answer


def test_invented_numbers_fall_back_to_a_template(con):
    made_up = {"answer": "Kerala collected ₹9,999 crore."}
    result = agent(
        con, {"plan": [KERALA_AUG], "sql": [KERALA_SQL], "answer": [made_up, made_up]}
    ).ask("Kerala GST August 2026?")
    assert result.template_answer
    assert "3,077.71" in result.answer


def test_averaging_a_ratio_is_rejected(con):
    plan_reply = {
        **KERALA_AUG,
        "metrics": ["per_capita_nsdp_current"],
        "areas": [],
        "period_start": "2022-04-01",
        "period_end": "2023-03-31",
        "task": "group",
    }
    averaged = {
        "sql": "select avg(value) as value from fct_state_metric "
        "where metric_id = 'per_capita_nsdp_current' and period_label = '2022-23'"
    }
    summed = {
        "sql": "select max(value) as value from fct_state_metric "
        "where metric_id = 'per_capita_nsdp_current' and period_label = '2022-23'"
    }
    result = agent(
        con,
        {"plan": [plan_reply], "sql": [averaged, summed], "answer": lambda p: {"answer": "Done."}},
    ).ask("Average per capita income?")
    first = next(t for t in result.trace if t["step"] == "sql")
    assert "averages ratio" in first["problem"]


def test_cannot_answer_refuses_without_writing_sql(con):
    result = agent(
        con,
        {"plan": [{"status": "cannot_answer", "reason": "not_loaded", "interpretation": "UPI."}]},
    ).ask("UPI value in Karnataka?")
    assert result.status == "refuse" and result.reason == "not_loaded"
    assert "GST" in result.answer  # says what is available
    assert result.llm_calls == 1


def test_unclear_asks_back(con):
    reply = {"status": "unclear", "clarifying_question": "Which measure do you mean?"}
    result = agent(con, {"plan": [reply]}).ask("How is Kerala doing?")
    assert result.status == "clarify" and result.answer == "Which measure do you mean?"


def test_unknown_metric_is_refused(con):
    result = agent(con, {"plan": [{**KERALA_AUG, "metrics": ["upi_value"]}]}).ask("UPI?")
    assert result.status == "refuse" and result.reason == "not_loaded"


def test_cache_returns_the_same_answer_without_llm_calls(con, tmp_path):
    script = {
        "plan": [KERALA_AUG],
        "sql": [KERALA_SQL],
        "answer": [{"answer": "₹3,077.71 crore."}],
    }
    first = agent(con, script, tmp_path)
    first.ask("Kerala GST August 2026?")
    second = agent(con, {}, tmp_path).ask("  kerala GST   august 2026? ")
    assert second.cached and second.answer == "₹3,077.71 crore."


def test_correlation_is_computed_in_code(con):
    reply = {
        "status": "answerable",
        "metrics": ["scb_offices", "population"],
        "areas": [],
        "period_start": "2025-03-31",
        "period_end": "2025-12-31",
        "task": "correlation",
        "causal": True,
    }
    sql = {
        "sql": "select o.state_name, o.value as x, p.value as y from fct_state_metric o "
        "join fct_state_metric p on p.state_code = o.state_code and p.metric_id = 'population' "
        "and p.period_label = '2025' where o.metric_id = 'scb_offices' "
        "and o.period_label = '2025-03-31'"
    }

    def answer(prompt):
        stats = json.loads(prompt.split("Computed statistics: ")[1])
        return {"answer": f"Correlation {stats['pearson']:.2f} across {stats['n']} states."}

    result = agent(con, {"plan": [reply], "sql": [sql], "answer": answer}).ask(
        "Do more people mean more bank offices?"
    )
    assert result.status == "answer" and result.stats["n"] >= 30
    assert "causation" in [c["id"] for c in result.caveats]
    assert result.chart["kind"] == "scatter"


# ---------------------------------------------------------------- the coverage gate


@pytest.mark.parametrize(
    ("fields", "reason", "caveat"),
    [
        (
            dict(
                metrics=["scb_deposits"],
                areas=["Ladakh"],
                period_start="2015-03-31",
                period_end="2015-03-31",
            ),
            "wrong_area",
            "ladakh_in_jk",
        ),
        (
            dict(
                metrics=["gst_total"],
                areas=["Mumbai"],
                period_start="2026-08-01",
                period_end="2026-08-31",
            ),
            "wrong_area",
            None,
        ),
        (
            dict(
                metrics=["wireless_subscribers"],
                areas=["Jharkhand"],
                period_start="2026-09-01",
                period_end="2026-09-30",
            ),
            "wrong_area",
            "service_area",
        ),
        (
            dict(
                metrics=["gst_total"],
                areas=["Kerala"],
                period_start="2026-10-01",
                period_end="2026-10-31",
            ),
            "not_published",
            None,
        ),
        (
            dict(
                metrics=["population"],
                areas=["Goa"],
                period_start="2040-01-01",
                period_end="2040-12-31",
            ),
            "out_of_range",
            None,
        ),
        (
            dict(
                metrics=["scb_deposits"],
                areas=["Maharashtra"],
                period_start="2024-09-30",
                period_end="2024-09-30",
            ),
            "wrong_grain",
            None,
        ),
        (
            dict(
                metrics=["scb_credit"],
                areas=["Chhattisgarh"],
                period_start="1999-03-31",
                period_end="1999-03-31",
            ),
            "out_of_range",
            "state_formed",
        ),
        (
            dict(
                metrics=["gst_total"],
                areas=["Bihar"],
                period_start="2017-03-01",
                period_end="2017-03-31",
            ),
            "out_of_range",
            None,
        ),
        (dict(metrics=["gst_total"], causal=True, task="change"), "causal_claim", "causation"),
    ],
)
def test_gate_refuses(con, fields, reason, caveat):
    from bharat.agent.catalog import Catalog

    gate = check(plan(**fields), Catalog(con), today=TODAY)
    assert (gate.status, gate.reason) == ("refuse", reason)
    if caveat:
        assert caveat in gate.caveats


def test_gate_maps_old_uts_to_the_merged_ut(con):
    from bharat.agent.catalog import Catalog

    gate = check(
        plan(
            metrics=["scb_deposits"],
            areas=["Daman and Diu"],
            period_start="2023-03-31",
            period_end="2023-03-31",
        ),
        Catalog(con),
        today=TODAY,
    )
    assert gate.status == "proceed"
    assert gate.areas[0].state_code == 38 and "dnh_merged" in gate.caveats


def test_gate_flags_a_state_before_it_was_formed(con):
    from bharat.agent.catalog import Catalog

    gate = check(
        plan(
            metrics=["gsdp_current"],
            areas=["Telangana"],
            period_start="2012-04-01",
            period_end="2013-03-31",
        ),
        Catalog(con),
        today=TODAY,
    )
    assert gate.status == "proceed" and "state_formed" in gate.caveats


def test_gate_accepts_old_names(con):
    from bharat.agent.catalog import Catalog

    gate = check(
        plan(
            metrics=["gsdp_current"],
            areas=["Orissa"],
            period_start="2013-04-01",
            period_end="2014-03-31",
        ),
        Catalog(con),
        today=TODAY,
    )
    assert gate.status == "proceed" and gate.areas[0].name == "Odisha"


# ---------------------------------------------------------------- pieces


def test_worked_examples_never_come_from_the_test_split():
    test_sql = {q.gold_sql.strip() for q in load_questions("test") if q.gold_sql}
    for task in ("single_fact", "ranking", "change", "scaled", "combine", "trend", "group"):
        examples = worked_examples(task)
        assert examples and not {sql for _, sql in examples} & test_sql


def test_correlation_maths():
    rows = [("a", 1, 2), ("b", 2, 4), ("c", 3, 6), ("d", 4, 7)]
    stats = correlation(rows)
    assert stats["n"] == 4 and stats["spearman"] == pytest.approx(1.0)
    assert 0.98 < stats["pearson"] < 1.0


def test_parse_json_accepts_fenced_replies():
    assert parse_json('```json\n{"sql": "select 1"}\n```') == {"sql": "select 1"}


def test_llm_falls_back_to_the_second_provider(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        if "first" in str(request.url):
            return httpx.Response(429, json={"error": "rate limited"})
        body = {"choices": [{"message": {"content": '{"answer": "ok"}'}}]}
        return httpx.Response(200, json=body)

    monkeypatch.setenv("FIRST_KEY", "x")
    monkeypatch.setenv("SECOND_KEY", "y")
    llm = OpenAICompatibleLLM(
        providers=(
            Provider("first", "https://first.test/v1", "m1", "FIRST_KEY"),
            Provider("second", "https://second.test/v1", "m2", "SECOND_KEY"),
        ),
        http=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    assert llm.complete_json("answer", "s", "u") == {"answer": "ok"}
    assert llm.calls[0].provider == "second" and llm.calls[0].fallback
