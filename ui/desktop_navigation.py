"""Desktop navigation configuration for the lightweight macOS application."""
import os
import streamlit as st


def is_desktop_mode() -> bool:
    """Return True if running inside standalone desktop packaging."""
    return os.environ.get("PFA_DESKTOP") == "1"


def get_desktop_pages() -> tuple[list[st.Page], st.Page]:
    """Return stripped-down page list for desktop expense tracking (AC-5)."""
    from ui.pages import dashboard, settings, spending, transactions

    settings_page = st.Page(
        settings.render,
        title="Settings",
        icon=":material/settings:",
        url_path="settings",
        visibility="hidden",
    )
    pages = [
        st.Page(
            dashboard.render,
            title="Dashboard",
            icon=":material/dashboard:",
            default=True,
        ),
        st.Page(
            spending.render,
            title="Spending",
            icon=":material/payments:",
            url_path="spending",
        ),
        st.Page(
            transactions.render,
            title="Transactions",
            icon=":material/swap_horiz:",
            url_path="transactions",
        ),
        settings_page,
    ]
    return pages, settings_page
