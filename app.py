from datetime import datetime, date
import threading
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


def _on_privacy_toggle() -> None:
    st.session_state["hide_amounts"] = bool(
        st.session_state["global_privacy_toggle"])


# Apply styling and database migrations
database.migrate()
theme.register_plotly_theme()
theme.inject_custom_css()

# Background automatic sync on startup and every 10 minutes
_sync_lock = threading.Lock()
_is_syncing = False


def _run_bg_sync() -> None:
    global _is_syncing
    if _is_syncing:
        return
    with _sync_lock:
        _is_syncing = True
        try:
            from services.sync_service import sync_all
            bg_conn = database.connect(DB_PATH)
            sync_all(bg_conn)
            bg_conn.close()
        except Exception:
            pass
        finally:
            _is_syncing = False


def _trigger_auto_sync() -> None:
    threading.Thread(target=_run_bg_sync, daemon=True).start()


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
manual_stale = conn.execute("""
    SELECT a.name, MAX(s.snapshot_date) as last_snap
    FROM accounts a
    LEFT JOIN account_snapshots s ON s.account_id = a.id
    WHERE a.provider = 'manual' AND a.is_active = 1
    GROUP BY a.id
""").fetchall()
conn.close()

stale_accounts = []
for r in manual_stale:
    if not r["last_snap"]:
        stale_accounts.append(r["name"])
    else:
        try:
            last_snap = datetime.strptime(
                r["last_snap"][:10], "%Y-%m-%d").date()
            if (date.today() - last_snap).days >= 30:
                stale_accounts.append(r["name"])
        except Exception:
            pass

if stale_accounts and "stale_notified" not in st.session_state:
    st.toast(
        f"Reminder: Update your manual accounts ({', '.join(stale_accounts)}).", icon="📝")
    st.session_state["stale_notified"] = True

# Navigation definition: all 7 pages with Settings as the last tab
pages = [
    st.Page(dashboard.render, title="Dashboard",
            icon="📊", url_path="dashboard", default=True),
    st.Page(spending.render, title="Spending", icon="🛒", url_path="spending"),
    st.Page(investments.render, title="Investments",
            icon="📈", url_path="investments"),
    st.Page(mortgage.render, title="Mortgage", icon="🏠", url_path="mortgage"),
    st.Page(transactions.render, title="Transactions",
            icon="📝", url_path="transactions"),
    st.Page(tax.render, title="Tax Analysis", icon="💶", url_path="tax"),
    st.Page(settings.render, title="Settings", icon="⚙️", url_path="settings"),
]
active_page = st.navigation(pages, position="hidden")

# Global top app bar
with st.container(key="top_app_bar"):
    tabs_col, toggle_col = st.columns([0.84, 0.16])
    with tabs_col:
        tab_cols = st.columns(len(pages))
        for i, p in enumerate(pages):
            with tab_cols[i]:
                st.page_link(p, label=p.title, icon=p.icon)
    with toggle_col:
        st.toggle(
            "Hide values",
            key="global_privacy_toggle",
            on_change=_on_privacy_toggle,
        )

# Global sidebar
with st.sidebar:
    from ui.copilot_sidebar import render_copilot_sidebar
    render_copilot_sidebar()

active_page.run()
