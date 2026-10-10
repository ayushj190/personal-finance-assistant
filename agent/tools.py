from datetime import date, datetime
import sys
import io
from typing import Any
import pandas as pd
import streamlit as st

from agent.chart_renderer import render_chart
from agent.sql_sandbox import execute_safe_query
from config import DB_PATH
from connectors.file_import.detect import (
    FileFormat,
    parse_statement,
    parse_statement_balance,
    parse_statement_holdings,
)
from connectors.market_data_service import update_quotes, fetch_yfinance_quote
from db import database
from services.llm_client import classify_merchants, search_brave
from services.mortgage import sync_liability_schedule
from services.sync_service import import_statement_content, process_and_save_transactions
from services.analytics import calculate_current_net_worth


def tool_get_current_net_worth() -> dict[str, Any]:
    """Calculate and return the user's real-time net worth, including liquid cash, investments, and home equity."""
    conn = database.connect(DB_PATH)
    try:
        nw_data = calculate_current_net_worth(conn)
        return {
            "success": True,
            "liquid_cash_eur": nw_data["liquid_cash"],
            "investments_eur": nw_data["invested"],
            "home_equity_eur": nw_data["home_equity"],
            "net_worth_eur": nw_data["net_worth"],
            "message": f"Your current net worth is €{nw_data['net_worth']:,.2f}."
        }
    finally:
        conn.close()


def tool_toggle_privacy_mode(enable: bool | None = None) -> dict[str, Any]:
    """Toggle or set privacy mode (hide or show financial amounts)."""
    current = st.session_state.get("hide_amounts", False) if hasattr(
        st, "session_state") else False
    new_val = not current if enable is None else bool(enable)
    if hasattr(st, "session_state"):
        st.session_state["hide_amounts"] = new_val
        st.session_state["global_privacy_toggle"] = new_val
    state_str = "ENABLED (Amounts hidden)" if new_val else "DISABLED (Amounts visible)"
    return {"success": True, "message": f"Privacy mode is now {state_str}."}


def tool_set_theme(theme: str) -> dict[str, Any]:
    """Set app theme to 'dark' or 'light'."""
    clean_theme = theme.lower().strip()
    if clean_theme not in ("dark", "light"):
        return {"success": False, "message": "Theme must be either 'dark' or 'light'."}
    if hasattr(st, "session_state"):
        st.session_state["theme"] = clean_theme
        st.session_state["global_theme_toggle"] = (clean_theme == "light")
    return {"success": True, "message": f"App theme switched to {clean_theme} mode."}


def tool_set_active_allocation_profile(profile_name: str) -> dict[str, Any]:
    """Set the active investment asset allocation profile by name."""
    conn = database.connect(DB_PATH)
    try:
        row = conn.execute(
            "SELECT id, name, dimension, drift_band_pct FROM allocation_profiles WHERE LOWER(name) LIKE LOWER(?)",
            (f"%{profile_name.strip()}%",),
        ).fetchone()
        if not row:
            profiles = conn.execute(
                "SELECT name FROM allocation_profiles").fetchall()
            available = [p["name"] for p in profiles]
            return {
                "success": False,
                "message": f"Profile '{profile_name}' not found. Available profiles: {', '.join(available)}",
            }

        with conn:
            conn.execute("UPDATE allocation_profiles SET is_active = 0")
            conn.execute(
                "UPDATE allocation_profiles SET is_active = 1 WHERE id = ?", (row["id"],))

        return {
            "success": True,
            "message": f"Active allocation profile set to '{row['name']}' (Dimension: {row['dimension']}, Tolerance: ±{row['drift_band_pct']}pp).",
        }
    finally:
        conn.close()


