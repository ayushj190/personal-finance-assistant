"""Copilot read only insight tools (AC-7).

Each tool answers through `db.database.connect_readonly`, returns a serializable
dict with `success` and `message`, and reuses a named service rather than adding
new math. A tool that can render a figure also returns a one line `headline` so the
destination page panel has a title.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd

from agent.chart_renderer import render_chart
from agent.tools.spending import (
    tool_get_monthly_cashflow,
    tool_get_spending_by_category,
)
from core.config import DB_PATH
from db import database
from db.repositories import AccountRepository
from services.analytics import calculate_current_net_worth, detect_recurring_charges
from services.budget_service import (
    calculate_3_month_historical_burn_rate,
    calculate_12_month_runway_forecast,
    calculate_budget_variance,
)
from services.date_scope import resolve_date_scope
from services.dividend_service import calculate_dividend_projections


def _period_summary(date_scope: Any, fallback_label: str) -> dict[str, Any]:
    """Spending and cashflow totals over one resolved range (reuses the two tools)."""
    scope = resolve_date_scope(date_scope)
    if scope.get("error"):
        return {"error": scope["error"]}

    spend = tool_get_spending_by_category(date_scope=date_scope)
    cash = tool_get_monthly_cashflow(date_scope=date_scope)

    spending = float(spend.get("total_spent_eur", 0.0) or 0.0)
    income = 0.0
    expenses = 0.0
    for row in cash.get("cashflow", []) or []:
        income += float(row.get("income_eur", 0) or 0)
        expenses += float(row.get("fixed_eur", 0) or 0) + float(
            row.get("discretionary_eur", 0) or 0
        )

    return {
        "label": scope.get("label") or fallback_label,
        "start": scope.get("start_iso"),
        "end": scope.get("end_iso"),
        "spending_eur": round(spending, 2),
        "income_eur": round(income, 2),
        "expenses_eur": round(expenses, 2),
    }


def tool_compare_periods(range_a: Any = None, range_b: Any = None) -> dict[str, Any]:
    """Compare spending and cashflow totals across two date ranges (AC-7)."""
    a = _period_summary(range_a, "range A")
    if a.get("error"):
        return {"success": False, "message": f"Range A: {a['error']}"}
    b = _period_summary(range_b, "range B")
    if b.get("error"):
        return {"success": False, "message": f"Range B: {b['error']}"}

    delta = round(b["spending_eur"] - a["spending_eur"], 2)
    direction = "more" if delta > 0 else ("less" if delta < 0 else "the same")
    df = pd.DataFrame(
        [
            {
                "period": a["label"],
                "spending_eur": a["spending_eur"],
                "income_eur": a["income_eur"],
                "expenses_eur": a["expenses_eur"],
            },
            {
                "period": b["label"],
                "spending_eur": b["spending_eur"],
                "income_eur": b["income_eur"],
                "expenses_eur": b["expenses_eur"],
            },
        ]
    )
    fig = render_chart(
        df,
        {"type": "bar", "x": "period", "y": "spending_eur", "title": "Spending by period"},
    )
    return {
        "success": True,
        "range_a": a,
        "range_b": b,
        "delta_spending_eur": delta,
        "df": df,
        "figure": fig,
        "headline": (
            f"{b['label']}: €{b['spending_eur']:,.2f} spent, {direction} than {a['label']}"
        ),
        "message": (
            f"Spending was €{a['spending_eur']:,.2f} for {a['label']} and "
            f"€{b['spending_eur']:,.2f} for {b['label']}, a change of €{delta:,.2f}."
        ),
    }


def tool_get_budget_status(date_scope: Any = None) -> dict[str, Any]:
    """Per category budget, spent, remaining, and an over budget flag (AC-7)."""
    scope = resolve_date_scope(date_scope)
    if scope.get("error"):
        return {"success": False, "message": scope["error"]}

    start = scope["start_iso"] if scope["requested"] else None
    end = scope["end_iso"] if scope["requested"] else None

    conn = database.connect_readonly(DB_PATH)
    try:
        data = calculate_budget_variance(
            conn, start_date=start, end_date=end, ensure_table=False
        )
    except Exception as exc:
        return {"success": False, "message": f"Could not read budget status: {exc}"}
    finally:
        conn.close()

    rows: list[dict[str, Any]] = []
    cat_df = data["categories_df"]
    if not cat_df.empty:
        shown = cat_df[
            cat_df["is_parent"] | (cat_df["budget_eur"] > 0) | (cat_df["spent_eur"] > 0)
        ]
        for r in shown.to_dict("records"):
            rows.append(
                {
                    "category": r["category"],
                    "budget_eur": round(float(r["budget_eur"]), 2),
                    "spent_eur": round(float(r["spent_eur"]), 2),
                    "remaining_eur": round(float(r["remaining_eur"]), 2),
                    "over_budget": bool(
                        float(r["budget_eur"]) > 0
                        and float(r["spent_eur"]) > float(r["budget_eur"])
                    ),
                }
            )

    df = pd.DataFrame(rows)
    fig = (
        render_chart(
            df,
            {
                "type": "bar",
                "x": "category",
                "y": "spent_eur",
                "title": f"Spent by category ({data['month']})",
            },
        )
        if rows
        else None
    )
    over = [r["category"] for r in rows if r["over_budget"]]
    message = (
        f"Total budget €{data['total_budget_eur']:,.2f}, spent "
        f"€{data['total_spent_eur']:,.2f} in {data['month']}."
    )
    if over:
        message += f" Over budget: {', '.join(over)}."

    return {
        "success": True,
        "month": data["month"],
        "total_budget_eur": round(float(data["total_budget_eur"]), 2),
        "total_spent_eur": round(float(data["total_spent_eur"]), 2),
        "categories": rows,
        "df": df,
        "figure": fig,
        "headline": (
            f"Budget {data['month']}: €{data['total_spent_eur']:,.2f} of "
            f"€{data['total_budget_eur']:,.2f} spent"
        ),
        "message": message,
    }


def tool_get_account_balances() -> dict[str, Any]:
    """The accounts list and their latest balances (AC-7)."""
    conn = database.connect_readonly(DB_PATH)
    try:
        accounts = AccountRepository.get_all_accounts(conn)
        snaps = AccountRepository.get_all_latest_snapshots(conn)
    finally:
        conn.close()

    rows: list[dict[str, Any]] = []
    total = 0.0
    for acc in accounts:
        snap = snaps.get(acc.id) or {}
        balance = float(snap.get("balance_eur_minor") or 0) / 100.0
        total += balance
        rows.append(
            {
                "account": acc.name,
                "institution": acc.institution,
                "asset_class": acc.asset_class,
                "currency": acc.currency,
                "balance_eur": round(balance, 2),
                "as_of": str(snap.get("snapshot_date") or "")[:10],
            }
        )

    df = pd.DataFrame(rows)
    return {
        "success": True,
        "accounts": rows,
        "total_eur": round(total, 2),
        "df": df,
        "figure": None,
        "headline": f"Across {len(rows)} accounts: €{total:,.2f}",
        "message": (
            f"Found {len(rows)} accounts with a combined €{total:,.2f} as of the "
            "latest snapshots."
        ),
    }


def _avg_monthly_income(conn: Any) -> float:
    row = conn.execute(
        """
        SELECT AVG(monthly_inc) AS avg_inc FROM (
            SELECT SUM(amount_eur) AS monthly_inc
            FROM v_transactions
            WHERE category_kind = 'income' AND is_internal_transfer = 0
            GROUP BY strftime('%Y-%m', booking_date)
            ORDER BY strftime('%Y-%m', booking_date) DESC
            LIMIT 6
        )
        """
    ).fetchone()
    return float(row["avg_inc"] or 0.0) if row else 0.0


def tool_get_spending_forecast() -> dict[str, Any]:
    """Euro per month burn rate and a projected month end (AC-7)."""
    today_month = date.today().strftime("%Y-%m")
    conn = database.connect_readonly(DB_PATH)
    try:
        burn = calculate_3_month_historical_burn_rate(conn)
        nw = calculate_current_net_worth(conn)
        avg_income = _avg_monthly_income(conn)
        month_row = conn.execute(
            """
            SELECT COALESCE(SUM(-amount_eur), 0) AS spent
            FROM v_transactions
            WHERE is_internal_transfer = 0 AND amount_eur < 0
              AND strftime('%Y-%m', booking_date) = ?
            """,
            (today_month,),
        ).fetchone()
    finally:
        conn.close()

    burn_eur = float(burn.get("avg_burn_eur", 0.0) or 0.0)
    month_spent = round(float(month_row["spent"] or 0.0), 2)
    projected_month_end = round(month_spent + burn_eur, 2)

    forecast = calculate_12_month_runway_forecast(
        liquid_cash=float(nw.get("liquid_cash", 0.0) or 0.0),
        projected_monthly_income=avg_income,
        current_burn_rate=burn_eur,
        budgeted_burn_rate=burn_eur,
        horizon_months=12,
    )
    df = pd.DataFrame(forecast)
    fig = (
        render_chart(
            df,
            {
                "type": "line",
                "x": "month_label",
                "y": "current_spend_balance_eur",
                "title": "12 month balance trajectory at the 3 month burn rate",
            },
        )
        if not df.empty
        else None
    )

    return {
        "success": True,
        "burn_rate_eur_per_month": burn_eur,
        "current_month_spent_eur": month_spent,
        "projected_month_end_eur": projected_month_end,
        "months_count": burn.get("months_count", 0),
        "projection": forecast,
        "df": df,
        "figure": fig,
        "headline": (
            f"Burn €{burn_eur:,.2f}/mo, projected month end €{projected_month_end:,.2f}"
        ),
        "message": (
            f"Your 3 month burn rate is €{burn_eur:,.2f} per month, so this month is "
            f"projected to end at €{projected_month_end:,.2f}."
        ),
    }


def tool_get_income_summary(date_scope: Any = None) -> dict[str, Any]:
    """Income transactions by category plus projected holding dividends (AC-7)."""
    scope = resolve_date_scope(date_scope)
    if scope.get("error"):
        return {"success": False, "message": scope["error"]}

    clauses = ["is_internal_transfer = 0", "category_kind = 'income'"]
    params: list[Any] = []
    if scope["requested"] and scope["start_iso"]:
        clauses.append("booking_date >= ?")
        params.append(scope["start_iso"])
    if scope["requested"] and scope["end_iso"]:
        clauses.append("booking_date <= ?")
        params.append(scope["end_iso"])

    conn = database.connect_readonly(DB_PATH)
    try:
        rows = conn.execute(
            f"""
            SELECT category, ROUND(SUM(amount_eur), 2) AS total_eur, COUNT(*) AS count
            FROM v_transactions
            WHERE {" AND ".join(clauses)}
            GROUP BY category
            ORDER BY total_eur DESC
            """,
            tuple(params),
        ).fetchall()
        dividends = calculate_dividend_projections(conn)
    finally:
        conn.close()

    income_rows = [dict(r) for r in rows]
    income_total = round(sum(float(r["total_eur"] or 0) for r in income_rows), 2)
    period = (
        f"{scope['start_iso']} to {scope['end_iso']}" if scope["requested"] else "all time"
    )
    df = pd.DataFrame(income_rows)
    fig = (
        render_chart(
            df, {"type": "bar", "x": "category", "y": "total_eur", "title": "Income by category"}
        )
        if income_rows
        else None
    )
    annual_div = round(float(dividends.get("projected_annual_dividends_eur", 0.0) or 0.0), 2)

    return {
        "success": True,
        "period": period,
        "income_eur": income_total,
        "income_categories": income_rows,
        "projected_annual_dividends_eur": annual_div,
        "projected_monthly_dividends_eur": round(
            float(dividends.get("monthly_average_eur", 0.0) or 0.0), 2
        ),
        "df": df,
        "figure": fig,
        "headline": f"Income {period}: €{income_total:,.2f}",
        "message": (
            f"Income {period} is €{income_total:,.2f} across {len(income_rows)} "
            f"categories, with about €{annual_div:,.2f} per year in holding dividends."
        ),
    }


def tool_get_upcoming_bills() -> dict[str, Any]:
    """Recurring charges and their next due date (AC-7)."""
    conn = database.connect_readonly(DB_PATH)
    try:
        rows = [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM v_transactions ORDER BY booking_date DESC"
            ).fetchall()
        ]
    finally:
        conn.close()

    recurring = detect_recurring_charges(rows)
    recurring = sorted(recurring, key=lambda r: r.get("next_expected_date") or "")
    display = [
        {
            "merchant": r["merchant"],
            "cadence": r["cadence"],
            "amount_eur": r["amount_eur"],
            "next_due": r["next_expected_date"],
        }
        for r in recurring
    ]
    df = pd.DataFrame(display)
    fig = (
        render_chart(
            df,
            {
                "type": "bar",
                "x": "merchant",
                "y": "amount_eur",
                "title": "Upcoming bills by amount",
            },
        )
        if display
        else None
    )

    if not display:
        return {
            "success": True,
            "bills": [],
            "df": df,
            "figure": None,
            "message": "No recurring bills were detected in your transaction history.",
        }

    next_bill = display[0]
    return {
        "success": True,
        "bills": display,
        "df": df,
        "figure": fig,
        "headline": f"{len(display)} recurring bills, next {next_bill['merchant']} on {next_bill['next_due']}",
        "message": (
            f"Found {len(display)} recurring bills. The next due is "
            f"{next_bill['merchant']} on {next_bill['next_due']} for €{next_bill['amount_eur']:,.2f}."
        ),
    }


def tool_get_net_worth_history(date_scope: Any = None) -> dict[str, Any]:
    """An approximate monthly net worth series: running cash balance plus flat invested value (AC-7)."""
    scope = resolve_date_scope(date_scope)
    if scope.get("error"):
        return {"success": False, "message": scope["error"]}

    clauses: list[str] = []
    params: list[Any] = []
    if scope["requested"] and scope["start_iso"]:
        clauses.append("booking_date >= ?")
        params.append(scope["start_iso"])
    if scope["requested"] and scope["end_iso"]:
        clauses.append("booking_date <= ?")
        params.append(scope["end_iso"])
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""

    conn = database.connect_readonly(DB_PATH)
    try:
        nw = calculate_current_net_worth(conn)
        monthly = conn.execute(
            f"""
            SELECT strftime('%Y-%m', booking_date) AS month,
                   SUM(amount_eur) AS net_flow
            FROM v_transactions
            {where}
            GROUP BY month
            ORDER BY month ASC
            """,
            tuple(params),
        ).fetchall()
    finally:
        conn.close()

    invested_flat = float(nw.get("invested", 0.0) or 0.0)
    running = 0.0
    rows: list[dict[str, Any]] = []
    for r in monthly:
        running += float(r["net_flow"] or 0.0)
        rows.append(
            {
                "month": r["month"],
                "cash_eur": round(running, 2),
                "net_worth_eur": round(running + invested_flat, 2),
            }
        )

    df = pd.DataFrame(rows)
    fig = (
        render_chart(
            df,
            {
                "type": "line",
                "x": "month",
                "y": "net_worth_eur",
                "title": "Net worth trend (approximate)",
            },
        )
        if rows
        else None
    )
    latest = rows[-1]["net_worth_eur"] if rows else round(invested_flat, 2)

    return {
        "success": True,
        "approximate": True,
        "series": rows,
        "invested_value_eur": round(invested_flat, 2),
        "df": df,
        "figure": fig,
        "headline": f"Net worth about €{latest:,.2f} (approximate)",
        "message": (
            f"Net worth has been about €{latest:,.2f} (approximate: the ledger running "
            "cash balance plus the current invested value held flat, since there is no "
            "historical snapshot table)."
        ),
    }
