from datetime import date, datetime
from typing import Any
import pandas as pd
import streamlit as st
import plotly.express as px

from agent.chart_renderer import render_chart
from agent.tool_schemas import COPILOT_TOOLS_SCHEMA
from config import DB_PATH
from services.rag_service import search_knowledge_base, ingest_user_document
from services.legal_vault_service import search_legal_vault, lookup_article
from services.tax_optimizer import (
    calculate_jaarruimte,
    calculate_groenfondsen_arbitrage,
    simulate_capital_allocation_tradeoff,
    diagnose_tax_leakage,
)
from connectors.file_import.detect import (
    FileFormat,
    parse_statement,
    parse_statement_balance,
    parse_statement_holdings,
)
from connectors.market_data_service import update_quotes, fetch_yfinance_quote
from db import database
from db.repositories import AccountRepository, HoldingRepository
from services.llm_client import classify_merchants, search_brave
from services.mortgage import sync_liability_schedule
from services.sync_service import import_statement_content
from services.analytics import calculate_current_net_worth
from services.portfolio import calculate_drift, get_consolidated_holdings_df


def tool_get_current_net_worth() -> dict[str, Any]:
    """Calculate and return the user's real-time net worth, including liquid cash, investments, and home equity."""
    conn = database.connect_readonly(DB_PATH)
    try:
        nw_data = calculate_current_net_worth(conn)
        acc_count = conn.execute("SELECT COUNT(*) FROM accounts").fetchone()[0]
        if acc_count == 0 and nw_data["net_worth"] == 0:
            guidance = "No financial accounts configured yet. Import a bank or broker statement via '📎 Import' in the sidebar or add manual accounts on the Dashboard."
            return {
                "success": True,
                "liquid_cash_eur": 0.0,
                "investments_eur": 0.0,
                "home_equity_eur": 0.0,
                "net_worth_eur": 0.0,
                "empty_dataset": True,
                "guidance": guidance,
                "message": f"Your current net worth is €0.00. {guidance}",
            }
        return {
            "success": True,
            "liquid_cash_eur": nw_data["liquid_cash"],
            "investments_eur": nw_data["invested"],
            "home_equity_eur": nw_data["home_equity"],
            "net_worth_eur": nw_data["net_worth"],
            "message": f"Your current net worth is €{nw_data['net_worth']:,.2f}.",
        }
    finally:
        conn.close()


def tool_toggle_privacy_mode(enable: bool | None = None) -> dict[str, Any]:
    """Toggle or set privacy mode (hide or show financial amounts)."""
    current = False
    try:
        current = bool(st.session_state.get("hide_amounts", False))
    except Exception:
        pass
    new_val = not current if enable is None else bool(enable)
    try:
        st.session_state["hide_amounts"] = new_val
        st.session_state["global_privacy_toggle"] = new_val
    except Exception:
        pass
    state_str = "ENABLED (Amounts hidden)" if new_val else "DISABLED (Amounts visible)"
    return {"success": True, "message": f"Privacy mode is now {state_str}."}


def tool_set_theme(theme: str) -> dict[str, Any]:
    """Set app theme to 'dark' or 'light'."""
    clean_theme = theme.lower().strip()
    if clean_theme not in ("dark", "light"):
        return {"success": False, "message": "Theme must be either 'dark' or 'light'."}
    try:
        st.session_state["theme"] = clean_theme
        st.session_state["global_theme_toggle"] = (clean_theme == "light")
    except Exception:
        pass
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
    conn = database.connect_readonly(DB_PATH)
    try:
        profile = database.get_latest_risk_profile(conn)
        if not profile:
            guidance = "No risk profile has been established yet. You can complete the questionnaire by clicking '🎯 Assess Risk' in the sidebar."
            return {
                "success": False,
                "empty_dataset": True,
                "guidance": guidance,
                "message": f"No risk profile has been established yet. {guidance}",
            }
        return {"success": True, "profile": profile}
    finally:
        conn.close()


