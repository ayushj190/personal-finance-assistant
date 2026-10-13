from typing import Any
import calendar
import pandas as pd

from agent.chart_renderer import render_chart
from config import DB_PATH
from db import database
from money import Money
from services.date_scope import resolve_date_scope
from services.llm_client import classify_merchants


def tool_auto_categorize_uncategorized_transactions(limit: int = 50) -> dict[str, Any]:
    """Find uncategorized transactions and classify them using LLM / merchant rules."""
    conn = database.connect(DB_PATH)
    try:
        cat_map = database.get_category_map(conn)
        allowed_cats = [c for c in cat_map.keys() if c not in ("Income", "Transfers")]

        rows = conn.execute(
            """
            SELECT id, merchant_normalized, description_raw
            FROM transactions
            WHERE category_id IS NULL AND merchant_normalized IS NOT NULL AND merchant_normalized != ''
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

        if not rows:
            return {"success": True, "classified_count": 0, "message": "All transactions are already categorized!"}

        merchants = list(dict.fromkeys(r["merchant_normalized"] for r in rows if r["merchant_normalized"]))
        classifications = classify_merchants(merchants, allowed_cats)

        updated_count = 0
        with conn:
            for merch, cat_name, conf in classifications:
                if cat_name in cat_map and conf >= 0.5:
                    c_id = cat_map[cat_name]
                    database.upsert_category_rule(conn, merch, c_id, source="llm", confidence=conf)
                    res = conn.execute(
                        "UPDATE transactions SET category_id = ?, category_source = 'llm' WHERE merchant_normalized = ? AND category_id IS NULL",
                        (c_id, merch),
                    )
                    updated_count += res.rowcount

        return {
            "success": True,
            "classified_count": updated_count,
            "message": f"Categorized {updated_count} transactions across {len(classifications)} merchants using AI.",
        }
    finally:
        conn.close()


def tool_get_spending_by_category(
    year: int | None = None,
    month: int | None = None,
    date_scope: Any = None,
) -> dict[str, Any]:
    """Get aggregated spending by category for a specific month and year, or all-time."""
    scope = resolve_date_scope(date_scope)
    if scope.get("error"):
        return {"success": False, "message": scope["error"]}
    if scope["requested"] and (year is not None or month is not None):
        return {
            "success": False,
            "message": "Provide either date_scope or year and month, not both.",
        }

    if scope["requested"]:
        year = None
        month = None

    clean_year = None
    if year is not None:
        try:
            clean_year = int(year)
            if not (1900 <= clean_year <= 2100):
                return {
                    "success": False,
                    "message": f"Invalid year '{year}'. Please specify a year between 1900 and 2100.",
                }
        except (ValueError, TypeError):
            return {
                "success": False,
                "message": f"Invalid year '{year}'. Please specify a 4-digit numeric year (e.g. 2026).",
            }

    clean_month = None
    if month is not None:
        try:
            clean_month = int(month)
            if not (1 <= clean_month <= 12):
                return {
                    "success": False,
                    "message": f"Invalid month '{month}'. Please specify a month number between 1 and 12.",
                }
        except (ValueError, TypeError):
            return {
                "success": False,
                "message": f"Invalid month '{month}'. Please provide a valid numeric month (1 to 12).",
            }

    conn = database.connect_readonly(DB_PATH)
    try:
        where_clauses = ["is_internal_transfer = 0", "amount_eur < 0"]
        params: list[Any] = []

        if scope["requested"]:
            if scope["start_iso"]:
                where_clauses.append("booking_date >= ?")
                params.append(scope["start_iso"])
            if scope["end_iso"]:
                where_clauses.append("booking_date <= ?")
                params.append(scope["end_iso"])
        elif clean_year is not None and clean_month is not None:
            prefix = f"{clean_year:04d}-{clean_month:02d}%"
            where_clauses.append("booking_date LIKE ?")
            params.append(prefix)
        elif clean_year is not None:
            prefix = f"{clean_year:04d}-%"
            where_clauses.append("booking_date LIKE ?")
            params.append(prefix)

        query = f"""
            SELECT category, ROUND(SUM(-amount_eur), 2) as total_spent, COUNT(*) as count
            FROM v_transactions
            WHERE {" AND ".join(where_clauses)}
            GROUP BY category
            ORDER BY total_spent DESC
        """
        rows = conn.execute(query, tuple(params)).fetchall()
        df = pd.DataFrame([dict(r) for r in rows]) if rows else pd.DataFrame()

        total = float(df["total_spent"].sum()) if not df.empty else 0.0
        if scope["requested"]:
            time_label = f"from {scope['start_iso']} to {scope['end_iso']}"
        else:
            time_label = f"for {clean_year}-{clean_month:02d}" if (clean_year and clean_month) else (f"for {clean_year}" if clean_year else "overall")

        if df.empty:
            total_txs = conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
            if total_txs == 0:
                guidance = "Your transaction ledger is currently empty. You can import bank or credit card statements via the '📎 Import' button in the sidebar or from the Spending page."
            else:
                guidance = f"No spending transactions found {time_label}. Try checking a different month or viewing overall spending."
            return {
                "success": True,
                "period": time_label,
                "total_spent_eur": 0.0,
                "categories": [],
                "df": df,
                "figure": None,
                "empty_dataset": True,
                "guidance": guidance,
                "message": f"No spending records found {time_label}. {guidance}",
            }

        chart_spec = {
            "type": "bar",
            "x": "category",
            "y": "total_spent",
            "title": f"Spending by Category ({time_label})",
        }
        fig = render_chart(df, chart_spec)

        return {
            "success": True,
            "period": time_label,
            "total_spent_eur": total,
            "categories": df.to_dict(orient="records"),
            "df": df,
            "figure": fig,
            "message": f"Total spending {time_label} is €{total:,.2f} across {len(df)} categories.",
        }
    finally:
        conn.close()


def tool_get_recent_transactions(
    limit: int = 15,
    category: str | None = None,
    date_scope: Any = None,
) -> dict[str, Any]:
    """Retrieve recent transactions filtered optionally by category name."""
    scope = resolve_date_scope(date_scope)
    if scope.get("error"):
        return {"success": False, "message": scope["error"]}
    try:
        clean_limit = int(limit)
    except (ValueError, TypeError):
        return {
            "success": False,
            "message": f"Invalid limit '{limit}'. Please provide a numeric limit.",
        }
    if clean_limit <= 0:
        return {
            "success": False,
            "message": f"Limit must be a positive integer, got {limit}.",
        }
    clean_limit = min(clean_limit, 100)
    clean_category = str(category).strip() if category is not None and str(category).strip() else None

    conn = database.connect_readonly(DB_PATH)
    try:
        where_clauses = ["is_internal_transfer = 0"]
        params: list[Any] = []

        if scope["requested"] and scope["start_iso"]:
            where_clauses.append("booking_date >= ?")
            params.append(scope["start_iso"])
        if scope["requested"] and scope["end_iso"]:
            where_clauses.append("booking_date <= ?")
            params.append(scope["end_iso"])

        if clean_category:
            where_clauses.append("LOWER(category) LIKE LOWER(?)")
            params.append(f"%{clean_category}%")

        query = f"""
            SELECT booking_date, institution, merchant, category, amount_eur
            FROM v_transactions
            WHERE {" AND ".join(where_clauses)}
            ORDER BY booking_date DESC
            LIMIT ?
        """
        params.append(clean_limit)
        rows = conn.execute(query, tuple(params)).fetchall()
        df = pd.DataFrame([dict(r) for r in rows]) if rows else pd.DataFrame()

        if df.empty:
            total_txs = conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
            if total_txs == 0:
                guidance = "No transactions found because your transaction ledger is empty. Upload a CSV or PDF statement via '📎 Import' in the sidebar to populate your transactions."
            else:
                cat_desc = f" for category '{clean_category}'" if clean_category else ""
                guidance = f"No transactions found{cat_desc}. Try removing or broadening the category filter."
            return {
                "success": True,
                "count": 0,
                "transactions": [],
                "df": df,
                "figure": None,
                "empty_dataset": True,
                "guidance": guidance,
                "message": guidance,
            }

        return {
            "success": True,
            "count": len(df),
            "transactions": df.to_dict(orient="records"),
            "df": df,
            "figure": None,
            "message": f"Found {len(df)} transactions.",
        }
    finally:
        conn.close()


def tool_get_monthly_cashflow(year: int | None = None, date_scope: Any = None) -> dict[str, Any]:
    """Get monthly cashflow summary (income, fixed, discretionary, savings)."""
    scope = resolve_date_scope(date_scope)
    if scope.get("error"):
        return {"success": False, "message": scope["error"]}
    if scope["requested"] and year is not None:
        return {
            "success": False,
            "message": "Provide either date_scope or year, not both.",
        }

    note = ""
    start_month: date | None = None
    end_month: date | None = None
    if scope["requested"]:
        year = None
        if scope["start"] is not None and scope["end"] is not None:
            s = scope["start"]
            e = scope["end"]
            start_month = s.replace(day=1)
            end_month = e.replace(day=1)
            aligned = s.day == 1 and e.day == calendar.monthrange(e.year, e.month)[1]
            if aligned:
                note = f"Range: {s.isoformat()} to {e.isoformat()}."
            else:
                note = (
                    "Cashflow is month grained, so I snapped the range to whole months: "
                    f"{start_month.isoformat()} to {end_month.isoformat()}."
                )

    clean_year = None
    if year is not None:
        try:
            clean_year = int(year)
            if not (1900 <= clean_year <= 2100):
                return {
                    "success": False,
                    "message": f"Invalid year '{year}'. Please specify a year between 1900 and 2100.",
                }
        except (ValueError, TypeError):
            return {
                "success": False,
                "message": f"Invalid year '{year}'. Please specify a 4-digit numeric year.",
            }

    conn = database.connect_readonly(DB_PATH)
    try:
        params: list[Any] = []
        where_clause = ""
        if start_month is not None and end_month is not None:
            where_clause = "WHERE month >= ? AND month <= ?"
            params.extend([start_month.strftime("%Y-%m"), end_month.strftime("%Y-%m")])
        elif clean_year is not None:
            where_clause = "WHERE month LIKE ?"
            params.append(f"{clean_year:04d}-%")

        query = f"""
            SELECT month, income_eur, fixed_eur, discretionary_eur, savings_eur
            FROM v_monthly_cashflow
            {where_clause}
            ORDER BY month DESC
            LIMIT 12
        """
        rows = conn.execute(query, tuple(params)).fetchall()
        df = pd.DataFrame([dict(r) for r in rows]) if rows else pd.DataFrame()

        if df.empty:
            total_txs = conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
            if total_txs == 0:
                guidance = "No monthly cashflow available because your transaction ledger is empty. Upload bank statements via the '📎 Import' button in the sidebar to generate cashflow summaries."
            else:
                yr_desc = f" for year {clean_year}" if clean_year else ""
                guidance = f"No cashflow records found{yr_desc}. Import additional monthly statements or adjust the year filter."
            return {
                "success": True,
                "cashflow": [],
                "df": df,
                "figure": None,
                "empty_dataset": True,
                "guidance": guidance,
                "message": guidance,
            }

        return {
            "success": True,
            "cashflow": df.to_dict(orient="records"),
            "df": df,
            "figure": None,
            "message": f"Retrieved cashflow data for {len(df)} months. {note}".strip(),
        }
    finally:
        conn.close()
