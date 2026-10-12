from datetime import datetime
from ui.pages import (
    dashboard,
    investments,
    mortgage,
    settings,
    spending,
    transactions,
    tax,
)
import importlib
import streamlit as st

from db import database
from config import DB_PATH
from ui import theme
importlib.reload(theme)

# Initialize page config
st.set_page_config(
    page_title="Personal Finance Assistant",
    page_icon="🪙",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Synchronize theme state
if "theme" not in st.session_state:
    st.session_state["theme"] = "dark"

# Privacy / Mask amounts toggle state
if "hide_amounts" not in st.session_state:
    st.session_state["hide_amounts"] = True

if "global_privacy_toggle" in st.session_state:
    st.session_state["hide_amounts"] = bool(
        st.session_state["global_privacy_toggle"])
else:
    st.session_state["global_privacy_toggle"] = bool(
        st.session_state["hide_amounts"])


# Apply styling and database migrations
database.migrate()
theme.register_plotly_theme()
theme.inject_custom_css()

from db.repositories.account_repository import AccountRepository
from services.task_coordinator import coordinator


def _run_bg_sync() -> None:
    try:
        from services.sync_service import sync_all
        bg_conn = database.connect(DB_PATH)
        try:
            sync_all(bg_conn)
        finally:
            bg_conn.close()
    except Exception:
        pass


def _trigger_auto_sync() -> None:
    coordinator.submit("bg_sync", _run_bg_sync)


now = datetime.now()
if "_last_auto_sync" not in st.session_state:
    st.session_state["_last_auto_sync"] = now
    _trigger_auto_sync()
elif (now - st.session_state["_last_auto_sync"]).total_seconds() >= 600:
    st.session_state["_last_auto_sync"] = now
    _trigger_auto_sync()


@st.fragment(run_every=600)
def _auto_sync_scheduler() -> None:
    current_time = datetime.now()
    last = st.session_state.get("_last_auto_sync")
    if last is None or (current_time - last).total_seconds() >= 600:
        st.session_state["_last_auto_sync"] = current_time
        _trigger_auto_sync()


_auto_sync_scheduler()

# Check for manual accounts reminder
conn = database.connect(DB_PATH)
try:
    stale_accounts = AccountRepository.get_manual_stale_accounts(conn, days_threshold=30)
finally:
    conn.close()


if stale_accounts and "stale_notified" not in st.session_state:
    st.toast(
        f"Reminder: Update your manual accounts ({', '.join(stale_accounts)}).", icon="📝")
    st.session_state["stale_notified"] = True

# Navigation definition: all 7 pages with Settings as the last tab
settings_page = st.Page(
    settings.render,
    title="Settings",
    icon=":material/settings:",
    url_path="settings",
    visibility="hidden",
)
pages = [
    st.Page(dashboard.render, title="Dashboard",
            icon=":material/dashboard:", url_path="dashboard", default=True),
    st.Page(spending.render, title="Spending",
            icon=":material/payments:", url_path="spending"),
    st.Page(investments.render, title="Investments",
            icon=":material/monitoring:", url_path="investments"),
    st.Page(mortgage.render, title="Mortgage",
            icon=":material/real_estate_agent:", url_path="mortgage"),
    st.Page(transactions.render, title="Transactions",
            icon=":material/swap_horiz:", url_path="transactions"),
    st.Page(tax.render, title="Tax Analysis",
            icon=":material/account_balance:", url_path="tax"),
    settings_page,
]
active_page = st.navigation(pages, position="top")

# Global sidebar
with st.sidebar:
    from ui.copilot_sidebar import render_copilot_sidebar
    render_copilot_sidebar()

# Top navbar 3-dots menu (Options / Settings / Privacy toggle)
with st.container(key="top_navbar_actions"):
    with st.popover("", icon=":material/more_vert:", help="Options"):
        st.page_link(settings_page, label="Settings", icon=":material/settings:")
        st.divider()
        from ui.components import render_privacy_toggle
        render_privacy_toggle()

# Render active main page
active_page.run()