def tool_update_savings_rate(
    institution_or_name: str,
    apy_pct: float,
    balance_eur: float | None = None,
) -> dict[str, Any]:
    """Update Annual Percentage Yield (APY) interest rate or balance for a savings/cash account."""
    conn = database.connect(DB_PATH)
    try:
        row = conn.execute(
            """
            SELECT id, institution, name, apy FROM accounts
            WHERE asset_class = 'cash' AND (LOWER(institution) LIKE LOWER(?) OR LOWER(name) LIKE LOWER(?))
            LIMIT 1
            """,
            (f"%{institution_or_name.strip()}%",
             f"%{institution_or_name.strip()}%"),
        ).fetchone()

        if not row:
            accounts = conn.execute(
                "SELECT institution, name FROM accounts WHERE asset_class = 'cash'").fetchall()
            names = [f"{a['institution']} - {a['name']}" for a in accounts]
            return {
                "success": False,
                "message": f"Cash account '{institution_or_name}' not found. Available cash accounts: {', '.join(names)}",
            }

        acc_id = row["id"]
        with conn:
            conn.execute(
                "UPDATE accounts SET apy = ? WHERE id = ?", (apy_pct, acc_id))
            if balance_eur is not None:
                b_minor = int(round(balance_eur * 100))
                database.upsert_snapshots(
                    conn,
                    [{
                        "account_id": acc_id,
                        "snapshot_date": date.today().isoformat(),
                        "balance_minor": b_minor,
                        "balance_eur_minor": b_minor,
                    }],
                )

        msg = f"Updated {row['institution']} ({row['name']}) APY to {apy_pct:.2f}%."
        if balance_eur is not None:
            msg += f" Current balance recorded as €{balance_eur:,.2f}."
        return {"success": True, "message": msg}
    finally:
        conn.close()


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
            all_loans = conn.execute(
                "SELECT name, lender FROM liabilities").fetchall()
            names = [f"{l['name']} ({l['lender']})" for l in all_loans]
            return {
                "success": False,
                "message": f"Loan '{loan_name}' not found. Available loans: {', '.join(names)}",
            }

        lib_id = row["id"]
        p_date = paid_date or date.today().isoformat()
        amt_minor = int(round(amount_eur * 100))
        recalc_mode = "shorter_term" if recalc in (
            "shorter_term", "term") else "lower_payment"

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


def tool_save_risk_profile(
    risk_score: int,
    risk_tolerance: str,
    notes: str = "",
    answers: dict[str, str] | None = None,
    investment_horizon_years: int | None = None,
    liquidity_needs: str | None = None,
    investment_experience: str | None = None,
) -> dict[str, Any]:
    """Save user investment risk assessment profile to the database."""
    conn = database.connect(DB_PATH)
    try:
        score = max(1, min(10, int(risk_score))) if risk_score is not None else 5
        risk_tolerance = risk_tolerance.strip() if risk_tolerance else "Moderate"
        notes = notes.strip() if notes else ""
        p_id = database.save_risk_profile(
            conn,
            risk_score=score,
            risk_tolerance=risk_tolerance.strip(),
            notes=notes.strip(),
            answers=answers or {},
            investment_horizon_years=investment_horizon_years,
            liquidity_needs=liquidity_needs,
            investment_experience=investment_experience,
        )
        return {
            "success": True,
            "profile_id": p_id,
            "risk_score": score,
            "risk_tolerance": risk_tolerance.strip(),
            "message": f"Risk profile successfully saved: Score {score}/10 ({risk_tolerance}).",
        }
    finally:
        conn.close()


def tool_get_risk_profile() -> dict[str, Any]:
    """Retrieve the latest saved investment risk tolerance profile."""
    conn = database.connect(DB_PATH)
    try:
        profile = database.get_latest_risk_profile(conn)
        if not profile:
            return {
                "success": False,
                "message": "No risk profile has been established yet. Offer the user a risk questionnaire to determine their tolerance.",
            }
        return {"success": True, "profile": profile}
    finally:
        conn.close()


def tool_analyze_investments() -> dict[str, Any]:
    """Analyze current portfolio asset allocation against the active target profile and user risk profile."""
    conn = database.connect(DB_PATH)
    try:
        # Net worth breakdown
        nw_rows = conn.execute(
            """
            SELECT a.asset_class, SUM(s.balance_eur_minor) / 100.0 AS value_eur
            FROM account_snapshots s
            JOIN accounts a ON a.id = s.account_id
            WHERE s.snapshot_date = (SELECT MAX(snapshot_date) FROM account_snapshots WHERE account_id = s.account_id)
            GROUP BY a.asset_class
            """
        ).fetchall()
        asset_classes = {r["asset_class"]: r["value_eur"] for r in nw_rows}

        # Holdings breakdown
        h_rows = conn.execute(
            """
            SELECT asset_type, SUM(value_eur) as total_eur
            FROM v_holdings
            GROUP BY asset_type
            """
        ).fetchall()
        holdings_by_type = {r["asset_type"]: r["total_eur"] for r in h_rows}

        # Active allocation profile & targets
        profile = conn.execute(
            "SELECT * FROM allocation_profiles WHERE is_active = 1 LIMIT 1").fetchone()
        targets = []
        if profile:
            t_rows = conn.execute(
                "SELECT bucket, target_pct FROM allocation_targets WHERE profile_id = ?",
                (profile["id"],),
            ).fetchall()
            targets = [dict(t) for t in t_rows]

        risk_prof = database.get_latest_risk_profile(conn)

        return {
            "success": True,
            "asset_classes_eur": asset_classes,
            "holdings_by_asset_type_eur": holdings_by_type,
            "active_allocation_profile": dict(profile) if profile else None,
            "allocation_targets": targets,
            "risk_profile": risk_prof,
        }
    finally:
        conn.close()


