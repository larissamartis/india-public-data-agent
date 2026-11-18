"""Ask: a question in, an answer out with chart, table, SQL, caveats and sources."""

import html
import os
import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st

from bharat.agent.pipeline import Agent, AgentResult
from bharat.app.ui import (
    card,
    chart_from_spec,
    database,
    header,
    paginate,
    plain,
    query,
    section,
    show_chart,
)

MAX_QUESTIONS = 10  # per visit, to keep the free model quota for everyone
MAX_CHARS = 300
KEYS = ("GEMINI_API_KEY", "GROQ_API_KEY")
# Simple line icons (24 x 24, drawn with strokes) for the topic cards.
ICONS = {
    "receipt": '<path d="M6 3h12v18l-3-2-3 2-3-2-3 2z"/><path d="M9 8h6M9 12h6M9 16h3"/>',
    "growth": '<path d="M3 17l6-6 4 4 8-8"/><path d="M15 7h6v6"/>',
    "bank": '<path d="M3 10l9-6 9 6"/><path d="M5 10v8M9.5 10v8M14.5 10v8M19 10v8"/>'
    '<path d="M3 20h18"/>',
    "phone": '<rect x="7" y="2.5" width="10" height="19" rx="2"/><path d="M11 18h2"/>',
    "trend": '<path d="M3 3v18h18"/><path d="M7 15l4-5 3 3 5-6"/>',
    "stop": '<circle cx="12" cy="12" r="9"/><path d="M5.6 5.6l12.8 12.8"/>',
}
# Each topic card: icon, tile colour, icon colour, title, what it covers, and a question to try
# (each one is from the benchmark).
TOPICS = (
    (
        "receipt",
        "#E7EEF8",
        "#1D4E89",
        "GST collections",
        "How much tax each state collects, month by month.",
        "Which five states collected the most GST in August 2026?",
    ),
    (
        "growth",
        "#E4F3EA",
        "#1F7A4D",
        "State economy",
        "The size of each state's economy, and income per person, year by year.",
        "Rank the top five states or UTs by GSDP at current prices in 2022-23.",
    ),
    (
        "bank",
        "#FBF0DC",
        "#9A6510",
        "Banking",
        "Bank branches, deposits and loans in each state.",
        "Which five states or UTs had the highest credit-deposit ratio at end-March 2025?",
    ),
    (
        "phone",
        "#EEE9F8",
        "#5B3FA8",
        "Mobile phones",
        "Mobile connections in each telecom circle, month by month.",
        "How many wireless subscribers did the Delhi service area add between August and "
        "September 2026?",
    ),
    (
        "trend",
        "#E2F2F4",
        "#17707D",
        "Changes over time",
        "How a figure has moved over the years, drawn as a line.",
        "Show Kerala's bank deposits at end-March for each year from 2015 to 2025.",
    ),
    (
        "stop",
        "#F9E6E4",
        "#A53A2C",
        "When it says no",
        "If the data isn't there, it tells you so. It never makes up a number.",
        "What is the literacy rate of Rajasthan?",
    ),
)
EXAMPLES = tuple(topic[5] for topic in TOPICS)
STEPS = (
    ("Ask", "Pick a question below, or type your own in everyday words."),
    (
        "We look it up",
        "The figures come straight from government data, and every number is checked.",
    ),
    ("Read the answer", "A short answer with a chart, the table, and a link to each source."),
)
# A small drawing for the page header: columns and a trend line, in the page's colours.
ART = """<svg width="250" height="150" viewBox="0 0 250 150" role="img"
aria-label="A column chart with a rising line">
<rect x="0" y="0" width="250" height="150" rx="12" fill="#F3F6FA"/>
<path d="M24 124H226" stroke="#C9D3E0" stroke-width="1.5"/>
<rect x="36" y="88" width="22" height="36" rx="3" fill="#C9D9EE"/>
<rect x="72" y="70" width="22" height="54" rx="3" fill="#A9C2E2"/>
<rect x="108" y="78" width="22" height="46" rx="3" fill="#C9D9EE"/>
<rect x="144" y="52" width="22" height="72" rx="3" fill="#7FA3D1"/>
<rect x="180" y="34" width="22" height="90" rx="3" fill="#1D4E89"/>
<path d="M47 74L83 58L119 64L155 40L191 22" fill="none" stroke="#D08A1E" stroke-width="2.5"
stroke-linecap="round" stroke-linejoin="round"/>
<g fill="#FFFFFF" stroke="#D08A1E" stroke-width="2.5">
<circle cx="47" cy="74" r="4"/><circle cx="83" cy="58" r="4"/><circle cx="119" cy="64" r="4"/>
<circle cx="155" cy="40" r="4"/><circle cx="191" cy="22" r="4"/></g>
</svg>"""
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
    """Fill the box and ask straight away."""
    st.session_state["question"] = text
    st.session_state["ask_now"] = True


def _asked(result: AgentResult) -> None:
    st.markdown(
        f'<div class="asked">You asked: “{html.escape(result.question)}”</div>',
        unsafe_allow_html=True,
    )


