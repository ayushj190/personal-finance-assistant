import importlib
import streamlit as st

from db import database
from ui import theme
importlib.reload(theme)
from ui.pages import (
    analyst,
    dashboard,
    import_files,
    investments,
    mortgage,
    settings,
    spending,
    transactions,
)

# Initialize page config
st.set_page_config(
    page_title="Personal Finance Assistant",
    page_icon="🪙",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Synchronize theme state before rendering or injecting styles
if "theme" not in st.session_state:
    st.session_state["theme"] = "dark"

if "global_theme_toggle" in st.session_state:
    st.session_state["theme"] = "light" if st.session_state["global_theme_toggle"] else "dark"
else:
    st.session_state["global_theme_toggle"] = (st.session_state["theme"] == "light")

if "hide_amounts" not in st.session_state:
    st.session_state["hide_amounts"] = False

if "global_privacy_toggle" in st.session_state:
    st.session_state["hide_amounts"] = bool(st.session_state["global_privacy_toggle"])
else:
    st.session_state["global_privacy_toggle"] = bool(st.session_state["hide_amounts"])


def _on_theme_toggle() -> None:
    st.session_state["theme"] = "light" if st.session_state["global_theme_toggle"] else "dark"


def _on_privacy_toggle() -> None:
    st.session_state["hide_amounts"] = bool(st.session_state["global_privacy_toggle"])


# Apply styling and database migrations
database.migrate()
theme.register_plotly_theme()
theme.inject_custom_css()

# Global sidebar preferences
with st.sidebar:
    st.markdown("### 🪙 PFA Finance")
    col_t1, col_t2 = st.columns(2)
    with col_t1:
        st.toggle(
            "🔒 Privacy",
            key="global_privacy_toggle",
            on_change=_on_privacy_toggle,
            help="Globally hide financial numbers with currency symbol and ****",
        )
    with col_t2:
        st.toggle(
            "☀️ Light",
            key="global_theme_toggle",
            on_change=_on_theme_toggle,
            help="Switch between Dark and Light mode",
        )

    st.divider()

    from ui.copilot_sidebar import render_copilot_sidebar
    render_copilot_sidebar()
    st.divider()


# Navigation definition
pages = [
    st.Page(dashboard.render, title="Dashboard", icon="📊", url_path="dashboard", default=True),
    st.Page(spending.render, title="Spending", icon="🛒", url_path="spending"),
    st.Page(investments.render, title="Investments", icon="📈", url_path="investments"),
    st.Page(mortgage.render, title="Mortgage", icon="🏠", url_path="mortgage"),
    st.Page(transactions.render, title="Transactions", icon="📝", url_path="transactions"),
    st.Page(import_files.render, title="Import", icon="📥", url_path="import"),
    st.Page(analyst.render, title="AI Analyst", icon="🧠", url_path="analyst"),
    st.Page(settings.render, title="Settings", icon="⚙️", url_path="settings"),
]

nav = st.navigation(pages)
nav.run()

