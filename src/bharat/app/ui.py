"""Look and small helpers shared by every page: one brand colour, white cards on a light grey
page, paginated tables, and charts from the agent's chart spec."""

from __future__ import annotations

import math
import re

import altair as alt
import pandas as pd
import streamlit as st

BRAND = "#1D4E89"
MUTED = "#5B6B7F"
PAGE_SIZE = 15

CSS = f"""
<style>
.stApp {{ background: #F5F7FA; }}
[data-testid="stSidebar"] {{ background: #FFFFFF; border-right: 1px solid #E3E8EF; }}
[class*="st-key-card-"] {{
  background: #FFFFFF; border: 1px solid #E3E8EF; border-radius: 12px;
  padding: 1rem 1.2rem; box-shadow: 0 1px 2px rgba(20, 38, 61, 0.04);
}}
h1, h2, h3 {{ color: #14263D; letter-spacing: -0.01em; }}
.lead {{ color: {MUTED}; font-size: 1.05rem; margin-top: -0.6rem; margin-bottom: 1rem; }}
.small {{ color: {MUTED}; font-size: 0.85rem; }}
.big-number {{ color: {BRAND}; font-size: 2.1rem; font-weight: 700; line-height: 1.1; }}
.answer {{ font-size: 1.12rem; line-height: 1.55; }}
.pill {{ display: inline-block; padding: 0.1rem 0.55rem; border-radius: 999px;
  background: #E8EEF6; color: {BRAND}; font-size: 0.78rem; margin-right: 0.3rem; }}
</style>
"""


@st.cache_resource
def database():
    """One read-only connection to the serving file for the whole app; pages use cursors."""
    from bharat.agent.catalog import connect

    return connect()


def query(sql: str) -> pd.DataFrame:
    cursor = database().cursor()
    try:
        result = cursor.execute(sql)
        return pd.DataFrame(result.fetchall(), columns=[d[0] for d in result.description])
    finally:
        cursor.close()


def style() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def card(name: str):
    """A white card: use as `with card("answer"):`. The key gives the CSS class."""
    return st.container(key=f"card-{name}")


def header(title: str, lead: str) -> None:
    st.title(title)
    st.markdown(f'<p class="lead">{lead}</p>', unsafe_allow_html=True)


_MARKDOWN = re.compile(r"([\\`*_{}\[\]()#+\-.!|~<>$])")


def plain(text: str) -> str:
    """Escape Markdown and HTML, so text from the model or a question shows as typed."""
    return _MARKDOWN.sub(r"\\\1", text or "")


def table(df: pd.DataFrame, **kwargs) -> None:
    try:
        st.dataframe(df, hide_index=True, width="stretch", **kwargs)
    except TypeError:  # older Streamlit
        st.dataframe(df, hide_index=True, use_container_width=True, **kwargs)


def show_chart(chart: alt.Chart) -> None:
    try:
        st.altair_chart(chart, width="stretch")
    except TypeError:  # older Streamlit
        st.altair_chart(chart, use_container_width=True)


def paginate(df: pd.DataFrame, key: str, size: int = PAGE_SIZE) -> pd.DataFrame:
    """Show one page of a long table with Previous and Next; returns that page."""
    pages = max(1, math.ceil(len(df) / size))
    page = min(max(1, st.session_state.get(key, 1)), pages)
    st.session_state[key] = page

    def move(step: int) -> None:
        st.session_state[key] = min(max(1, st.session_state.get(key, 1) + step), pages)

    chunk = df.iloc[(page - 1) * size : page * size]
    table(chunk)
    if pages > 1:
        left, middle, right = st.columns([1, 2, 1])
        left.button("‹ Previous", key=f"{key}_prev", disabled=page <= 1, on_click=move, args=(-1,))
        middle.markdown(
            f'<p class="small" style="text-align:center">Page {page} of {pages} · '
            f"{len(df)} rows</p>",
            unsafe_allow_html=True,
        )
        right.button("Next ›", key=f"{key}_next", disabled=page >= pages, on_click=move, args=(1,))
    return chunk


def chart_from_spec(spec: dict, columns: list[str], rows: list[list]) -> alt.Chart | None:
    """Bar, line or scatter chart for an agent answer, in the brand colour."""
    if not spec or not rows:
        return None
    df = pd.DataFrame(rows, columns=columns)
    x, y = spec["x"], spec["y"]
    if x not in df or y not in df:
        return None
    df[y] = pd.to_numeric(df[y], errors="coerce")
    tooltip = [alt.Tooltip(field=c, type="nominal") for c in columns]
    if spec["kind"] == "bar":
        df[x] = df[x].astype(str)
        chart = (
            alt.Chart(df)
            .mark_bar(color=BRAND, cornerRadiusEnd=3)
            .encode(
                y=alt.Y(field=x, type="nominal", sort="-x", title=None),
                x=alt.X(field=y, type="quantitative", title=y),
                tooltip=tooltip,
            )
            .properties(height=max(180, 24 * len(df)))
        )
    elif spec["kind"] == "line":
        df[x] = df[x].astype(str)
        chart = (
            alt.Chart(df)
            .mark_line(color=BRAND, point=alt.OverlayMarkDef(color=BRAND))
            .encode(
                x=alt.X(field=x, type="ordinal", title=None),
                y=alt.Y(field=y, type="quantitative", title=y),
                tooltip=tooltip,
            )
            .properties(height=320)
        )
    elif spec["kind"] == "scatter":
        df[x] = pd.to_numeric(df[x], errors="coerce")
        chart = (
            alt.Chart(df)
            .mark_circle(color=BRAND, size=80, opacity=0.8)
            .encode(
                x=alt.X(field=x, type="quantitative", title=x),
                y=alt.Y(field=y, type="quantitative", title=y),
                tooltip=tooltip,
            )
            .properties(height=360)
        )
    else:
        return None
    return chart.configure_view(stroke=None).configure_axis(
        labelColor=MUTED, titleColor=MUTED, gridColor="#E9EDF2"
    )
