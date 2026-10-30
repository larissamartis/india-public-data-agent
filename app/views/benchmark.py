"""Benchmark results: how often each setup was right, with uncertainty, and every question."""

import altair as alt
import pandas as pd
import streamlit as st

from bharat.app.ui import BRAND, MUTED, card, header, paginate, show_chart, table
from bharat.eval.questions import load_questions
from bharat.eval.run import RESULTS, _load, by_question_type, summarise, test_run_count

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
split = st.radio(
    "Question set",
    splits,
    horizontal=True,
    format_func={"dev": "Development (100)", "test": "Held-out test (55)"}.get,
)
shown = [r for r in rows if r["split"] == split]

for column, row in zip(st.columns(len(shown)), shown, strict=True):
    with column, card(f"setup-{row['setup']}"):
        st.markdown(f"**{row['name']}**")
        st.markdown(f'<div class="big-number">{row["rate"]:.0%}</div>', unsafe_allow_html=True)
        st.markdown(
            f'<p class="small">{row["correct"]} of {row["n"]} correct · 95% range '
            f"{row['low']:.0%}–{row['high']:.0%}</p>",
            unsafe_allow_html=True,
        )

frame = pd.DataFrame(shown)
order = list(frame["name"])
bars = (
    alt.Chart(frame)
    .mark_bar(color=BRAND, cornerRadiusEnd=3, size=26)
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
    .mark_rule(color=MUTED, strokeWidth=2)
    .encode(y=alt.Y("name:N", sort=order), x="low:Q", x2="high:Q")
)
with card("chart"):
    st.markdown("**Share correct, with 95% Wilson interval**")
    show_chart((bars + ranges).properties(height=60 * len(frame)).configure_view(stroke=None))
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
                "Wrong answers": frame["wrong_answers"],
                "Refused answerable questions": frame["over_refusals"].astype(str)
                + " of "
                + frame["answerable"].astype(str),
                "Caveats present": frame["caveats_rate"].map("{:.0%}".format),
                "Model calls per question": frame["calls"].round(1),
                "Median seconds": frame["median_seconds"].round(1),
                "Fallbacks to second model": frame["fallbacks"],
            }
        )
    )
    st.caption(
        "Wrong answers are confident answers with the wrong figures; refusing an answerable "
        "question is counted separately. A fallback means the first free model was busy."
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
            "Correct": "Yes" if r["score"]["correct"] else "No",
            "Where it went wrong": r["score"]["failed_step"] or "",
        }
        for r in sorted(records, key=lambda r: r["id"])
        if not (wrong_only and r["score"]["correct"])
    ]
    if table_rows:
        paginate(pd.DataFrame(table_rows), key=f"questions_{setup}_{split}_{wrong_only}")
    else:
        st.caption("Nothing to show.")
