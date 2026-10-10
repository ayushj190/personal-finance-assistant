from datetime import date, timedelta
from typing import Any
import streamlit as st

from config import DB_PATH
from db import database


def render_filters(title: str = "Filters") -> dict[str, Any]:
    with st.popover(f"🔍 {title}"):
        # Date range preset
        date_preset = st.selectbox(
            "Date Range",
            options=["Last 3 Months", "MTD", "Last Month",
                     "YTD", "Last 12 Months", "All Time"],
            index=0,
        )

    today = date.today()
    start_date = None
    end_date = today

    if date_preset == "MTD":
        start_date = today.replace(day=1)
    elif date_preset == "Last Month":
        first_this_month = today.replace(day=1)
        prev_month_end = first_this_month - timedelta(days=1)
        start_date = prev_month_end.replace(day=1)
        end_date = prev_month_end
    elif date_preset == "Last 3 Months":
        start_date = today - timedelta(days=90)
    elif date_preset == "YTD":
        start_date = today.replace(month=1, day=1)
    elif date_preset == "Last 12 Months":
        start_date = today - timedelta(days=365)
    elif date_preset == "All Time":
        start_date = None

    conn = database.connect(DB_PATH)
    accounts = [dict(r) for r in conn.execute(
        "SELECT id, name, institution, currency FROM accounts WHERE is_active = 1 ORDER BY institution, name"
    ).fetchall()]
    conn.close()

    acc_options: dict[int, str] = {0: "All Accounts"}
    for a in accounts:
        acc_options[a["id"]] = f"{a['institution']} - {a['name']}"

    selected_account_id = st.selectbox(
        "Account",
        options=list(acc_options.keys()),
        format_func=lambda x: acc_options[x],
        index=0,
    )
    selected_account_ids = None if selected_account_id == 0 else [
        selected_account_id]

    include_transfers = st.toggle(
        "Include internal transfers", value=False)

    return {
        "start_date": start_date,
        "end_date": end_date,
        "account_ids": selected_account_ids,
        "include_transfers": include_transfers,
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
