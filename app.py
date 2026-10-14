from datetime import date, datetime
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
import logging_setup
logging_setup.configure()
import streamlit as st

from db import database
from db.migrations import MigrationError
from config import DB_PATH, DEMO
from ui import theme
importlib.reload(theme)

# Initialize page config
st.set_page_config(
    page_title="Personal Finance Assistant",
    page_icon="🪙",
    layout="wide",
    initial_sidebar_state="expanded",
)

from ui import state
state.init_defaults()


# Apply styling and database migrations
try:
    database.migrate()
except MigrationError as exc:
    st.error("Database migration failed. The app will not start until this is resolved.")
    st.error(str(exc))
    st.stop()
theme.register_plotly_theme()
theme.inject_custom_css()
theme.inject_sidebar_resize()

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


def _should_auto_sync() -> bool:
    """Cross session guard: the coordinator singleton remembers the last sync, so
    identical bank and broker calls do not repeat per session (AC-10)."""
    if coordinator.is_running("bg_sync"):
        return False
    last = coordinator.get_state("bg_sync").finished_at
    return last is None or (datetime.now() - last).total_seconds() >= 600


if not DEMO:
    if _should_auto_sync():
        _trigger_auto_sync()

    @st.fragment(run_every=600)
    def _auto_sync_scheduler() -> None:
        if _should_auto_sync():
            _trigger_auto_sync()

    _auto_sync_scheduler()

# Check for manual accounts reminder
conn = database.connect(DB_PATH)
try:
    stale_accounts = AccountRepository.get_manual_stale_accounts(conn, days_threshold=30)
finally:
    conn.close()


if stale_accounts and not state.has(state.K.STALE_NOTIFIED):
    st.toast(
        f"Reminder: Update your manual accounts ({', '.join(stale_accounts)}).", icon="📝")
    state.set(state.K.STALE_NOTIFIED, True)

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
            icon=":material/dashboard:", default=True),
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

# Map canonical page ids to the st.Page objects for the Copilot action layer.
_page_map = {
    "dashboard": pages[0],
    "spending": pages[1],
    "investments": pages[2],
    "mortgage": pages[3],
    "transactions": pages[4],
    "tax": pages[5],
    "settings": settings_page,
}

# Global sidebar
with st.sidebar:
    from ui.copilot_sidebar import render_copilot_sidebar
    render_copilot_sidebar()

# Consume a Copilot navigation intent exactly once, after navigation and before render (AC-19).
from services.date_scope import CUSTOM_PRESET
from services.navigation import FILTERED_PAGES as _FILTERED_PAGES
from ui.state import K as _K

_intent = st.session_state.pop(_K.COPILOT_UI_INTENT, None)
if _intent and _intent.get("page") in _page_map:
    _page_id = _intent["page"]
    _tab = _intent.get("tab")
    _ds = _intent.get("date_scope") or {}
    if _ds.get("requested") and _page_id in _FILTERED_PAGES:
        if _ds.get("preset"):
            st.session_state[_K.FILTER_STATE] = {"preset": _ds["preset"]}
        elif _ds.get("start_iso"):
            st.session_state[_K.FILTER_STATE] = {
                "preset": CUSTOM_PRESET,
                "custom_start": date.fromisoformat(_ds["start_iso"]),
                "custom_end": date.fromisoformat(_ds["end_iso"]),
            }
    if _tab:
        st.session_state[_K.INVESTMENTS_ACTIVE_TAB] = _tab
        st.session_state[_K.INVESTMENTS_TABS_GENERATION] = (
            st.session_state.get(_K.INVESTMENTS_TABS_GENERATION, 0) + 1
        )
    from ui.view_state import apply_view as _apply_view
    _apply_view(_page_id, _intent.get("view"))
    _target = _page_map[_page_id]
    if _target is not active_page:
        st.switch_page(_target)

# A manual page change drops the Copilot panel; a Copilot navigation keeps it (AC-3).
_current_page_id = next(
    (pid for pid, page in _page_map.items() if page is active_page), None
)
_panel = st.session_state.get(_K.COPILOT_PAGE_PANEL)
if _panel and _intent is None and _panel.get("page") != _current_page_id:
    st.session_state.pop(_K.COPILOT_PAGE_PANEL, None)

# Top navbar 3-dots menu (Options / Settings / Privacy toggle)
with st.container(key="top_navbar_actions"):
    with st.popover("", icon=":material/more_vert:", help="Options"):
        st.page_link(settings_page, label="Settings", icon=":material/settings:")
        st.divider()
        from ui.components import render_privacy_toggle
        render_privacy_toggle()

# Render active main page
active_page.run()
