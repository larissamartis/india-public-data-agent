"""Data sources and coverage: where every figure comes from and which states and periods exist."""

import altair as alt
import streamlit as st

from bharat.app.ui import BRAND, GRAIN_NAMES, card, finish, header, paginate, show_chart, table
from bharat.app.ui import query as _query

header(
    "Data sources and coverage",
    "Four official publishers, loaded into one warehouse with the same state names, units and "
    "periods. The agent checks this coverage before it writes any SQL.",
)

build = _query("select built_at, git_sha, state_rows, national_rows, revisions from build_info")
info = build.iloc[0]
for number, (column, (label, value)) in enumerate(
    zip(
        st.columns(4),
        [
            ("Warehouse built", str(info["built_at"])[:10]),
            ("State rows", f"{int(info['state_rows']):,}"),
            ("All-India rows", f"{int(info['national_rows']):,}"),
            ("Revised since last build", f"{int(info['revisions']):,}"),
        ],
        strict=True,
    )
):
    with column, card(f"stat-{number}"):
        st.markdown(f'<p class="small">{label}</p>', unsafe_allow_html=True)
        st.markdown(f'<div class="big-number">{value}</div>', unsafe_allow_html=True)

sources = _query("select source_id, name, publisher, url, access from dim_source order by 1")
with card("sources"):
    st.markdown("**Sources**")
    for row in sources.itertuples():
        st.markdown(
            f"**[{row.name}]({row.url})**  \n{row.publisher}  \n"
            f'<span class="small">How it is loaded: {row.access}</span>',
            unsafe_allow_html=True,
        )
    st.caption(
        "Manual files are kept on the repository's raw-inputs release, with SHA-256 "
        "fingerprints in data/manifest.yml, so every build reads exactly the same bytes."
    )

metrics = _query(
    """
    select m.label as "Measure", m.unit as "Unit", m.grain as "Time step",
        s.publisher as "Publisher",
        coalesce(cast(min(c.first_period) as varchar), '') as "From",
        coalesce(cast(max(c.last_period) as varchar), '') as "To",
        count(distinct c.state_code) filter (where c.state_code > 0) as "States and UTs"
    from dim_metric m
    join dim_source s using (source_id)
    left join coverage c using (metric_id)
    group by all
    order by "Publisher", "Measure"
    """
)
lsa = _query(
    "select min(period_end) as first, max(period_end) as last, count(distinct service_area) as n "
    "from fct_lsa_metric"
).iloc[0]
with card("metrics"):
    st.markdown("**Measures**")
    metrics["Time step"] = metrics["Time step"].map(lambda g: GRAIN_NAMES.get(g, g))
    table(metrics, height=36 * (len(metrics) + 1) + 4)
    if lsa["n"]:
        st.caption(
            f"Mobile subscribers are published by TRAI for {int(lsa['n'])} telecom service areas, "
            f"not states, from {lsa['first']} to {lsa['last']}."
        )

# Share of each measure's periods that a state has, so gaps stand out whatever the time step.
heat = _query(
    """
    with per_state as (
        select c.state_name as state, m.label as measure, sum(c.periods) as periods
        from coverage c join dim_metric m using (metric_id)
        where c.state_code > 0
        group by all
    )
    select *, periods / max(periods) over (partition by measure) as share from per_state
    """
)
with card("coverage"):
    st.markdown("**Coverage by state** (share of each measure's periods with a figure)")
    if heat.empty:
        st.caption("No state figures loaded.")
    else:
        chart = (
            alt.Chart(heat)
            .mark_rect(cornerRadius=2, stroke="#FFFFFF", strokeWidth=1)
            .encode(
                x=alt.X(
                    "measure:N",
                    title=None,
                    axis=alt.Axis(orient="top", labelAngle=-40, labelOverlap=False),
                ),
                y=alt.Y("state:N", title=None, sort="ascending", axis=alt.Axis(labelOverlap=False)),
                color=alt.Color(
                    "share:Q",
                    title="Share",
                    scale=alt.Scale(domain=[0, 1], range=["#E4ECF5", BRAND]),
                    legend=alt.Legend(format="%"),
                ),
                tooltip=[
                    alt.Tooltip("state:N", title="State or UT"),
                    alt.Tooltip("measure:N", title="Measure"),
                    alt.Tooltip("periods:Q", title="Periods"),
                    alt.Tooltip("share:Q", title="Share", format=".0%"),
                ],
            )
            .properties(height=20 * heat["state"].nunique())
        )
        show_chart(finish(chart))
        st.caption(
            "Lighter cells are states with fewer periods than others, for example because the "
            "state or UT was formed later, or the source doesn't publish it."
        )

revisions = _query(
    """
    select metric_id as "Measure", period_label as "Period", previous_value as "Was",
        new_value as "Now", change_type as "Change"
    from revisions order by 1, 2
    """
)
with card("revisions"):
    st.markdown("**Revisions since the last build**")
    if revisions.empty:
        st.caption("No published figure changed since the last build.")
    else:
        paginate(revisions, key="revisions")

with card("gaps"):
    st.markdown("**Not loaded (yet)**")
    st.markdown(
        "- UPI and other payments by state (NPCI): the site returned server errors when "
        "loading was tried.\n"
        "- Price indices and surveys from MoSPI: needs an account for its API.\n"
        "- Health and literacy indicators (NFHS, Census): not part of this version.\n\n"
        "Questions about these are refused, with a note on what is available instead."
    )
