import sqlite3
from typing import Any
import pandas as pd
from datetime import date

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

    # Fetch all expense categories with parent info (excluding Uncategorized, defensively deduped)
    categories = _conn.execute(
        """
        SELECT MIN(c.id) as id, c.name, c.kind, c.parent_id, COALESCE(MAX(b.monthly_limit_eur), 0.0) as budget_eur
        FROM categories c
        LEFT JOIN category_budgets b ON b.category_id = c.id
        WHERE c.kind IN ('fixed', 'discretionary')
          AND c.name != 'Uncategorized'
        GROUP BY LOWER(c.name), COALESCE(c.parent_id, -1)
        ORDER BY c.parent_id IS NOT NULL, c.name ASC
        """
    ).fetchall()

    cat_by_id = {cat["id"]: cat for cat in categories}
    children_map: dict[int, list[int]] = {}
    for cat in categories:
        p_id = cat["parent_id"]
        if p_id is not None:
            children_map.setdefault(p_id, []).append(cat["id"])

    # Fetch actual spending in integer minor units (cents)
    if start_date and end_date:
        spend_rows = _conn.execute(
            """
            SELECT category_id, SUM(-amount_eur_minor) as spent_minor
            FROM transactions
            WHERE is_internal_transfer = 0
              AND amount_eur_minor < 0
              AND category_id IS NOT NULL
              AND booking_date >= ? AND booking_date <= ?
            GROUP BY category_id
            """,
            (start_date, end_date),
        ).fetchall()
    else:
        spend_rows = _conn.execute(
            """
            SELECT category_id, SUM(-amount_eur_minor) as spent_minor
            FROM transactions
            WHERE is_internal_transfer = 0
              AND amount_eur_minor < 0
              AND category_id IS NOT NULL
              AND strftime('%Y-%m', booking_date) = ?
            GROUP BY category_id
            """,
            (target_month,),
        ).fetchall()

    direct_spend_minor = {
        int(r["category_id"]): int(r["spent_minor"])
        for r in spend_rows
        if r["category_id"]
    }

    # Branch Rollup Rule:
    # A parent category with explicit B_parent > 0 defines the branch target.
    # If B_parent == 0, the sum of child limits defines the branch target.
    # Parent and child targets are never summed together (eliminates double counting).
    root_categories = [c for c in categories if c["parent_id"] is None or c["parent_id"] not in cat_by_id]
    total_budget_minor = 0
    total_spent_minor = 0
    branch_budget_map: dict[int, int] = {}
    parent_spent_map: dict[int, int] = {}

    for p in root_categories:
        p_id = p["id"]
        p_b_minor = int(round(float(p["budget_eur"]) * 100))
        sub_ids = children_map.get(p_id, [])
        c_b_minor = sum(
            int(round(float(cat_by_id[s]["budget_eur"]) * 100))
            for s in sub_ids
            if s in cat_by_id
        )
        eff_b_minor = p_b_minor if p_b_minor > 0 else c_b_minor
        branch_budget_map[p_id] = eff_b_minor
        total_budget_minor += eff_b_minor

        p_s_minor = direct_spend_minor.get(p_id, 0) + sum(
            direct_spend_minor.get(s, 0) for s in sub_ids
        )
        parent_spent_map[p_id] = p_s_minor
        total_spent_minor += p_s_minor

    rows = []
    for cat in categories:
        c_id = cat["id"]
        c_name = cat["name"]
        p_id = cat["parent_id"]
        is_parent = (p_id is None or p_id not in cat_by_id)

        if is_parent:
            b_minor = branch_budget_map.get(c_id, int(round(float(cat["budget_eur"]) * 100)))
            s_minor = parent_spent_map.get(c_id, direct_spend_minor.get(c_id, 0))
        else:
            b_minor = int(round(float(cat["budget_eur"]) * 100))
            s_minor = direct_spend_minor.get(c_id, 0)

        budget = b_minor / 100.0
        spent = s_minor / 100.0
        remaining = (b_minor - s_minor) / 100.0 if b_minor > 0 else 0.0
        pct = (s_minor / b_minor * 100.0) if b_minor > 0 else (100.0 if s_minor > 0 else 0.0)

        if b_minor == 0:
            status = "Unbudgeted"
        elif s_minor > b_minor:
            status = "⚠️ Over Budget"
        elif s_minor >= int(round(b_minor * 0.85)):
            status = "🟡 Near Limit"
        else:
            status = "✅ On Track"

        rows.append({
            "category_id": c_id,
            "category": c_name,
            "is_parent": is_parent,
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
        "total_budget_eur": total_budget_minor / 100.0,
        "total_spent_eur": total_spent_minor / 100.0,
        "variance_eur": (total_budget_minor - total_spent_minor) / 100.0,
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
