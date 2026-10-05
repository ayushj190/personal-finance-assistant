import streamlit as st

from db import database
from ui import theme
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

# Apply styling and database migrations
database.migrate()
theme.register_plotly_theme()
theme.inject_custom_css()

# Global sidebar preferences
with st.sidebar:
    st.markdown("### 🪙 PFA Finance")
    hide_vals = st.toggle(
        "🔒 Privacy Mode (Hide Values)",
        value=st.session_state.get("hide_amounts", False),
        key="global_privacy_toggle",
        help="Globally hide financial numbers with currency symbol and ****",
    )
    st.session_state["hide_amounts"] = hide_vals
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

