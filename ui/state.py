from typing import Any
import streamlit as st


class K:
    """Namespaced constants for Streamlit session state keys."""

    # Global / Theme / Privacy
    THEME = "theme"
    PRIVACY_HIDDEN = "hide_amounts"
    GLOBAL_PRIVACY_TOGGLE = "global_privacy_toggle"
    LAST_AUTO_SYNC = "_last_auto_sync"
    STALE_NOTIFIED = "stale_notified"

    # Copilot & Forms
    COPILOT_HISTORY = "copilot_history"
    COPILOT_ACTIVE_TASK = "copilot_active_task"
    PENDING_COPILOT_PROMPT = "pending_copilot_prompt"
    PENDING_FORM = "pending_form"
    COPILOT_FILE_UPLOADER = "copilot_file_uploader"

    # Dashboard
    DASHBOARD_SANKEY_DRILLDOWN = "dashboard_sankey_drilldown_state"

    # Investments
    TV_WATCHLIST_MINIMIZED = "tv_watchlist_minimized"
    INVESTMENTS_EXP_DIM = "investments_exp_dim"

    # Spending
    SPENDING_DRILLDOWN = "spending_donut_drilldown"

    # Transactions
    TX_SELECT_ALL_FLAG = "tx_select_all_flag"
    TX_EDITOR_VERSION = "tx_editor_version"


def get(key: str, default: Any = None) -> Any:
    """Retrieve value from st.session_state."""
    if not hasattr(st, "session_state"):
        return default
    return st.session_state.get(key, default)


def set(key: str, value: Any) -> None:
    """Assign value into st.session_state."""
    if hasattr(st, "session_state"):
        st.session_state[key] = value


def has(key: str) -> bool:
    """Check if key exists in st.session_state."""
    if not hasattr(st, "session_state"):
        return False
    return key in st.session_state


def delete(key: str) -> None:
    """Remove key from st.session_state if present."""
    if hasattr(st, "session_state") and key in st.session_state:
        del st.session_state[key]


def pop(key: str, default: Any = None) -> Any:
    """Pop key from st.session_state."""
    if hasattr(st, "session_state"):
        return st.session_state.pop(key, default)
    return default


def setdefault(key: str, default: Any) -> Any:
    """Set default value in st.session_state if not present."""
    if hasattr(st, "session_state"):
        return st.session_state.setdefault(key, default)
    return default


def init_defaults() -> None:
    """Initialize standard session state defaults once in app.py."""
    if not hasattr(st, "session_state"):
        return

    if K.THEME not in st.session_state:
        st.session_state[K.THEME] = "dark"

    if K.PRIVACY_HIDDEN not in st.session_state:
        st.session_state[K.PRIVACY_HIDDEN] = True

    if K.GLOBAL_PRIVACY_TOGGLE in st.session_state:
        st.session_state[K.PRIVACY_HIDDEN] = bool(st.session_state[K.GLOBAL_PRIVACY_TOGGLE])
    else:
        st.session_state[K.GLOBAL_PRIVACY_TOGGLE] = bool(st.session_state[K.PRIVACY_HIDDEN])

    if K.COPILOT_HISTORY not in st.session_state:
        st.session_state[K.COPILOT_HISTORY] = []