def tool_analyze_investments() -> dict[str, Any]:
    """Analyze current portfolio asset allocation against the active target profile and user risk profile."""
    conn = database.connect_readonly(DB_PATH)
    try:
        # Net worth breakdown by asset class
        nw_rows = conn.execute(
            """
            SELECT a.asset_class, SUM(s.balance_eur_minor) / 100.0 AS value_eur
            FROM account_snapshots s
            JOIN accounts a ON a.id = s.account_id
            WHERE s.snapshot_date = (SELECT MAX(snapshot_date) FROM account_snapshots WHERE account_id = s.account_id)
            GROUP BY a.asset_class
            """
        ).fetchall()
        asset_classes = {
            r["asset_class"]: round(float(r["value_eur"]), 2)
            for r in nw_rows
            if r["value_eur"] is not None
        }

        # Liquid cash balance in EUR
        cash_balance_eur = round(float(AccountRepository.get_total_cash_balance(conn)), 2)

        # Single source of truth: consolidated holdings resolving direct holdings and copy trade mirrors
        consolidated_df = get_consolidated_holdings_df(conn)

        positions: list[dict[str, Any]] = []
        if not consolidated_df.empty and "value_eur" in consolidated_df.columns:
            total_portfolio_value_eur = round(float(consolidated_df["value_eur"].sum()), 2)
            holdings_by_type = {
                str(k): round(float(v), 2)
                for k, v in consolidated_df.groupby("asset_type")["value_eur"].sum().to_dict().items()
            }
            for _, row in consolidated_df.iterrows():
                val = float(row.get("value_eur", 0.0) or 0.0)
                positions.append({
                    "ticker": str(row.get("ticker", "")),
                    "name": str(row.get("name", "")),
                    "display_label": str(row.get("display_label", "")),
                    "value_eur": round(val, 2),
                    "value_eur_formatted": f"€{val:,.2f}",
                    "asset_class": str(row.get("asset_class", "investment")),
                    "asset_type": str(row.get("asset_type", "")),
                    "region": str(row.get("region", "")),
                    "sector": str(row.get("sector", "")),
                    "currency": str(row.get("currency", "EUR")),
                    "source": str(row.get("source", "Direct Holdings")),
                })
        else:
            total_portfolio_value_eur = 0.0
            holdings_by_type = {}

        # Active allocation profile & targets
        profiles = HoldingRepository.get_allocation_profiles(conn)
        active_profile = next((p for p in profiles if p.get("is_active")), profiles[0] if profiles else None)
        targets_dict: dict[str, float] = {}
        targets_list: list[dict[str, Any]] = []
        drift_data: list[dict[str, Any]] = []

        if active_profile:
            targets_dict = HoldingRepository.get_allocation_targets(conn, active_profile["id"])
            targets_list = [{"bucket": b, "target_pct": pct} for b, pct in targets_dict.items()]

            dimension = active_profile.get("dimension") or "asset_type"
            include_cash = bool(active_profile.get("include_cash", 0))
            drift_band_pct = float(active_profile.get("drift_band_pct", 5.0))

            current_values: dict[str, float] = {}
            if not consolidated_df.empty:
                col_to_use = dimension if dimension in consolidated_df.columns else "asset_type"
                for _, row in consolidated_df.iterrows():
                    b_key = str(row.get(col_to_use) or "other")
                    current_values[b_key] = current_values.get(b_key, 0.0) + float(row.get("value_eur", 0.0) or 0.0)

            if include_cash and cash_balance_eur > 0:
                current_values["cash"] = cash_balance_eur

            drift_data = calculate_drift(
                current_values=current_values,
                targets=targets_dict,
                drift_band_pct=drift_band_pct,
            )

        risk_prof = database.get_latest_risk_profile(conn)

        # Graceful empty state handling (AC-6)
        if consolidated_df.empty and not asset_classes:
            guidance = (
                "No portfolio holdings or investment accounts recorded yet. "
                "Import an eToro or broker statement via the '📎 Import' button in the sidebar "
                "or from the Investments page."
            )
            return {
                "success": True,
                "empty_dataset": True,
                "total_portfolio_value_eur": 0.0,
                "total_portfolio_value_formatted": "€0.00",
                "cash_balance_eur": cash_balance_eur,
                "cash_balance_formatted": f"€{cash_balance_eur:,.2f}",
                "asset_classes_eur": {},
                "holdings_by_asset_type_eur": {},
                "positions": [],
                "active_allocation_profile": active_profile,
                "allocation_targets": targets_list,
                "allocation_drift": [],
                "rebalance_needed": False,
                "risk_profile": risk_prof,
                "guidance": guidance,
                "message": f"No investment holdings found. {guidance}",
            }

        drift_alerts = [d for d in drift_data if d.get("alert")]
        rebalance_needed = len(drift_alerts) > 0
        msg_parts = [f"Total portfolio value is €{total_portfolio_value_eur:,.2f} across {len(positions)} positions."]
        if active_profile:
            if rebalance_needed:
                msg_parts.append(
                    f"Active profile '{active_profile['name']}' indicates {len(drift_alerts)} allocation bucket(s) need rebalancing."
                )
            else:
                msg_parts.append(f"Active profile '{active_profile['name']}' is on target.")
        if cash_balance_eur > 0:
            msg_parts.append(f"Liquid cash balance is €{cash_balance_eur:,.2f}.")

        return {
            "success": True,
            "empty_dataset": False,
            "total_portfolio_value_eur": total_portfolio_value_eur,
            "total_portfolio_value_formatted": f"€{total_portfolio_value_eur:,.2f}",
            "cash_balance_eur": cash_balance_eur,
            "cash_balance_formatted": f"€{cash_balance_eur:,.2f}",
            "asset_classes_eur": asset_classes,
            "holdings_by_asset_type_eur": holdings_by_type,
            "positions": positions,
            "active_allocation_profile": active_profile,
            "allocation_targets": targets_list,
            "allocation_drift": drift_data,
            "rebalance_needed": rebalance_needed,
            "risk_profile": risk_prof,
            "message": " ".join(msg_parts),
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


def tool_get_spending_by_category(
    year: int | None = None,
    month: int | None = None,
) -> dict[str, Any]:
    """Get aggregated spending by category for a specific month and year, or all-time."""
    # Parameter sanitization
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

        if clean_year is not None and clean_month is not None:
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
) -> dict[str, Any]:
    """Retrieve recent transactions filtered optionally by category name."""
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