tool_get_portfolio_and_risk_summary = tool_analyze_investments



def tool_parse_and_import_file(
    file_name: str,
    file_bytes: bytes,
    confirm_balance: float | None = None,
) -> dict[str, Any]:
    """Parse uploaded bank/broker statement (PDF, CSV, TAB, XML, MT940) and insert transactions and holdings into DB."""
    conn = database.connect(DB_PATH)
    try:
        fmt, raw_txs = parse_statement(file_bytes)
        raw_holdings = parse_statement_holdings(file_bytes)
        detected_balance = parse_statement_balance(file_bytes)

        if not raw_txs and not raw_holdings and detected_balance is None:
            return {
                "success": False,
                "message": f"Could not detect valid financial transactions, holdings, or balance in '{file_name}'. (Detected format: {fmt.value})",
            }

        # Map format to accounts
        mapping = {
            FileFormat.ETORO_STATEMENT_CSV: ("eToro", "etoro_cash_eur", "etoro_trading_usd"),
            FileFormat.ETORO_MONEY_TSV: ("eToro Bank", "etoro_cash_eur", "etoro_cash_eur"),
            FileFormat.REVOLUT_CSV: ("Revolut", "revolut_eur", "revolut_eur"),
            FileFormat.ABN_AMRO_TAB: ("ABN AMRO", "abn_checking", "abn_checking"),
        }
        inst, cash_ext, inv_ext = mapping.get(
            fmt, ("Imported Bank", "imported_cash", "imported_inv"))

        # Resolve accounts
        cash_row = conn.execute(
            "SELECT id FROM accounts WHERE external_id = ?", (cash_ext,)).fetchone()
        if cash_row:
            cash_id = cash_row["id"]
        else:
            cash_id = database.upsert_account(
                conn,
                {
                    "provider": "manual",
                    "institution": inst,
                    "external_id": cash_ext,
                    "name": f"{inst} Cash",
                    "currency": "EUR",
                    "asset_class": "cash",
                    "apy": 3.0 if inst == "Trade Republic" else None,
                },
            )

        inv_row = conn.execute(
            "SELECT id FROM accounts WHERE external_id = ?", (inv_ext,)).fetchone()
        if inv_row:
            inv_id = inv_row["id"]
        else:
            inv_id = database.upsert_account(
                conn,
                {
                    "provider": "manual",
                    "institution": inst,
                    "external_id": inv_ext,
                    "name": f"{inst} Investment",
                    "currency": "EUR",
                    "asset_class": "investment",
                },
            )

        details = []
        inserted, skipped = 0, 0
        if raw_txs:
            content_str = file_bytes.decode("utf-8", errors="replace")
            inserted, skipped, _ = import_statement_content(
                conn, content=content_str, target_account_id=cash_id, enable_llm=False
            )
            details.append(
                f"{inserted} transactions imported ({skipped} duplicates skipped)")

        # Balance update
        final_bal = confirm_balance if confirm_balance is not None else (
            detected_balance / 100.0 if detected_balance else None)
        if final_bal is not None:
            b_minor = int(round(final_bal * 100))
            database.upsert_snapshots(
                conn,
                [{
                    "account_id": cash_id,
                    "snapshot_date": date.today().isoformat(),
                    "balance_minor": b_minor,
                    "balance_eur_minor": b_minor,
                }],
            )
            details.append(f"Balance recorded: €{final_bal:,.2f}")

        # Holdings
        if raw_holdings:
            prepared_h = [
                {
                    "account_id": inv_id,
                    "ticker": h.ticker,
                    "isin": h.isin,
                    "name": h.name,
                    "asset_type": h.asset_type,
                    "region": h.region,
                    "sector": h.sector,
                    "quantity": h.quantity,
                    "cost_basis_minor": h.cost_basis_minor,
                    "currency": h.currency,
                    "updated_at": datetime.now().isoformat(),
                }
                for h in raw_holdings
            ]
            database.upsert_holdings(conn, prepared_h)
            details.append(f"{len(raw_holdings)} investment positions saved")
            try:
                tickers = [h.ticker for h in raw_holdings if h.ticker]
                update_quotes(tickers, db_conn=conn)
            except Exception:
                pass

        return {
            "success": True,
            "format": fmt.value,
            "message": f"Successfully imported '{file_name}' ({fmt.value}): {', '.join(details)}.",
            "inserted_transactions": inserted,
            "skipped_transactions": skipped,
            "holdings_count": len(raw_holdings),
        }
    finally:
        conn.close()


