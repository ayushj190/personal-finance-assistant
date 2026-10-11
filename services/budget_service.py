import sqlite3
from typing import Any
import pandas as pd
from datetime import date

from config import DB_PATH
from db import database
import streamlit as st


def init_budget_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS category_budgets (
            category_id       INTEGER PRIMARY KEY REFERENCES categories(id),
            monthly_limit_eur REAL NOT NULL
        );
        """
    )


def get_all_category_budgets(conn: sqlite3.Connection) -> dict[int, float]:
    init_budget_table(conn)
    rows = conn.execute("SELECT category_id, monthly_limit_eur FROM category_budgets").fetchall()
    return {r["category_id"]: float(r["monthly_limit_eur"]) for r in rows}


def set_category_budget(conn: sqlite3.Connection, category_id: int, monthly_limit_eur: float) -> None:
    init_budget_table(conn)
    with conn:
        conn.execute(
            """
            INSERT INTO category_budgets (category_id, monthly_limit_eur)
            VALUES (?, ?)
            ON CONFLICT(category_id) DO UPDATE SET monthly_limit_eur = excluded.monthly_limit_eur
            """,
            (category_id, monthly_limit_eur),
        )


@st.cache_data(ttl=300)
def calculate_budget_variance(
    _conn: sqlite3.Connection,
    year_month: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, Any]:
    init_budget_table(_conn)
    target_month = year_month or date.today().strftime("%Y-%m")

    # Fetch all expense categories with parent info
    categories = _conn.execute(
        """
        SELECT c.id, c.name, c.kind, c.parent_id, COALESCE(b.monthly_limit_eur, 0.0) as budget_eur
        FROM categories c
        LEFT JOIN category_budgets b ON b.category_id = c.id
        WHERE c.kind IN ('fixed', 'discretionary')
        ORDER BY c.parent_id IS NOT NULL, c.name ASC
        """
    ).fetchall()

    children_map: dict[int, list[int]] = {}
    for cat in categories:
        p_id = cat["parent_id"]
        if p_id is not None:
            children_map.setdefault(p_id, []).append(cat["id"])

    # Fetch actual spending in this date range or calendar month
    if start_date and end_date:
        spend_rows = _conn.execute(
            """
            SELECT category_id, SUM(-amount_eur_minor) / 100.0 as spent_eur
            FROM transactions
            WHERE is_internal_transfer = 0
              AND amount_eur_minor < 0
              AND booking_date >= ? AND booking_date <= ?
            GROUP BY category_id
            """,
            (start_date, end_date),
        ).fetchall()
    else:
        spend_rows = _conn.execute(
            """
            SELECT category_id, SUM(-amount_eur_minor) / 100.0 as spent_eur
            FROM transactions
            WHERE is_internal_transfer = 0
              AND amount_eur_minor < 0
              AND strftime('%Y-%m', booking_date) = ?
            GROUP BY category_id
            """,
            (target_month,),
        ).fetchall()

    direct_spend = {r["category_id"]: float(r["spent_eur"]) for r in spend_rows if r["category_id"]}

    rows = []
    total_budget = 0.0
    total_spent = 0.0

    for cat in categories:
        c_id = cat["id"]
        c_name = cat["name"]
        budget = float(cat["budget_eur"])
        p_id = cat["parent_id"]

        if p_id is None:
            spent = direct_spend.get(c_id, 0.0) + sum(direct_spend.get(sub_id, 0.0) for sub_id in children_map.get(c_id, []))
            total_budget += budget
            total_spent += spent
        else:
            spent = direct_spend.get(c_id, 0.0)
            if budget > 0:
                total_budget += budget

        pct = (spent / budget * 100.0) if budget > 0 else (100.0 if spent > 0 else 0.0)
        remaining = budget - spent if budget > 0 else 0.0

        if budget == 0:
            status = "Unbudgeted"
        elif spent > budget:
            status = "⚠️ Over Budget"
        elif spent >= budget * 0.85:
            status = "🟡 Near Limit"
        else:
            status = "✅ On Track"

        rows.append({
            "category_id": c_id,
            "category": c_name,
            "is_parent": p_id is None,
            "parent_id": p_id,
            "kind": cat["kind"].title(),
            "budget_eur": budget,
            "spent_eur": spent,
            "remaining_eur": remaining,
            "pct_used": pct,
            "status": status,
        })

    df = pd.DataFrame(rows)
    return {
        "month": target_month,
        "total_budget_eur": total_budget,
        "total_spent_eur": total_spent,
        "variance_eur": total_budget - total_spent,
        "categories_df": df,
    }


def calculate_12_month_runway_forecast(
    liquid_cash: float,
    projected_monthly_income: float,
    current_burn_rate: float,
    budgeted_burn_rate: float,
    horizon_months: int = 12,
) -> list[dict[str, Any]]:
    """Generates monthly balance trajectories for current vs budgeted spending."""
    forecast = []
    cur_bal = liquid_cash
    bud_bal = liquid_cash

    today = date.today()
    for m in range(1, horizon_months + 1):
        m_label = f"Month {m}"
        cur_bal = cur_bal + projected_monthly_income - current_burn_rate
        bud_bal = bud_bal + projected_monthly_income - budgeted_burn_rate

        forecast.append({
            "month_idx": m,
            "month_label": m_label,
            "current_spend_balance_eur": round(max(0.0, cur_bal), 2),
            "budgeted_spend_balance_eur": round(max(0.0, bud_bal), 2),
        })

    return forecast