def tool_get_monthly_cashflow(year: int | None = None) -> dict[str, Any]:
    """Get monthly cashflow summary (income, fixed, discretionary, savings)."""
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
        if clean_year is not None:
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
            "message": f"Retrieved cashflow data for {len(df)} months.",
        }
    finally:
        conn.close()



def tool_search_dutch_law_vault(
    query: str,
    category: str | None = None,
    effective_year: int | None = None,
) -> dict[str, Any]:
    """Search the Dutch Financial Law Vector Vault using hybrid FTS5 and sqlite-vec RRF search."""
    if not query or not str(query).strip():
        return {
            "success": False,
            "message": "Search query cannot be empty. Please specify a financial, tax, or legal question.",
        }
    clean_query = str(query).strip()

    clean_year = None
    if effective_year is not None:
        try:
            clean_year = int(effective_year)
            if not (1900 <= clean_year <= 2100):
                return {
                    "success": False,
                    "message": f"Invalid effective year '{effective_year}'. Must be between 1900 and 2100.",
                }
        except (ValueError, TypeError):
            return {
                "success": False,
                "message": f"Invalid effective year '{effective_year}'. Must be a 4-digit numeric year.",
            }

    results = search_legal_vault(clean_query, category=category, top_k=4, effective_year=clean_year)
    if not results:
        # Graceful fallback to legacy knowledge base if no statutory article matches
        legacy_res = search_knowledge_base(clean_query, top_k=3, category=category)
        if legacy_res:
            citations = [
                {
                    "article_ref": r.get("id", "Guidance"),
                    "statute_title": r.get("title", "Dutch Tax & Mortgage Guidance"),
                    "summary": r.get("content", "")[:220],
                    "content": r.get("content", ""),
                    "score": r.get("score", 0.75),
                    "effective_year": 2026,
                }
                for r in legacy_res
            ]
            return {
                "success": True,
                "results": legacy_res,
                "citations": citations,
                "message": f"Retrieved {len(legacy_res)} articles from knowledge base.",
            }
        return {
            "success": False,
            "results": [],
            "citations": [],
            "message": f"No statutory articles found for query '{clean_query}'.",
        }

    citations = [
        {
            "chunk_id": r.chunk_id,
            "article_ref": r.article_ref,
            "chunk_title": r.chunk_title,
            "statute_title": r.doc_title,
            "category": r.category,
            "effective_year": r.effective_year,
            "summary": r.summary,
            "content": r.content,
            "juriconnect_ref": r.juriconnect_ref,
            "source_url": r.source_url,
            "score": r.score,
        }
        for r in results
    ]

    return {
        "success": True,
        "results": [
            {
                "id": f"{r.doc_id}_{r.chunk_id}",
                "title": f"{r.article_ref} ({r.doc_title})",
                "category": r.category,
                "content": r.content,
                "score": r.score,
            }
            for r in results
        ],
        "citations": citations,
        "message": f"Retrieved {len(results)} statutory citations from Dutch Financial Law Vault.",
    }


