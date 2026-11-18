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
INK = "#14263D"
PAGE_SIZE = 15

CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Source+Sans+3:wght@400;500;600;700&family=Source+Serif+4:opsz,wght@8..60,600;8..60,700&display=swap');
.stApp {{ background: #F6F7F9; font-family: 'Source Sans 3', 'Segoe UI', sans-serif; }}
[data-testid="stHeader"] {{ background: transparent; }}
.block-container {{ padding-top: 2rem; max-width: 1160px; }}
[data-testid="stSidebar"] {{ background: #FFFFFF; border-right: 1px solid #E3E8EF; }}
[data-testid="stSidebarNav"] a {{ border-radius: 8px; }}
[class*="st-key-card-"] {{
  background: #FFFFFF; border: 1px solid #E3E8EF; border-radius: 12px;
  padding: 1.1rem 1.3rem;
}}
h1, h2, h3 {{ color: {INK}; }}

/* Page header: white, a serif headline, plain figures, an optional drawing */
.hero {{ background: #FFFFFF; border: 1px solid #E3E8EF; border-top: 4px solid {BRAND};
  border-radius: 12px; padding: 1.7rem 2rem 1.5rem; margin-bottom: 1.4rem;
  display: flex; gap: 2rem; align-items: center; justify-content: space-between; }}
.hero .eyebrow {{ color: {BRAND}; font-size: 0.8rem; font-weight: 700; letter-spacing: 0.09em;
  text-transform: uppercase; margin-bottom: 0.35rem; }}
.hero h1 {{ font-family: 'Source Serif 4', Georgia, serif; color: {INK}; font-size: 2.2rem;
  font-weight: 700; line-height: 1.2; margin: 0 0 0.5rem; padding: 0; }}
.hero p {{ color: #3E4C5E; font-size: 1.08rem; line-height: 1.6; margin: 0; max-width: 44rem; }}
.hero .art {{ flex: none; }}
.figures {{ display: flex; flex-wrap: wrap; margin-top: 1.2rem; }}
.figures div {{ padding: 0 1.4rem; border-left: 1px solid #E3E8EF; }}
.figures div:first-child {{ padding-left: 0; border-left: none; }}
.figures b {{ display: block; font-family: 'Source Serif 4', Georgia, serif; font-size: 1.45rem;
  color: {INK}; line-height: 1.2; }}
.figures span {{ color: {MUTED}; font-size: 0.86rem; }}
@media (max-width: 900px) {{ .hero .art {{ display: none; }} }}

/* Section titles and the "how it works" steps */
.section {{ font-family: 'Source Serif 4', Georgia, serif; font-weight: 600; color: {INK};
  font-size: 1.35rem; margin: 1.8rem 0 0.15rem; }}
.section-lead {{ color: {MUTED}; font-size: 0.98rem; margin: 0 0 0.9rem; }}
.step {{ display: flex; gap: 0.85rem; align-items: flex-start; }}
.step .num {{ flex: none; width: 2rem; height: 2rem; border-radius: 50%;
  border: 2px solid {BRAND}; color: {BRAND}; font-weight: 700; display: flex;
  align-items: center; justify-content: center; }}
.step b {{ display: block; color: {INK}; margin-bottom: 0.1rem; }}
.step span {{ color: {MUTED}; font-size: 0.94rem; line-height: 1.45; }}

/* Topic cards: white, with a line icon on a soft colour tile */
[class*="st-key-topic-"] {{ background: #FFFFFF; border: 1px solid #E3E8EF; border-radius: 12px;
  padding: 1.1rem 1.15rem 1.15rem; height: 100%; transition: box-shadow 0.15s; }}
[class*="st-key-topic-"]:hover {{ box-shadow: 0 4px 14px rgba(20, 38, 61, 0.08); }}
.tile {{ width: 2.6rem; height: 2.6rem; border-radius: 10px; display: flex; align-items: center;
  justify-content: center; }}
.tile svg {{ width: 1.35rem; height: 1.35rem; fill: none; stroke: currentColor; stroke-width: 1.8;
  stroke-linecap: round; stroke-linejoin: round; }}
.topic-title {{ font-weight: 700; font-size: 1.05rem; color: {INK}; margin: 0.7rem 0 0.15rem; }}
.topic-text {{ color: {MUTED}; font-size: 0.93rem; line-height: 1.45; min-height: 2.75rem; }}
[class*="st-key-topic-"] button {{ background: #F6F7F9; border: 1px solid #E3E8EF;
  border-radius: 8px; justify-content: flex-start; padding: 0.55rem 0.8rem; min-height: 3.6rem; }}
[class*="st-key-topic-"] button p {{ white-space: normal; text-align: left; font-size: 0.92rem;
  color: #2B3A4D; }}
[class*="st-key-topic-"] button:hover {{ border-color: {BRAND}; background: #FFFFFF; }}
[class*="st-key-topic-"] button:hover p {{ color: {BRAND}; }}

/* Question box */
.st-key-card-question textarea {{ font-size: 1.05rem; border-radius: 8px; }}
[data-testid="stForm"] {{ border: none; padding: 0; }}
button[kind="primaryFormSubmit"], button[kind="primary"] {{ border-radius: 8px;
  padding: 0.5rem 1.5rem; font-weight: 600; }}

/* Answers */
.label {{ font-size: 0.8rem; font-weight: 700; color: {BRAND}; letter-spacing: 0.06em;
  text-transform: uppercase; margin-bottom: 0.3rem; }}
.asked {{ color: {MUTED}; font-size: 0.95rem; margin-bottom: 0.7rem; font-style: italic; }}
.st-key-card-answer {{ border-left: 5px solid {BRAND}; }}
.st-key-card-refusal {{ border-left: 5px solid #B7791F; }}
.st-key-card-clarify {{ border-left: 5px solid #6B4FBB; }}
.st-key-card-error {{ border-left: 5px solid #B42318; }}
.note {{ background: #FFF8EB; border: 1px solid #F0DDB5; border-radius: 8px;
  padding: 0.75rem 1rem; color: #5C4300; font-size: 0.95rem; margin: 0.7rem 0; }}
.note ul {{ margin: 0.3rem 0 0 1.1rem; padding: 0; }}
.source {{ display: inline-block; border: 1px solid #DCE4EE; border-radius: 6px;
  padding: 0.2rem 0.7rem; font-size: 0.88rem; margin: 0.3rem 0.35rem 0 0; color: {MUTED}; }}
.source a {{ color: {BRAND}; text-decoration: none; font-weight: 600; }}
.stTabs [data-baseweb="tab"] {{ font-weight: 600; }}

.lead {{ color: {MUTED}; font-size: 1.05rem; margin-top: -0.6rem; margin-bottom: 1rem; }}
.small {{ color: {MUTED}; font-size: 0.86rem; }}
.big-number {{ font-family: 'Source Serif 4', Georgia, serif; color: {BRAND}; font-size: 2rem;
  font-weight: 700; line-height: 1.2; padding-bottom: 0.35rem; }}
.answer {{ font-size: 1.18rem; line-height: 1.6; color: {INK}; }}
.pill {{ display: inline-block; padding: 0.1rem 0.55rem; border-radius: 999px;
  background: #E8EEF6; color: {BRAND}; font-size: 0.8rem; margin-right: 0.3rem; }}
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


def header(title: str, lead: str, figures: tuple[tuple[str, str], ...] = (), art: str = "") -> None:
    """The header at the top of every page. Text here is ours, never the user's."""
    numbers = "".join(f"<div><b>{value}</b><span>{label}</span></div>" for value, label in figures)
    st.markdown(
        '<div class="hero"><div><div class="eyebrow">India Public Data Agent</div>'
        f"<h1>{title}</h1><p>{lead}</p>"
        + (f'<div class="figures">{numbers}</div>' if numbers else "")
        + "</div>"
        + (f'<div class="art">{art}</div>' if art else "")
        + "</div>",
        unsafe_allow_html=True,
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
