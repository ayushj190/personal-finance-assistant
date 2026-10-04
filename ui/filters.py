from datetime import date, datetime, timedelta
import sqlite3
from textwrap import dedent
from typing import Any
import streamlit as st

from config import DB_PATH
from db import database


def render_sidebar_filters() -> dict[str, Any]:
    st.sidebar.header("🪙 PFA Finance")
    st.sidebar.subheader("Filters")

    # Date range preset
    date_preset = st.sidebar.selectbox(
        "Date Range",
        options=["MTD", "Last Month", "Last 3 Months", "YTD", "Last 12 Months", "All Time"],
        index=2,
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
    accounts = conn.execute("SELECT id, name, institution, asset_class, currency FROM accounts ORDER BY institution, name").fetchall()
    
    # Calculate balances for each account and filter
    valid_accounts = []
    for a in accounts:
        # Get latest balance from snapshots or transactions
        row = conn.execute(
            "SELECT balance_eur_minor FROM account_snapshots WHERE account_id = ? ORDER BY snapshot_date DESC LIMIT 1",
            (a["id"],),
        ).fetchone()
        
        if row:
            bal_eur = row["balance_eur_minor"] / 100.0
        else:
            tx_sum = conn.execute(
                "SELECT SUM(amount_eur_minor) AS total FROM transactions WHERE account_id = ?",
                (a["id"],),
            ).fetchone()
            bal_eur = (tx_sum["total"] or 0) / 100.0

        # Keep if balance is non-zero, or if it's an eToro account
        if bal_eur != 0 or "etoro" in a["institution"].lower():
            # Create a dict that can be modified, since fetchall() returns row objects
            a_dict = dict(a)
            a_dict["balance"] = bal_eur
            valid_accounts.append(a_dict)

    conn.close()

    acc_options = {a["id"]: f"{a['institution']} - {a['name']} (€{a['balance']:,.2f})" for a in valid_accounts}
    selected_account_ids = st.sidebar.multiselect(
        "Accounts",
        options=list(acc_options.keys()),
        format_func=lambda x: acc_options[x],
        default=list(acc_options.keys()),
    )

    include_transfers = st.sidebar.toggle("Include internal transfers", value=False)

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