def tool_lookup_tax_law_article(article_ref: str) -> dict[str, Any]:
    """Look up an exact Dutch statutory tax code or legal article reference (e.g. 'Art. 3.16', 'Art. 5.2', 'Art. 3.120')."""
    if not article_ref or not str(article_ref).strip():
        return {
            "success": False,
            "message": "Article reference cannot be empty. Please specify an article reference such as 'Art. 3.16' or 'Art. 5.2'.",
        }
    clean_ref = str(article_ref).strip()
    res = lookup_article(clean_ref)
    if not res:
        return {
            "success": False,
            "message": f"Article reference '{clean_ref}' not found in the Dutch Financial Law Vault.",
        }

    citation = {
        "chunk_id": res.chunk_id,
        "article_ref": res.article_ref,
        "chunk_title": res.chunk_title,
        "statute_title": res.doc_title,
        "category": res.category,
        "effective_year": res.effective_year,
        "summary": res.summary,
        "content": res.content,
        "juriconnect_ref": res.juriconnect_ref,
        "source_url": res.source_url,
        "score": res.score,
    }

    return {
        "success": True,
        "article": citation,
        "citations": [citation],
        "message": f"Found statutory article {res.article_ref} from {res.doc_title}.",
    }


def tool_search_financial_knowledge_base(query: str, category: str | None = None) -> dict[str, Any]:
    """Search the local knowledge base for Dutch tax laws, Box 1/3 rules, pension spaces, or mortgages."""
    return tool_search_dutch_law_vault(query, category=category)


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
    employer_pension_match_pct: float = 0,
    factor_a: float = 0,
    green_investments_eur: float = 0,
    reserveringsruimte_eur: float = 0,
) -> dict[str, Any]:
    """Save user tax profile to the database."""
    conn = database.connect(DB_PATH)
    try:
        with conn:
            conn.execute(
                "INSERT INTO tax_profile (id, gross_annual_income, has_fiscal_partner, has_30_percent_ruling, "
                "is_entrepreneur, owns_home, birth_year, has_13th_month, expected_bonus_eur, pension_contribution_pct, "
                "employer_pension_match_pct, factor_a_minor, green_investments_minor, reserveringsruimte_minor) "
                "VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET gross_annual_income=excluded.gross_annual_income, "
                "has_fiscal_partner=excluded.has_fiscal_partner, has_30_percent_ruling=excluded.has_30_percent_ruling, "
                "is_entrepreneur=excluded.is_entrepreneur, owns_home=excluded.owns_home, birth_year=excluded.birth_year, "
                "has_13th_month=excluded.has_13th_month, expected_bonus_eur=excluded.expected_bonus_eur, "
                "pension_contribution_pct=excluded.pension_contribution_pct, employer_pension_match_pct=excluded.employer_pension_match_pct, "
                "factor_a_minor=excluded.factor_a_minor, green_investments_minor=excluded.green_investments_minor, "
                "reserveringsruimte_minor=excluded.reserveringsruimte_minor, "
                "updated_at=datetime('now')",
                (
                    gross_annual_income if gross_annual_income is not None else 0.0,
                    1 if has_fiscal_partner else 0,
                    1 if has_30_percent_ruling else 0,
                    1 if is_entrepreneur else 0,
                    1 if owns_home else 0,
                    birth_year,
                    1 if has_13th_month else 0,
                    int(expected_bonus_eur) if expected_bonus_eur is not None else 0,
                    pension_contribution_pct if pension_contribution_pct is not None else 0.0,
                    employer_pension_match_pct if employer_pension_match_pct is not None else 0.0,
                    int(round((factor_a or 0.0) * 100)),
                    int(round((green_investments_eur or 0.0) * 100)),
                    int(round((reserveringsruimte_eur or 0.0) * 100)),
                ),
            )
        return {
            "success": True,
            "message": f"Tax profile saved successfully: Gross Income €{(gross_annual_income or 0):,.2f}, Fiscal Partner: {bool(has_fiscal_partner)}, Factor A: €{(factor_a or 0):,.0f}, Green Assets: €{(green_investments_eur or 0):,.0f}."
        }
    finally:
        conn.close()