def _sources(result: AgentResult) -> None:
    built = result.data_version.split("|")[0][:10] if result.data_version else ""
    chips = "".join(
        f'<span class="source"><a href="{html.escape(s["url"])}" target="_blank">'
        f"{html.escape(s['name'])}</a> · {html.escape(s['publisher'])}</span>"
        for s in result.sources
    )
    if chips:
        st.markdown(
            f'<div class="label" style="margin-top:0.8rem">Where this comes from</div>{chips}',
            unsafe_allow_html=True,
        )
    if built:
        st.markdown(f'<p class="small">Data last updated {built}.</p>', unsafe_allow_html=True)


def show(result: AgentResult) -> None:
    if result.status == "answer":
        with card("answer"):
            _asked(result)
            st.markdown('<div class="label">Answer</div>', unsafe_allow_html=True)
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
                items = "".join(f"<li>{html.escape(c['text'])}</li>" for c in result.caveats)
                st.markdown(
                    f'<div class="note"><b>Worth knowing</b><ul>{items}</ul></div>',
                    unsafe_allow_html=True,
                )
            _sources(result)
        chart = chart_from_spec(result.chart, result.columns, result.rows)
        tabs = st.tabs(
            [
                ":material/bar_chart: Chart",
                ":material/table: Table",
                ":material/code: SQL",
                ":material/route: How it was answered",
            ]
        )
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
            _asked(result)
            st.markdown(f"**I can't answer that from this data.** {REASONS.get(result.reason, '')}")
            st.markdown(plain(result.answer))
            st.caption("The topic cards above show the data it has.")
    elif result.status == "clarify":
        with card("clarify"):
            _asked(result)
            st.markdown("**Could you say a bit more?**")
            st.markdown(plain(result.answer))
    else:
        with card("error"):
            _asked(result)
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


def _figures() -> tuple[tuple[str, str], ...]:
    try:
        row = query(
            "select (select count(distinct state_code) from coverage where state_code > 0),"
            " (select count(*) from dim_metric), (select count(*) from dim_source),"
            " (select built_at from build_info)"
        ).iloc[0]
    except Exception:  # the header still shows without its numbers
        return ()
    return (
        (str(row.iloc[0]), "states and UTs"),
        (str(row.iloc[1]), "measures"),
        (str(row.iloc[2]), "official publishers"),
        (f"{(built := pd.Timestamp(row.iloc[3])).day} {built:%b %Y}", "last updated"),
    )


header(
    "Questions about India's states, answered from official data",
    "GST, the economy, banking, population and mobile phones, for every state and UT. Ask in "
    "your own words and you get a short answer, a chart and the source. If the data can't "
    "answer, it says so.",
    _figures(),
    ART,
)

agent = _agent()
if agent is None:
    st.warning(
        "Asking needs a free Gemini or Groq API key, which isn't set up here. "
        "The benchmark, sources and method pages work without one."
    )

with card("how"):
    for column, (number, (title, text)) in zip(
        st.columns(3), enumerate(STEPS, start=1), strict=True
    ):
        column.markdown(
            f'<div class="step"><div class="num">{number}</div>'
            f"<div><b>{title}</b><span>{text}</span></div></div>",
            unsafe_allow_html=True,
        )

section("What you can ask about", "Click a question to try it.")
for first in (0, 3):
    for column, number in zip(st.columns(3), range(first, first + 3), strict=True):
        icon, tile, ink, title, text, example = TOPICS[number]
        with column, st.container(key=f"topic-{number}"):
            st.markdown(
                f'<div class="tile" style="background:{tile};color:{ink}">'
                f'<svg viewBox="0 0 24 24" aria-hidden="true">{ICONS[icon]}</svg></div>'
                f'<div class="topic-title">{title}</div><div class="topic-text">{text}</div>',
                unsafe_allow_html=True,
            )
            st.button(
                example,
                key=f"example_{number}",
                on_click=_use_example,
                args=(example,),
                width="stretch",
                disabled=agent is None,
            )

section("Or ask your own question")
with card("question"), st.form("ask", border=False):
    st.text_area(
        "Your question",
        key="question",
        max_chars=MAX_CHARS,
        height=90,
        label_visibility="collapsed",
        placeholder="For example: How did Bihar's GSDP at constant prices change from 2014-15 "
        "to 2023-24?",
    )
    asked = st.form_submit_button("Get the answer →", type="primary", disabled=agent is None)

asked = st.session_state.pop("ask_now", False) or asked
question = st.session_state.get("question", "")
count = st.session_state.get("asked_count", 0)
if asked and agent is not None and question.strip():
    if count >= MAX_QUESTIONS:
        st.info(f"That's {MAX_QUESTIONS} questions for this visit. Reload the page to ask more.")
    else:
        with st.spinner("Finding the official figures and checking the numbers…"):
            st.session_state["result"] = agent.ask(question.strip()[:MAX_CHARS])
        st.session_state["asked_count"] = count + 1
        st.session_state["answer_rows"] = 1

if "result" in st.session_state:
    show(st.session_state["result"])
