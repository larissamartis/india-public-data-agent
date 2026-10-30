from pathlib import Path

import pytest

pytest.importorskip("streamlit")

from streamlit.testing.v1 import AppTest  # noqa: E402

from bharat.agent.catalog import SERVING_DB  # noqa: E402
from bharat.agent.llm import FakeLLM  # noqa: E402
from bharat.agent.pipeline import Agent  # noqa: E402
from bharat.app.ui import chart_from_spec, plain  # noqa: E402

pytestmark = pytest.mark.skipif(not SERVING_DB.exists(), reason="no serving file")
VIEWS = Path(__file__).resolve().parents[1] / "app" / "views"

KERALA = "What was Kerala's total GST collection in August 2026?"
SCRIPT = {
    "plan": [
        {
            "status": "answerable",
            "interpretation": "Kerala's total GST collection in August 2026.",
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


def page(name: str) -> AppTest:
    return AppTest.from_file(str(VIEWS / f"{name}.py"), default_timeout=60)


@pytest.mark.parametrize("name", ["benchmark", "sources", "method"])
def test_page_renders(name):
    app = page(name).run()
    assert not app.exception, app.exception


def text_of(app: AppTest) -> str:
    return "\n".join(m.value for m in app.markdown)


def ask(question: str, script: dict) -> AppTest:
    app = page("ask")
    app.session_state["agent"] = Agent(FakeLLM(script), cache_dir=None)
    app.run()
    app.text_area(key="question").input(question)
    next(b for b in app.button if b.label == "Ask").click().run()
    assert not app.exception, app.exception
    return app


def test_ask_shows_answer_sql_caveat_and_source():
    app = ask(KERALA, SCRIPT)
    text = text_of(app)
    assert "3,077" in text
    assert "provisional" in text  # the GST caveat
    assert "GST collections" in text  # the source
    assert "fct_state_metric" in app.code[0].value


def test_ask_explains_a_refusal():
    script = {
        "plan": [
            {
                "status": "cannot_answer",
                "reason": "not_loaded",
                "interpretation": "Literacy rate of Rajasthan.",
                "metrics": [],
                "areas": ["Rajasthan"],
            }
        ]
    }
    app = ask("What is the literacy rate of Rajasthan?", script)
    assert "can't answer that from this data" in text_of(app)
    assert not app.code  # no SQL was run


def test_ask_without_keys_says_so(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    app = page("ask").run()
    assert not app.exception
    assert "API key" in app.warning[0].value


def test_example_button_fills_the_question():
    app = page("ask")
    app.session_state["agent"] = Agent(FakeLLM({}), cache_dir=None)
    app.run()
    app.button(key="example_3").click().run()
    assert app.text_area(key="question").value == "What is the literacy rate of Rajasthan?"


def test_plain_escapes_markdown_and_html():
    assert plain("<b>[x](http://e.test)</b>") == r"\<b\>\[x\]\(http://e\.test\)\</b\>"


def test_chart_from_spec_kinds():
    columns, rows = ["state_name", "value"], [["Kerala", 2.0], ["Goa", 1.0]]
    for kind in ("bar", "line"):
        assert chart_from_spec({"kind": kind, "x": "state_name", "y": "value"}, columns, rows)
    scatter = chart_from_spec(
        {"kind": "scatter", "x": "a", "y": "b"}, ["s", "a", "b"], [["x", 1, 2], ["y", 2, 3]]
    )
    assert scatter is not None
    assert chart_from_spec({"kind": "bar", "x": "nope", "y": "value"}, columns, rows) is None