def tool_simulate_tax_optimization(capital_eur: float, horizon_years: int = 10) -> dict[str, Any]:
    """Simulate 4-way capital trade-off (Mortgage Prepayment vs. Pillar 3 Jaarruimte vs. Certified Groenfonds vs. Taxable ETF)."""
    try:
        clean_capital = float(capital_eur)
    except (ValueError, TypeError):
        return {
            "success": False,
            "message": f"Invalid capital amount '{capital_eur}'. Please provide a numeric value.",
        }
    if clean_capital <= 0:
        return {
            "success": False,
            "message": f"Capital amount must be greater than 0, got €{clean_capital:,.2f}.",
        }

    try:
        clean_horizon = int(horizon_years)
    except (ValueError, TypeError):
        clean_horizon = 10
    if not (1 <= clean_horizon <= 50):
        return {
            "success": False,
            "message": f"Horizon must be between 1 and 50 years, got {horizon_years}.",
        }

    conn = database.connect_readonly(DB_PATH)
    try:
        sim = simulate_capital_allocation_tradeoff(clean_capital, clean_horizon, conn=conn)
        df = sim["trajectory_df"]

        fig = px.line(
            df,
            x="Year",
            y=["Mortgage Prepayment", "Pillar 3 Pension (Jaarruimte)", "Certified Groenfonds", "Taxable Box 3 ETF"],
            title=f"Capital Allocation Strategy Comparison (€{clean_capital:,.0f} Horizon {clean_horizon}y)",
            labels={"value": "Total Net Wealth (€)", "variable": "Strategy"},
            markers=True,
        )
        fig.update_layout(
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            margin=dict(l=10, r=10, t=50, b=10),
            hovermode="x unified",
        )

        winner = sim["winner_strategy"].replace("_", " ").title()
        msg = (
            f"Simulated €{clean_capital:,.0f} across {clean_horizon} years. "
            f"Top outcome: {winner} yielding €{sim['final_values'][sim['winner_strategy']]:,.2f} net. "
            f"Immediate Pillar 3 tax refund: €{sim['immediate_pension_refund_eur']:,.2f}."
        )

        return {
            "success": True,
            "simulation": sim,
            "figure": fig,
            "df": df,
            "message": msg,
        }
    finally:
        conn.close()


