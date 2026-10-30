"""Benchmark results: how often each setup was right, with uncertainty, and every question."""

import altair as alt
import pandas as pd
import streamlit as st

from bharat.app.ui import BRAND, card, finish, header, paginate, show_chart, table
from bharat.eval.questions import load_questions
from bharat.eval.run import (
    RESULTS,
    _load,
    _pending,
    by_question_type,
    summarise,
    test_run_count,
)

header(
    "Benchmark results",
    "155 fixed questions with answers computed from the data and checked by hand. Each setup "
    "answers the same questions; an answer counts only if the figures, the decision to answer "
    "or refuse, and the required caveats are all right.",
)

data = _load(RESULTS)
rows = summarise(data)
if not rows:
    st.info("No benchmark results yet. Run the Benchmark workflow to create them.")
    st.stop()

splits = sorted({r["split"] for r in rows}, key=["dev", "test"].index)
SPLIT_NAMES = {"dev": "Development set (100 questions)", "test": "Held-out test set (55)"}
if len(splits) > 1:
    split = st.radio("Question set", splits, horizontal=True, format_func=SPLIT_NAMES.get)
else:
    split = splits[0]
    st.markdown(f'<p class="small">{SPLIT_NAMES[split]}</p>', unsafe_allow_html=True)
shown = [r for r in rows if r["split"] == split]
pending = {r["name"]: r["pending"] for r in shown if r["pending"]}
if pending:
    st.warning(
        "Some questions are not answered yet, because the free model quota ran out during the "
        "run: "
        + ", ".join(f"{name} ({count})" for name, count in pending.items())
        + ". They are left out of these scores and answered on the next run, so compare setups "
        "with care until then."
    )

for column, row in zip(st.columns(len(shown)), shown, strict=True):
    with column, card(f"setup-{row['setup']}"):
        st.markdown(f"**{row['name']}**")
        st.markdown(f'<div class="big-number">{row["rate"]:.0%}</div>', unsafe_allow_html=True)
        st.markdown(
            f'<p class="small">{row["correct"]} of {row["n"]} correct · 95% range '
            f"{row['low']:.0%}–{row['high']:.0%}"
            + (f" · {row['pending']} not yet answered" if row["pending"] else "")
            + "</p>",
            unsafe_allow_html=True,
        )

frame = pd.DataFrame(shown)
order = list(frame["name"])
bars = (
    alt.Chart(frame)
    .mark_bar(color="#9DB6D6", cornerRadiusEnd=3, size=24)
    .encode(
        y=alt.Y("name:N", sort=order, title=None),
        x=alt.X(
            "rate:Q",
            title="Share correct",
            axis=alt.Axis(format="%"),
            scale=alt.Scale(domain=[0, 1]),
        ),
        tooltip=[
            alt.Tooltip("name:N", title="Setup"),
            alt.Tooltip("rate:Q", title="Correct", format=".0%"),
            alt.Tooltip("n:Q", title="Questions"),
        ],
    )
)
ranges = (
    alt.Chart(frame)
    .mark_errorbar(color=BRAND, thickness=2.5, ticks=alt.TickConfig(size=14))
    .encode(y=alt.Y("name:N", sort=order), x=alt.X("low:Q", title="Share correct"), x2="high:Q")
)
points = (
    alt.Chart(frame)
    .mark_point(color=BRAND, filled=True, size=90, opacity=1)
    .encode(y=alt.Y("name:N", sort=order), x="rate:Q")
)
with card("chart"):
    st.markdown("**Share correct** (bar and dot), with the 95% Wilson range (line)")
    show_chart(finish((bars + ranges + points).properties(height=64 * len(frame))))
    if split == "test":
        st.caption(f"The test set has been run {test_run_count(RESULTS)} times in total.")

with card("details"):
    st.markdown("**Details**")
    table(
        pd.DataFrame(
            {
                "Setup": frame["name"],
                "Questions": frame["n"],
                "Correct": frame["correct"],
                "Wrong": frame["wrong_answers"],
                "Over-refused": frame["over_refusals"].astype(str)
                + " of "
                + frame["answerable"].astype(str),
                "Caveats": frame["caveats_rate"].map("{:.0%}".format),
                "Calls each": frame["calls"].round(1),
                "Median s": frame["median_seconds"].round(1),
                "Fallbacks": frame["fallbacks"],
            }
        )
    )
    st.caption(
        "Wrong: confident answers with the wrong figures. Over-refused: answerable questions "
        "it refused. Caveats: answers carrying every required warning. Calls each: model "
        "calls per question. Median s: median seconds per question. Fallbacks: calls the "
        "second free model answered because the first was busy."
    )

types = by_question_type(data)
keys = [k for k in types if k[1] == split]
type_names = sorted({t for k in keys for t in types[k]})
with card("types"):
    st.markdown("**By question type**")
    table(
        pd.DataFrame(
            [
                {"Type": t.replace("_", " ")}
                | {
                    next(r["name"] for r in shown if r["setup"] == k[0]): (
                        f"{sum(types[k][t])}/{len(types[k][t])}" if types[k].get(t) else ""
                    )
                    for k in keys
                }
                for t in type_names
            ]
        )
    )

with card("questions"):
    st.markdown("**Every question**")
    text = {q.id: " ".join(q.question.split()) for q in load_questions(split)}
    names = {r["setup"]: r["name"] for r in shown}
    left, right = st.columns([2, 1])
    setup = left.selectbox("Setup", list(names), format_func=names.get, index=len(names) - 1)
    wrong_only = right.toggle("Only wrong ones")
    records = data[(setup, split)]
    table_rows = [
        {
            "ID": r["id"],
            "Type": r["score"]["type"].replace("_", " "),
            "Question": text.get(r["id"], ""),
            "Expected": r["score"]["expected"],
            "Got": r["score"]["status"],
            "Correct": "Not yet answered"
            if _pending(r)
            else ("Yes" if r["score"]["correct"] else "No"),
            "Where it went wrong": r["score"]["failed_step"] or "",
        }
        for r in sorted(records, key=lambda r: r["id"])
        if not (wrong_only and r["score"]["correct"])
    ]
    if table_rows:
        paginate(pd.DataFrame(table_rows), key=f"questions_{setup}_{split}_{wrong_only}")
    else:
        st.caption("Nothing to show.")
