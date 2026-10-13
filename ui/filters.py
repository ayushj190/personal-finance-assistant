from datetime import date, timedelta
from typing import Any
import streamlit as st

from config import DB_PATH
from db import database
from services.date_scope import CUSTOM_PRESET, PRESETS, resolve_date_scope
from ui import state


def _on_filter_change() -> None:
    """Persist the filter widget state so a run without the widget keeps the scope."""
    preset = st.session_state.get("flt_preset", PRESETS[0])
    updated = {"preset": preset}
    if preset == CUSTOM_PRESET:
        updated["custom_start"] = st.session_state.get("flt_custom_start")
        updated["custom_end"] = st.session_state.get("flt_custom_end")
    else:
        # A preset clears any prior custom override.
        st.session_state.pop("flt_custom_start", None)
        st.session_state.pop("flt_custom_end", None)
    st.session_state[state.K.FILTER_STATE] = updated


def render_filters(title: str = "Filters") -> dict[str, Any]:
    conn = database.connect(DB_PATH)
    accounts = [dict(r) for r in conn.execute(
        "SELECT id, name, institution, currency FROM accounts WHERE is_active = 1 ORDER BY institution, name"
    ).fetchall()]
    conn.close()

    acc_options: dict[int, str] = {0: "All Accounts"}
    for a in accounts:
        acc_options[a["id"]] = f"{a['institution']} - {a['name']}"

    # Persistent filter state; the Copilot intent can write it (AC-3, AC-19).
    flt = state.setdefault(state.K.FILTER_STATE, {"preset": PRESETS[0]})
    # Copy the persistent value into the widget keys so a run without the widget
    # does not wipe it, and an intent write takes effect.
    st.session_state["flt_preset"] = flt.get("preset", PRESETS[0])
    if flt.get("custom_start") is not None:
        st.session_state["flt_custom_start"] = flt["custom_start"]
    if flt.get("custom_end") is not None:
        st.session_state["flt_custom_end"] = flt["custom_end"]

    with st.popover(f"🔍 {title}", width="stretch"):
        # Date range preset
        date_preset = st.selectbox(
            "Date Range",
            options=PRESETS + [CUSTOM_PRESET],
            key="flt_preset",
            on_change=_on_filter_change,
        )
        if date_preset == CUSTOM_PRESET:
            st.date_input("Start date", key="flt_custom_start", on_change=_on_filter_change)
            st.date_input("End date", key="flt_custom_end", on_change=_on_filter_change)
        selected_account_id = st.selectbox(
            "Account",
            options=list(acc_options.keys()),
            format_func=lambda x: acc_options[x],
            key="flt_account",
        )
        include_transfers = st.toggle(
            "Include internal transfers", key="flt_transfers"
        )

    if date_preset == CUSTOM_PRESET:
        scope_input: Any = {
            "start": st.session_state.get("flt_custom_start"),
            "end": st.session_state.get("flt_custom_end"),
        }
    else:
        scope_input = {"preset": date_preset}

    resolved = resolve_date_scope(scope_input)
    start_date = resolved.get("start")
    end_date = resolved.get("end") or date.today()

    selected_account_ids = None if selected_account_id == 0 else [
        selected_account_id]


    return {
        "start_date": start_date,
        "end_date": end_date,
        "account_ids": selected_account_ids,
        "include_transfers": include_transfers,
        "preset": date_preset,
        "resolved": resolved,
    }


def build_where_clause(filters: dict[str, Any], table_alias: str = "t") -> tuple[str, list[Any]]:
    clauses: list[str] = []
    params: list[Any] = []

    prefix = f"{table_alias}." if table_alias else ""

    if filters.get("start_date"):
        clauses.append(f"{prefix}booking_date >= ?")
        params.append(filters["start_date"].isoformat())

    if filters.get("end_date"):
        clauses.append(f"{prefix}booking_date <= ?")
        params.append(filters["end_date"].isoformat())

    if filters.get("account_ids"):
        placeholders = ",".join("?" for _ in filters["account_ids"])
        clauses.append(f"{prefix}account_id IN ({placeholders})")
        params.extend(filters["account_ids"])

    if not filters.get("include_transfers"):
        clauses.append(f"{prefix}is_internal_transfer = 0")

    where_sql = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    return where_sql, params
