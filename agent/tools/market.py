from datetime import date
from typing import Any

from config import DB_PATH
from connectors.market_data_service import fetch_yfinance_quote
from db import database
from money import Money
from services.llm_client import search_brave
from services.mortgage import sync_liability_schedule


def tool_search_web(query: str) -> dict[str, Any]:
    """Search the web for up-to-date information, news, or context."""
    result = search_brave(query)
    if not result:
        return {"success": False, "message": "No web search results found or Brave API key is missing."}
    return {"success": True, "results": result}


def tool_analyze_market_data(ticker: str) -> dict[str, Any]:
    """Fetch live market data and fundamentals for a stock or ETF ticker (e.g., AAPL, VWCE.DE)."""
    quote = fetch_yfinance_quote(ticker)
    if not quote:
        return {"success": False, "message": f"Could not find market data for ticker: {ticker}"}
    return {"success": True, "quote": quote}


def tool_add_mortgage_payment(
    loan_name: str,
    amount_eur: float,
    paid_date: str | None = None,
    recalc: str = "lower_payment",
) -> dict[str, Any]:
    """Add extra (penalty-free) repayment on a mortgage loan and recalculate schedule."""
    conn = database.connect(DB_PATH)
    try:
        row = conn.execute(
            "SELECT id, name, lender, loan_type FROM liabilities WHERE LOWER(name) LIKE LOWER(?) OR LOWER(lender) LIKE LOWER(?) LIMIT 1",
            (f"%{loan_name.strip()}%", f"%{loan_name.strip()}%"),
        ).fetchone()

        if not row:
            all_loans = conn.execute("SELECT name, lender FROM liabilities").fetchall()
            names = [f"{l['name']} ({l['lender']})" for l in all_loans]
            return {
                "success": False,
                "message": f"Loan '{loan_name}' not found. Available loans: {', '.join(names)}",
            }

        lib_id = row["id"]
        p_date = paid_date or date.today().isoformat()
        amt_minor = Money.from_major(amount_eur).cents
        recalc_mode = "shorter_term" if recalc in ("shorter_term", "term") else "lower_payment"

        with conn:
            conn.execute(
                """
                INSERT INTO liability_extra_payments (liability_id, paid_date, amount_minor, recalc)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(liability_id, paid_date) DO UPDATE SET
                    amount_minor = excluded.amount_minor,
                    recalc = excluded.recalc
                """,
                (lib_id, p_date, amt_minor, recalc_mode),
            )

        sync_liability_schedule(conn, lib_id)
        return {
            "success": True,
            "message": f"Recorded extra payment of €{amount_eur:,.2f} on {p_date} for '{row['name']}'. Mortgage schedule recalculated ({recalc_mode}).",
        }
    finally:
        conn.close()


def tool_analyze_mortgage() -> dict[str, Any]:
    """Fetch liability details, schedule, and interest rates for mortgage analysis."""
    conn = database.connect_readonly(DB_PATH)
    try:
        liabilities = conn.execute("SELECT * FROM liabilities").fetchall()
        if not liabilities:
            guidance = (
                "No active mortgages or liabilities configured in your ledger. "
                "You can add a mortgage on the Mortgage page to track amortization schedules, "
                "interest rates, and deductible interest."
            )
            return {
                "success": False,
                "empty_dataset": True,
                "guidance": guidance,
                "message": f"No active mortgages or loans found. {guidance}",
            }

        mortgage_data = []
        for lib in liabilities:
            lib_id = lib["id"]
            rate = conn.execute(
                "SELECT annual_rate, fixed_until FROM liability_rate_periods WHERE liability_id = ? ORDER BY from_date DESC LIMIT 1",
                (lib_id,),
            ).fetchone()
            schedule = conn.execute(
                "SELECT due_date, payment_minor, interest_minor, principal_minor, balance_minor FROM liability_schedule WHERE liability_id = ? AND due_date >= date('now') ORDER BY due_date ASC LIMIT 3",
                (lib_id,),
            ).fetchall()

            mortgage_data.append({
                "liability": dict(lib),
                "current_rate": dict(rate) if rate else None,
                "upcoming_schedule": [dict(s) for s in schedule],
            })

        return {
            "success": True,
            "mortgages": mortgage_data,
            "message": "Mortgage data retrieved successfully.",
        }
    finally:
        conn.close()


def tool_request_profile_form(form_type: str) -> dict[str, Any]:
    """Request the UI to render an interactive form for the user to fill out. Valid form_types: 'tax_profile', 'risk_profile'"""
    return {
        "success": True,
        "form_request": form_type,
        "message": f"Displaying the {form_type.replace('_', ' ')} form...",
    }
