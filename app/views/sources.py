"""Data sources and coverage: where every figure comes from and which states and periods exist."""

import altair as alt
import streamlit as st

from bharat.app.ui import BRAND, card, header, paginate, show_chart, table
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
    table(metrics)
    if lsa["n"]:
        st.caption(
            f"Mobile subscribers are published by TRAI for {int(lsa['n'])} telecom service areas, "
            f"not states, from {lsa['first']} to {lsa['last']}."
        )

heat = _query(
    """
    select c.state_name as state, m.label as measure, sum(c.periods) as periods
    from coverage c join dim_metric m using (metric_id)
    where c.state_code > 0
    group by all
    """
)
with card("coverage"):
    st.markdown("**Coverage by state** (number of periods with a figure)")
    if heat.empty:
        st.caption("No state figures loaded.")
    else:
        chart = (
            alt.Chart(heat)
            .mark_rect(cornerRadius=2)
            .encode(
                x=alt.X("measure:N", title=None, axis=alt.Axis(labelAngle=-35, labelLimit=180)),
                y=alt.Y("state:N", title=None, sort="ascending"),
                color=alt.Color(
                    "periods:Q",
                    title="Periods",
                    scale=alt.Scale(range=["#DCE6F2", BRAND]),
                ),
                tooltip=["state:N", "measure:N", "periods:Q"],
            )
            .properties(height=16 * heat["state"].nunique())
            .configure_view(stroke=None)
        )
        show_chart(chart)

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