def tool_auto_categorize_uncategorized_transactions(limit: int = 50) -> dict[str, Any]:
    """Find uncategorized transactions and classify them using LLM / merchant rules."""
    conn = database.connect(DB_PATH)
    try:
        cat_map = database.get_category_map(conn)
        allowed_cats = [c for c in cat_map.keys(
        ) if c not in ("Income", "Transfers")]

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

        merchants = list(dict.fromkeys(
            r["merchant_normalized"] for r in rows if r["merchant_normalized"]))
        classifications = classify_merchants(merchants, allowed_cats)

        updated_count = 0
        with conn:
            for merch, cat_name, conf in classifications:
                if cat_name in cat_map and conf >= 0.5:
                    c_id = cat_map[cat_name]
                    database.upsert_category_rule(
                        conn, merch, c_id, source="llm", confidence=conf)
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


def tool_query_financial_data(
    sql: str,
    chart_spec: dict[str, Any] | None = None,
    summary_template: str = "",
) -> dict[str, Any]:
    """Execute read-only SQL query against financial views and generate Plotly charts."""
    df = pd.DataFrame()
    try:
        df = execute_safe_query(sql)
    except Exception as e:
        return {
            "success": False,
            "answer": f"Database query failed: {str(e)}",
            "sql": sql,
            "df": pd.DataFrame(),
            "figure": None,
        }

    fig = render_chart(df, chart_spec) if chart_spec else None

    # Summary
    summary = summary_template
    if summary and not df.empty:
        try:
            first_row = df.iloc[0].to_dict()
            first_val = list(first_row.values())[0] if first_row else ""
            summary = summary.replace("{total}", str(round(first_val, 2)) if isinstance(
                first_val, (int, float)) else str(first_val))
            summary = summary.replace("{count}", str(len(df)))
        except Exception:
            pass
    elif not summary:
        summary = f"Found {len(df)} matching records."

    return {
        "success": True,
        "answer": summary,
        "sql": sql,
        "df": df,
        "figure": fig,
    }


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


def tool_execute_python(code: str) -> dict[str, Any]:
    """Execute Python code for complex data analysis using pandas or sqlite3. Returns stdout."""
    old_stdout = sys.stdout
    redirected_output = sys.stdout = io.StringIO()
    try:
        import pandas as pd
        import sqlite3
        import numpy as np
        from config import DB_PATH

        local_env = {
            "pd": pd,
            "sqlite3": sqlite3,
            "np": np,
            "DB_PATH": DB_PATH,
        }
        exec(code, local_env)
        stdout_val = redirected_output.getvalue()
        return {"success": True, "output": stdout_val.strip()}
    except Exception as e:
        return {"success": False, "error": str(e)}
    finally:
        sys.stdout = old_stdout


