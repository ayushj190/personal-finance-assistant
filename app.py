from datetime import datetime, date
from ui.pages import (
    dashboard,
    investments,
    mortgage,
    settings,
    spending,
    transactions,
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

# Synchronize theme state before rendering or injecting styles
if "theme" not in st.session_state:
    st.session_state["theme"] = "dark"

if "global_theme_toggle" in st.session_state:
    st.session_state["theme"] = "light" if st.session_state["global_theme_toggle"] else "dark"
else:
    st.session_state["global_theme_toggle"] = (
        st.session_state["theme"] == "light")

if "hide_amounts" not in st.session_state:
    st.session_state["hide_amounts"] = True

if "global_privacy_toggle" in st.session_state:
    st.session_state["hide_amounts"] = bool(
        st.session_state["global_privacy_toggle"])
else:
    st.session_state["global_privacy_toggle"] = bool(
        st.session_state["hide_amounts"])


def _on_theme_toggle() -> None:
    st.session_state["theme"] = "light" if st.session_state["global_theme_toggle"] else "dark"


def _on_privacy_toggle() -> None:
    st.session_state["hide_amounts"] = bool(
        st.session_state["global_privacy_toggle"])


# Apply styling and database migrations
database.migrate()
theme.register_plotly_theme()
theme.inject_custom_css()


conn = database.connect(DB_PATH)
last_sync_row = conn.execute(
    "SELECT started_at FROM sync_log ORDER BY started_at DESC LIMIT 1").fetchone()
last_sync_time = ""
if last_sync_row:
    started_at = last_sync_row["started_at"]
    if "T" in started_at:
        last_sync_time = f" ({started_at.split('T')[1][:5]})"
    elif " " in started_at:
        last_sync_time = f" ({started_at.split(' ')[1][:5]})"

# Check for manual accounts reminder
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

# Navigation definition
settings_page = st.Page(settings.render, title="Settings",
                        icon="⚙️", url_path="settings")
pages = [
    st.Page(dashboard.render, title="Dashboard",
            icon="📊", url_path="dashboard", default=True),
    st.Page(spending.render, title="Spending", icon="🛒", url_path="spending"),
    st.Page(investments.render, title="Investments",
            icon="📈", url_path="investments"),
    st.Page(mortgage.render, title="Mortgage", icon="🏠", url_path="mortgage"),
    st.Page(transactions.render, title="Transactions",
            icon="📝", url_path="transactions"),
    settings_page,
]

all_pages = pages
nav = st.navigation(all_pages, position="hidden")

# Global sidebar preferences and navigation
with st.sidebar:
    st.markdown("<h3 style='margin-top: 0rem; margin-bottom: 1rem;'>Personal Finance Assistant</h3>",
                unsafe_allow_html=True)
    with st.expander("🧭 Menu & Settings", expanded=not st.session_state.get("copilot_is_thinking", False)):
        for p in pages:
            st.page_link(p, label=p.title, icon=p.icon)

        st.divider()
        st.toggle(
            "🔒 Hide Values",
            key="global_privacy_toggle",
            on_change=_on_privacy_toggle,
            help="Globally hide financial numbers with currency symbol and ****",
        )
        st.toggle(
            "☀️ Light Mode",
            key="global_theme_toggle",
            on_change=_on_theme_toggle,
            help="Switch between Dark and Light mode",
        )
        if st.button(f"🔄 Sync{last_sync_time}", help="Sync all banks and brokers", use_container_width=True):
            with st.spinner("Syncing..."):
                from services.sync_service import sync_all
                c = database.connect(DB_PATH)
                sync_all(c)
                c.close()
                st.rerun()

    from ui.copilot_sidebar import render_copilot_sidebar
    render_copilot_sidebar()

nav.run()