def tool_calculate_pension_room(gross_income: float | None = None, factor_a: float = 0.0) -> dict[str, Any]:
    """Calculate official Dutch Pillar 3 pension gap (Jaarruimte & Reserveringsruimte) and immediate Box 1 tax refund."""
    clean_income = None
    if gross_income is not None:
        try:
            clean_income = float(gross_income)
            if clean_income < 0:
                return {
                    "success": False,
                    "message": f"Gross annual income cannot be negative, got €{clean_income:,.2f}.",
                }
        except (ValueError, TypeError):
            return {
                "success": False,
                "message": f"Invalid gross income '{gross_income}'. Please provide a valid numeric amount.",
            }

    try:
        clean_factor_a = float(factor_a)
        if clean_factor_a < 0:
            return {
                "success": False,
                "message": f"Factor A cannot be negative, got €{clean_factor_a:,.2f}.",
            }
    except (ValueError, TypeError):
        clean_factor_a = 0.0

    conn = database.connect_readonly(DB_PATH)
    try:
        if clean_income is None:
            profile = conn.execute("SELECT gross_annual_income, factor_a_minor, reserveringsruimte_minor FROM tax_profile WHERE id = 1").fetchone()
            clean_income = float(profile["gross_annual_income"]) if profile else 65000.0
            if clean_factor_a == 0.0 and profile and "factor_a_minor" in profile.keys():
                clean_factor_a = float(profile["factor_a_minor"]) / 100.0

        pension_data = calculate_jaarruimte(gross_income=clean_income, factor_a=clean_factor_a)
        msg = (
            f"Calculated Jaarruimte for €{clean_income:,.0f} gross (Factor A: €{clean_factor_a:,.0f}): "
            f"Annual room €{pension_data['annual_jaarruimte']:,.2f}. "
            f"Immediate Box 1 tax refund: €{pension_data['immediate_tax_rebate']:,.2f} "
            f"({pension_data['marginal_tax_rate']*100:.2f}% marginal bracket). "
            f"20-year compound tax shield: €{pension_data['compounding_tax_shield']:,.2f}."
        )
        return {
            "success": True,
            "pension_data": pension_data,
            "message": msg,
        }
    finally:
        conn.close()


def tool_analyze_green_fund_strategy(target_allocation: float | None = None) -> dict[str, Any]:
    """Analyze Dutch Groenfondsen double tax benefit (Box 3 wealth tax exemption and 0.1% Box 1 credit)."""
    clean_target = None
    if target_allocation is not None:
        try:
            clean_target = float(target_allocation)
            if clean_target < 0:
                return {
                    "success": False,
                    "message": f"Target allocation cannot be negative, got €{clean_target:,.2f}.",
                }
        except (ValueError, TypeError):
            return {
                "success": False,
                "message": f"Invalid target allocation '{target_allocation}'. Please provide a valid numeric amount.",
            }

    conn = database.connect_readonly(DB_PATH)
    try:
        nw = calculate_current_net_worth(conn)
        total_wealth = nw["liquid_cash"] + nw["invested"]
        profile = conn.execute("SELECT * FROM tax_profile WHERE id = 1").fetchone()
        has_partner = bool(profile["has_fiscal_partner"]) if profile else False
        current_green = (float(profile["green_investments_minor"]) / 100.0) if profile and "green_investments_minor" in profile.keys() else 0.0
        prospective = clean_target if clean_target is not None else (25000.0 if current_green == 0 else 0.0)

        arb = calculate_groenfondsen_arbitrage(
            total_wealth=total_wealth,
            current_green=current_green,
            prospective_green=prospective,
            has_fiscal_partner=has_partner,
        )

        msg = (
            f"Groenfondsen Analysis: Exemption cap €{arb['exemption_cap']:,.0f}. "
            f"Annual tax benefit for €{arb['total_green']:,.0f} green allocation: "
            f"€{arb['total_annual_tax_benefit']:,.2f} (avoiding €{arb['box3_annual_savings']:,.2f} in Box 3 + "
            f"€{arb['box1_annual_credit']:,.2f} Box 1 credit). "
            f"Guaranteed tax alpha: ~{arb['guaranteed_tax_alpha_pct']:.2f}%."
        )
        return {
            "success": True,
            "arbitrage": arb,
            "message": msg,
        }
    finally:
        conn.close()


