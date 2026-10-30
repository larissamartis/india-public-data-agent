"""Method and limits: how an answer is made, how it was tested, and what it can't do."""

import streamlit as st

from bharat.app.ui import card, header

header(
    "Method and limits",
    "The language model handles language. Code handles everything that has to be right: "
    "what data exists, what SQL may run, and whether every number in the answer is real.",
)

STEPS = [
    ("Plan", "model", "Turns the question into measures, places, periods and a task."),
    ("Coverage check", "code", "Refuses, saying what is available, if the data doesn't exist."),
    ("SQL", "model", "Writes one query, guided by worked examples from the development set."),
    (
        "Safety check",
        "code",
        "Read-only, known tables only, no averaging of ratios; up to two repairs.",
    ),
    ("Maths", "code", "Correlations (Pearson and Spearman, with n) are computed, not guessed."),
    ("Answer", "model", "About 80 words, written only from the result table."),
    ("Number check", "code", "Every number must appear in the results; otherwise a template."),
    ("Caveats and chart", "code", "Rules add the warnings each measure needs, and pick a chart."),
]

with card("steps"):
    st.markdown("**How an answer is made**")
    for number, (name, who, what) in enumerate(STEPS, start=1):
        st.markdown(
            f'{number}. **{name}** <span class="pill">{who}</span> {what}', unsafe_allow_html=True
        )
    st.caption(
        "Questions are treated as untrusted. The coverage check, safety check and number check "
        "are code, so a cleverly worded question cannot talk its way past them."
    )

left, right = st.columns(2)
with left, card("warehouse"):
    st.markdown("**The warehouse**")
    st.markdown(
        "- Sources are downloaded by scripts or from fingerprinted files, checked against "
        "data contracts, and stored unchanged.\n"
        "- dbt builds one long table of state figures with official names, units and periods, "
        "plus coverage and revision tables, with tests that states add up to All-India.\n"
        "- Measures are defined once, in a MetricFlow semantic layer, including how each one "
        "may be combined across states.\n"
        "- The app reads one small DuckDB file, rebuilt by a workflow."
    )
with right, card("benchmark"):
    st.markdown("**The benchmark**")
    st.markdown(
        "- 155 questions: 100 for development and 55 held back for testing. Every test run is "
        "counted and reported.\n"
        "- Answers come from SQL run on the same data, and 26 were checked by hand against "
        "the original files.\n"
        "- Three setups answer the same questions: a plain model with no data, the agent "
        "without its metrics layer, and the full agent.\n"
        "- Ranges are 95% Wilson intervals, because the samples are small."
    )

with card("limits"):
    st.markdown("**Limits**")
    st.markdown(
        "- **Coverage.** GST, state income, banking, projected population and mobile "
        "subscribers only. Payments (NPCI), prices and surveys are not loaded.\n"
        "- **Definitions.** GST is provisional and counted where the taxpayer is registered. "
        "Population figures are 2019 projections from Census 2011, not counts. Telecom figures "
        "are by service area, not state.\n"
        "- **Correlation is not cause.** The agent reports how measures move together and "
        "says it cannot show cause.\n"
        "- **Free models.** Answers depend on free-tier models that are sometimes busy; the "
        "agent says when it couldn't answer reliably rather than guessing.\n"
        "- **Revisions.** Sources revise past figures, so an answer can change after a "
        "rebuild. The Sources page lists what changed."
    )
