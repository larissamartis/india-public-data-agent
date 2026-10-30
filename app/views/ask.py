"""Ask: a question in, an answer out with chart, table, SQL, caveats and sources."""

import os
import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st

from bharat.agent.pipeline import Agent, AgentResult
from bharat.app.ui import card, chart_from_spec, database, header, paginate, plain, show_chart

MAX_QUESTIONS = 10  # per visit, to keep the free model quota for everyone
MAX_CHARS = 300
KEYS = ("GEMINI_API_KEY", "GROQ_API_KEY")
EXAMPLES = (
    "Which five states collected the most GST in August 2026?",
    "Show Karnataka's monthly total GST collection from April 2025 to March 2026.",
    "What was the credit-deposit ratio of scheduled commercial banks in Tamil Nadu at "
    "end-March 2025?",
    "What is the literacy rate of Rajasthan?",
)
REASONS = {
    "not_loaded": "That data isn't in this warehouse.",
    "out_of_range": "That period is outside the data.",
    "not_published": "That period hasn't been published yet.",
    "wrong_area": "That place isn't covered at this level.",
    "wrong_grain": "The data isn't published at that time step.",
    "causal_claim": "The data can show association, not cause.",
}


def _keys_from_secrets() -> None:
    try:
        for key in KEYS:
            if key in st.secrets and not os.environ.get(key):
                os.environ[key] = st.secrets[key]
    except Exception:  # no secrets file locally
        pass
    os.environ.setdefault("LLM_TIMEOUT", "30")
    os.environ.setdefault("LLM_COOLDOWN", "180")


def _agent() -> Agent | None:
    if "agent" in st.session_state:
        return st.session_state["agent"]
    _keys_from_secrets()
    if not any(os.environ.get(key) for key in KEYS):
        return None
    from bharat.agent.llm import OpenAICompatibleLLM

    cache = Path(tempfile.gettempdir()) / "bharat-answers"
    agent = Agent(OpenAICompatibleLLM(), con=database().cursor(), cache_dir=cache)
    st.session_state["agent"] = agent
    return agent


def _use_example(text: str) -> None:
    st.session_state["question"] = text


def _sources(result: AgentResult) -> None:
    built = result.data_version.split("|")[0][:10] if result.data_version else ""
    lines = [
        f"- [{plain(s['name'])}]({s['url']}) · {plain(s['publisher'])}" for s in result.sources
    ]
    if lines:
        st.markdown("**Sources**\n" + "\n".join(lines))
    if built:
        st.markdown(f'<p class="small">Warehouse built {built}.</p>', unsafe_allow_html=True)


def show(result: AgentResult) -> None:
    if result.status == "answer":
        with card("answer"):
            st.markdown(f'<div class="answer">{plain(result.answer)}</div>', unsafe_allow_html=True)
            stats = result.stats or {}
            if stats.get("pearson") is not None and stats.get("spearman") is not None:
                st.markdown(
                    f'<span class="pill">Pearson r {stats["pearson"]:.2f}</span>'
                    f'<span class="pill">Spearman ρ {stats["spearman"]:.2f}</span>'
                    f'<span class="pill">n = {stats["n"]}</span>',
                    unsafe_allow_html=True,
                )
            if result.caveats:
                st.markdown(
                    "**Read with care**\n"
                    + "\n".join(f"- {plain(c['text'])}" for c in result.caveats)
                )
            _sources(result)
        chart = chart_from_spec(result.chart, result.columns, result.rows)
        tabs = st.tabs(["Chart", "Table", "SQL", "How it was answered"])
        with tabs[0]:
            if chart is not None:
                show_chart(chart)
            else:
                st.caption("A single figure needs no chart; see the table.")
        with tabs[1]:
            paginate(pd.DataFrame(result.rows, columns=result.columns), key="answer_rows")
        with tabs[2]:
            st.code(result.sql or "", language="sql")
            st.caption("Run read-only against the warehouse after an automatic safety check.")
        with tabs[3]:
            _trace(result)
    elif result.status == "refuse":
        with card("refusal"):
            st.markdown(f"**I can't answer that from this data.** {REASONS.get(result.reason, '')}")
            st.markdown(plain(result.answer))
    elif result.status == "clarify":
        with card("clarify"):
            st.markdown("**Could you say a bit more?**")
            st.markdown(plain(result.answer))
    else:
        with card("error"):
            st.markdown(f"**{plain(result.answer)}**")
            st.caption("The free language models may be busy. Please try again in a minute.")


def _trace(result: AgentResult) -> None:
    steps = [t.get("step", "") for t in result.trace]
    st.markdown(
        f"{result.llm_calls} model calls · {result.seconds:.1f} seconds"
        + (" · from cache" if result.cached else "")
        + (" · answer written from a template" if result.template_answer else "")
    )
    st.markdown(" → ".join(dict.fromkeys(s for s in steps if s)) or "No steps recorded.")
    if result.plan:
        st.json(result.plan, expanded=False)


header(
    "Ask about India's states",
    "GST, state income, banking, population and mobile subscribers, from official sources. "
    "Every answer shows its SQL and sources, and the agent says so when the data can't answer.",
)

agent = _agent()
if agent is None:
    st.warning(
        "Asking needs a free Gemini or Groq API key, which isn't set up here. "
        "The benchmark, sources and method pages work without one."
    )

st.markdown('<p class="small">Try one:</p>', unsafe_allow_html=True)
columns = st.columns(len(EXAMPLES))
for column, example in zip(columns, EXAMPLES, strict=True):
    column.button(
        example, key=f"example_{EXAMPLES.index(example)}", on_click=_use_example, args=(example,)
    )

with st.form("ask"):
    question = st.text_area(
        "Your question",
        key="question",
        max_chars=MAX_CHARS,
        height=90,
        placeholder="For example: How did Bihar's GSDP at constant prices change from 2014-15 "
        "to 2023-24?",
    )
    asked = st.form_submit_button("Ask", type="primary", disabled=agent is None)

count = st.session_state.get("asked_count", 0)
if asked and agent is not None and question.strip():
    if count >= MAX_QUESTIONS:
        st.info(f"That's {MAX_QUESTIONS} questions for this visit. Reload the page to ask more.")
    else:
        with st.spinner("Planning, checking coverage, running SQL and checking numbers…"):
            st.session_state["result"] = agent.ask(question.strip()[:MAX_CHARS])
        st.session_state["asked_count"] = count + 1
        st.session_state["answer_rows"] = 1

if "result" in st.session_state:
    show(st.session_state["result"])