def tool_save_tax_profile(
    gross_annual_income: float,
    has_fiscal_partner: bool,
    has_30_percent_ruling: bool = False,
    is_entrepreneur: bool = False,
    owns_home: bool = False,
    birth_year: int | None = None,
    has_13th_month: bool = False,
    expected_bonus_eur: float = 0,
    pension_contribution_pct: float = 0,
    employer_pension_match_pct: float = 0
) -> dict[str, Any]:
    """Save user tax profile to the database."""
    conn = database.connect(DB_PATH)
    try:
        with conn:
            conn.execute(
                "INSERT INTO tax_profile (id, gross_annual_income, has_fiscal_partner, has_30_percent_ruling, "
                "is_entrepreneur, owns_home, birth_year, has_13th_month, expected_bonus_eur, pension_contribution_pct, employer_pension_match_pct) "
                "VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET gross_annual_income=excluded.gross_annual_income, "
                "has_fiscal_partner=excluded.has_fiscal_partner, has_30_percent_ruling=excluded.has_30_percent_ruling, "
                "is_entrepreneur=excluded.is_entrepreneur, owns_home=excluded.owns_home, birth_year=excluded.birth_year, "
                "has_13th_month=excluded.has_13th_month, expected_bonus_eur=excluded.expected_bonus_eur, "
                "pension_contribution_pct=excluded.pension_contribution_pct, employer_pension_match_pct=excluded.employer_pension_match_pct, "
                "updated_at=datetime('now')",
                (gross_annual_income if gross_annual_income is not None else 0.0, 
                 1 if has_fiscal_partner else 0, 1 if has_30_percent_ruling else 0, 1 if is_entrepreneur else 0, 
                 1 if owns_home else 0, birth_year, 1 if has_13th_month else 0, 
                 int(expected_bonus_eur) if expected_bonus_eur is not None else 0, 
                 pension_contribution_pct if pension_contribution_pct is not None else 0.0, 
                 employer_pension_match_pct if employer_pension_match_pct is not None else 0.0)
            )
        return {
            "success": True,
            "message": f"Tax profile saved successfully: Gross Income €{(gross_annual_income or 0):,.2f}, Fiscal Partner: {bool(has_fiscal_partner)}."
        }
    finally:
        conn.close()


def tool_analyze_tax_situation() -> dict[str, Any]:
    """Fetch the user's gross income from tax_profile, their investment/cash balances for Box 3, and return them for analysis."""
    conn = database.connect(DB_PATH)
    try:
        profile = conn.execute("SELECT * FROM tax_profile WHERE id = 1").fetchone()
        if not profile or profile["gross_annual_income"] == 0:
            return {
                "success": False,
                "message": "User has not set up their tax profile or gross income. Ask them to fill it out in the Tax Analysis tab."
            }
        
        # Get net worth data for Box 3
        nw_data = calculate_current_net_worth(conn)
        cash_bal = nw_data["liquid_cash"]
        invested_bal = nw_data["invested"]
        
        return {
            "success": True,
            "tax_profile": dict(profile),
            "box3_assets": {
                "liquid_cash": cash_bal,
                "invested": invested_bal,
                "total_wealth": cash_bal + invested_bal
            },
            "message": "Tax data retrieved successfully."
        }
    finally:
        conn.close()


def tool_analyze_mortgage() -> dict[str, Any]:
    """Fetch liability details, schedule, and interest rates for mortgage analysis."""
    conn = database.connect(DB_PATH)
    try:
        liabilities = conn.execute("SELECT * FROM liabilities").fetchall()
        if not liabilities:
            return {
                "success": False,
                "message": "User has no active mortgages or liabilities configured."
            }
        
        mortgage_data = []
        for lib in liabilities:
            lib_id = lib["id"]
            # Get latest rate period
            rate = conn.execute("SELECT annual_rate, fixed_until FROM liability_rate_periods WHERE liability_id = ? ORDER BY from_date DESC LIMIT 1", (lib_id,)).fetchone()
            # Get upcoming schedule payments (next 3 months)
            schedule = conn.execute("SELECT due_date, payment_minor, interest_minor, principal_minor, balance_minor FROM liability_schedule WHERE liability_id = ? AND due_date >= date('now') ORDER BY due_date ASC LIMIT 3", (lib_id,)).fetchall()
            
            mortgage_data.append({
                "liability": dict(lib),
                "current_rate": dict(rate) if rate else None,
                "upcoming_schedule": [dict(s) for s in schedule]
            })
            
        return {
            "success": True,
            "mortgages": mortgage_data,
            "message": "Mortgage data retrieved successfully."
        }
    finally:
        conn.close()


def tool_request_profile_form(form_type: str) -> dict[str, Any]:
    """Request the UI to render an interactive form for the user to fill out. Valid form_types: 'tax_profile', 'risk_profile'"""
    return {
        "success": True,
        "form_request": form_type,
        "message": f"Displaying the {form_type.replace('_', ' ')} form..."
    }

