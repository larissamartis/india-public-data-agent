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
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
.stApp {{ background: #F5F7FA; font-family: 'Inter', 'Segoe UI', sans-serif; }}
[data-testid="stHeader"] {{ background: transparent; }}
.block-container {{ padding-top: 2rem; max-width: 1180px; }}
[data-testid="stSidebar"] {{ background: #FFFFFF; border-right: 1px solid #E3E8EF; }}
[data-testid="stSidebarNav"] a {{ border-radius: 8px; }}
[class*="st-key-card-"] {{
  background: #FFFFFF; border: 1px solid #E3E8EF; border-radius: 14px;
  padding: 1.1rem 1.3rem; box-shadow: 0 1px 3px rgba(20, 38, 61, 0.05);
}}
h1, h2, h3 {{ color: #14263D; letter-spacing: -0.01em; }}

/* Page banner */
.hero {{ background: linear-gradient(135deg, {BRAND} 0%, #2F6DB5 100%); border-radius: 18px;
  padding: 1.9rem 2.1rem 1.6rem; margin-bottom: 1.4rem;
  box-shadow: 0 6px 18px rgba(29, 78, 137, 0.18); }}
.hero h1 {{ color: #FFFFFF; font-size: 2.15rem; font-weight: 700; margin: 0 0 0.45rem;
  padding: 0; }}
.hero p {{ color: #DCE7F5; font-size: 1.07rem; line-height: 1.55; margin: 0; max-width: 50rem; }}
.hero .chip {{ display: inline-block; background: rgba(255, 255, 255, 0.14);
  border: 1px solid rgba(255, 255, 255, 0.28); color: #FFFFFF; padding: 0.28rem 0.8rem;
  border-radius: 999px; font-size: 0.86rem; margin: 0.9rem 0.45rem 0 0; }}

/* Section titles and the "how it works" steps */
.section {{ font-weight: 650; color: #14263D; font-size: 1.2rem; margin: 1.6rem 0 0.2rem; }}
.section-lead {{ color: {MUTED}; font-size: 0.95rem; margin: 0 0 0.8rem; }}
.step {{ display: flex; gap: 0.8rem; align-items: flex-start; }}
.step .num {{ flex: none; width: 2.1rem; height: 2.1rem; border-radius: 50%; background: {BRAND};
  color: #FFFFFF; font-weight: 700; display: flex; align-items: center;
  justify-content: center; }}
.step b {{ display: block; color: #14263D; margin-bottom: 0.15rem; }}
.step span {{ color: {MUTED}; font-size: 0.92rem; line-height: 1.45; }}

/* Topic cards, each in its own soft colour */
[class*="st-key-topic-"] {{ border-radius: 16px; padding: 1.05rem 1.15rem 1.1rem;
  border: 1px solid transparent; height: 100%; }}
.st-key-topic-0 {{ background: #EAF1FB; border-color: #D3E1F4; }}
.st-key-topic-1 {{ background: #E8F6EF; border-color: #CDEBDB; }}
.st-key-topic-2 {{ background: #FDF4E3; border-color: #F4E2BC; }}
.st-key-topic-3 {{ background: #F1ECFA; border-color: #E0D5F4; }}
.st-key-topic-4 {{ background: #E5F5F7; border-color: #C9E8EC; }}
.st-key-topic-5 {{ background: #FCECEC; border-color: #F3D2D2; }}
.topic-icon {{ font-size: 1.7rem; line-height: 1; }}
.topic-title {{ font-weight: 650; font-size: 1.05rem; color: #14263D; margin: 0.45rem 0 0.15rem; }}
.topic-text {{ color: #4A5A6E; font-size: 0.9rem; line-height: 1.45; min-height: 2.7rem; }}
[class*="st-key-topic-"] button {{ background: #FFFFFF; border: 1px solid rgba(20, 38, 61, 0.12);
  border-radius: 10px; justify-content: flex-start; padding: 0.55rem 0.8rem;
  min-height: 3.6rem; }}
[class*="st-key-topic-"] button p {{ white-space: normal; text-align: left; font-size: 0.9rem; }}
[class*="st-key-topic-"] button:hover {{ border-color: {BRAND}; color: {BRAND};
  box-shadow: 0 2px 8px rgba(29, 78, 137, 0.12); }}

/* Question box */
.st-key-card-question textarea {{ font-size: 1.02rem; border-radius: 10px; }}
[data-testid="stForm"] {{ border: none; padding: 0; }}
button[kind="primaryFormSubmit"], button[kind="primary"] {{ border-radius: 10px;
  padding: 0.5rem 1.6rem; font-weight: 600; }}

/* Answers */
.label {{ text-transform: uppercase; letter-spacing: 0.07em; font-size: 0.74rem;
  font-weight: 700; color: {BRAND}; margin-bottom: 0.3rem; }}
.asked {{ color: {MUTED}; font-size: 0.92rem; margin-bottom: 0.6rem; }}
.st-key-card-answer {{ border-left: 6px solid {BRAND}; }}
.st-key-card-refusal {{ border-left: 6px solid #C77700; background: #FFFBF3; }}
.st-key-card-clarify {{ border-left: 6px solid #6B4FBB; background: #FAF8FE; }}
.st-key-card-error {{ border-left: 6px solid #B42318; background: #FFF8F7; }}
.note {{ background: #FFF6E5; border: 1px solid #F3DCAE; border-radius: 10px;
  padding: 0.7rem 0.95rem; color: #5C4300; font-size: 0.92rem; margin: 0.6rem 0; }}
.note ul {{ margin: 0.3rem 0 0 1.1rem; padding: 0; }}
.source {{ display: inline-block; background: #F1F5FA; border: 1px solid #DCE4EE;
  border-radius: 999px; padding: 0.2rem 0.75rem; font-size: 0.84rem; margin: 0.3rem 0.35rem 0 0; }}
.source a {{ color: {BRAND}; text-decoration: none; }}
.stTabs [data-baseweb="tab"] {{ font-weight: 600; }}

.lead {{ color: {MUTED}; font-size: 1.05rem; margin-top: -0.6rem; margin-bottom: 1rem; }}
.small {{ color: {MUTED}; font-size: 0.85rem; }}
.big-number {{ color: {BRAND}; font-size: 2rem; font-weight: 700; line-height: 1.2;
  padding-bottom: 0.35rem; }}
.answer {{ font-size: 1.15rem; line-height: 1.6; color: #14263D; }}
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


def header(title: str, lead: str, chips: tuple[str, ...] = ()) -> None:
    """The coloured banner at the top of every page. Text here is ours, never the user's."""
    badges = "".join(f'<span class="chip">{c}</span>' for c in chips)
    st.markdown(
        f'<div class="hero"><h1>{title}</h1><p>{lead}</p>{badges}</div>', unsafe_allow_html=True
    )


def section(title: str, lead: str = "") -> None:
    st.markdown(f'<div class="section">{title}</div>', unsafe_allow_html=True)
    if lead:
        st.markdown(f'<p class="section-lead">{lead}</p>', unsafe_allow_html=True)


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
    return finish(chart)


def finish(chart: alt.Chart) -> alt.Chart:
    """The shared chart look: white background, quiet axes, no border, full labels."""
    return (
        chart.configure(background="#FFFFFF")
        .configure_view(stroke=None)
        .configure_axis(labelColor=MUTED, titleColor=MUTED, gridColor="#E9EDF2", labelLimit=320)
        .configure_legend(labelColor=MUTED, titleColor=MUTED)
    )


GRAIN_NAMES = {
    "month": "Monthly",
    "month_end": "Month end",
    "fy": "Financial year",
    "end_march": "End of March",
    "year_jul1": "1 July each year",
}
