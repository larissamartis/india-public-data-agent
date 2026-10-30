"""India Public Data Agent: run with `uv run streamlit run app/streamlit_app.py`."""

import streamlit as st

from bharat.app.ui import style

st.set_page_config(page_title="India Public Data Agent", page_icon="📊", layout="wide")
style()

pages = [
    st.Page("views/ask.py", title="Ask", icon=":material/chat:", default=True),
    st.Page("views/benchmark.py", title="Benchmark results", icon=":material/fact_check:"),
    st.Page("views/sources.py", title="Data sources and coverage", icon=":material/database:"),
    st.Page("views/method.py", title="Method and limits", icon=":material/menu_book:"),
]
with st.sidebar:
    st.markdown("### India Public Data Agent")
    st.caption("Answers about India's states from official data, with the SQL and sources.")
page = st.navigation(pages, position="sidebar")
page.run()