def tool_diagnose_tax_leaks() -> dict[str, Any]:
    """Scan current user assets, liabilities, and income to proactively diagnose tax inefficiencies."""
    conn = database.connect_readonly(DB_PATH)
    try:
        leaks = diagnose_tax_leakage(conn)
        tot_savings = sum(l["potential_annual_saving_eur"] for l in leaks)
        msg = f"Diagnosed {len(leaks)} tax optimization opportunities with up to €{tot_savings:,.2f} in potential annual savings."
        return {
            "success": True,
            "leak_count": len(leaks),
            "total_potential_annual_savings_eur": tot_savings,
            "recommendations": leaks,
            "message": msg,
        }
    finally:
        conn.close()


def tool_ingest_financial_document(doc_title: str, content: str, category: str = "custom") -> dict[str, Any]:
    """Index a custom text/markdown document (e.g. UPO pension statement, mortgage advice deed) into local RAG."""
    conn = database.connect(DB_PATH)
    try:
        res = ingest_user_document(title=doc_title, content=content, category=category, conn=conn)
        return res
    finally:
        conn.close()


def tool_analyze_tax_situation() -> dict[str, Any]:
    """Fetch the user's gross income from tax_profile, their investment/cash balances for Box 3, and return them for analysis."""
    conn = database.connect_readonly(DB_PATH)
    try:
        profile = conn.execute("SELECT * FROM tax_profile WHERE id = 1").fetchone()
        if not profile or profile["gross_annual_income"] == 0:
            guidance = "No gross annual income or tax profile configured yet. Please open the Tax Analysis tab or tell me your gross income to configure Box 1 and Box 3 calculations."
            return {
                "success": False,
                "empty_dataset": True,
                "guidance": guidance,
                "message": f"Tax profile is not configured. {guidance}",
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
                "total_wealth": cash_bal + invested_bal,
            },
            "message": "Tax data retrieved successfully.",
        }
    finally:
        conn.close()


def tool_analyze_mortgage() -> dict[str, Any]:
    """Fetch liability details, schedule, and interest rates for mortgage analysis."""
    conn = database.connect_readonly(DB_PATH)
    try:
        liabilities = conn.execute("SELECT * FROM liabilities").fetchall()
        if not liabilities:
            guidance = "No active mortgages or liabilities configured in your ledger. You can add a mortgage on the Mortgage page to track amortization schedules, interest rates, and deductible interest."
            return {
                "success": False,
                "empty_dataset": True,
                "guidance": guidance,
                "message": f"No active mortgages or loans found. {guidance}",
            }

        mortgage_data = []
        for lib in liabilities:
            lib_id = lib["id"]
            rate = conn.execute("SELECT annual_rate, fixed_until FROM liability_rate_periods WHERE liability_id = ? ORDER BY from_date DESC LIMIT 1", (lib_id,)).fetchone()
            schedule = conn.execute("SELECT due_date, payment_minor, interest_minor, principal_minor, balance_minor FROM liability_schedule WHERE liability_id = ? AND due_date >= date('now') ORDER BY due_date ASC LIMIT 3", (lib_id,)).fetchall()

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
        "message": f"Displaying the {form_type.replace('_', ' ')} form..."
    }


__all__ = [
    "COPILOT_TOOLS_SCHEMA",
    "tool_get_current_net_worth",
    "tool_toggle_privacy_mode",
    "tool_set_theme",
    "tool_set_active_allocation_profile",
    "tool_update_savings_rate",
    "tool_add_mortgage_payment",
    "tool_save_risk_profile",
    "tool_get_risk_profile",
    "tool_analyze_investments",
    "tool_parse_and_import_file",
    "tool_auto_categorize_uncategorized_transactions",
    "tool_get_spending_by_category",
    "tool_get_recent_transactions",
    "tool_get_monthly_cashflow",
    "tool_search_dutch_law_vault",
    "tool_lookup_tax_law_article",
    "tool_search_financial_knowledge_base",
    "tool_search_web",
    "tool_analyze_market_data",
    "tool_save_tax_profile",
    "tool_simulate_tax_optimization",
    "tool_calculate_pension_room",
    "tool_analyze_green_fund_strategy",
    "tool_diagnose_tax_leaks",
    "tool_ingest_financial_document",
    "tool_analyze_tax_situation",
    "tool_analyze_mortgage",
    "tool_request_profile_form",
]



