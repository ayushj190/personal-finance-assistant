from datetime import date, datetime
from typing import Any
import pandas as pd
import streamlit as st

from config import DB_PATH
from db import database
from services.analytics import calculate_burn_and_runway, detect_recurring_charges
from ui.charts import build_net_worth_area_chart, build_spending_donut
from ui.components import empty_state, format_money, is_hidden, kpi_card, section_header, status_badge


def get_account_status(acc: dict[str, Any], sync_logs: list[dict[str, Any]]) -> tuple[str, str]:
    """Derive status badge label and kind for any bank or investment account."""
    provider = acc.get("provider", "manual")
    inst = (acc.get("institution") or "").lower()

    matched_log = None
    for log in sync_logs:
        connector = (log.get("connector") or "").lower()
        if provider == "enable_banking":
            if "enable_banking" in connector and any(w in connector for w in inst.split()):
                matched_log = log
                break
            elif "enable_banking" in connector and not matched_log:
                matched_log = log
        elif provider == "etoro" and "etoro" in connector:
            matched_log = log
            break
        elif provider == "manual" and any(w in connector for w in inst.split()):
            matched_log = log
            break

    if matched_log:
        status = matched_log.get("status")
        if status == "needs_reauth":
            return ("🟡 Re-auth", "warning")
        elif status == "error":
            return ("🔴 Error", "danger")

    if provider == "manual":
        return ("📝 Manual", "neutral")
    return ("🟢 Connected", "success")


def get_institution_icon(institution: str) -> str:
    inst = institution.lower()
    if "abn" in inst:
        return "🏦"
    elif "revolut" in inst:
        return "🟣"
    elif "etoro" in inst:
        return "📈"
    elif "trade republic" in inst:
        return "🟠"
    elif "ing" in inst:
        return "🦁"
    elif "rabobank" in inst:
        return "🟧"
    return "💳"


def render():
    conn = database.connect(DB_PATH)

    col_title, col_sync = st.columns([3, 1])
    with col_title:
        st.title("Financial Overview")

    # 1. Accounts & Balances
    accounts = [dict(r) for r in conn.execute(
        "SELECT * FROM accounts WHERE is_active = 1").fetchall()]
    if not accounts:
        conn.close()
        empty_state(
            "No Accounts Found",
            "Get started by importing your bank or brokerage statements in the 'Import' page, or connect an API in 'Settings'.",
        )
        return

    # Fetch sync logs to derive status for all bank & investment accounts
    sync_logs = [dict(r) for r in conn.execute(
        "SELECT connector, started_at, status, message FROM sync_log ORDER BY started_at DESC LIMIT 50"
    ).fetchall()]

    # Compute current balances
    acc_balances: dict[int, float] = {}
    acc_subtexts: dict[int, str] = {}
    today = date.today()

    for acc in accounts:
        row = conn.execute(
            "SELECT balance_minor, balance_eur_minor, snapshot_date FROM account_snapshots WHERE account_id = ? ORDER BY snapshot_date DESC LIMIT 1",
            (acc["id"],),
        ).fetchone()
        if row:
            base_bal_eur = row["balance_eur_minor"] / 100.0
            apy = acc.get("apy")
            subtext = ""
            if apy and apy > 0:
                snap_date_str = str(row["snapshot_date"])[:10]
                try:
                    snap_date = datetime.strptime(
                        snap_date_str, "%Y-%m-%d").date()
                    days = (today - snap_date).days
                    if days > 0:
                        daily_rate = (apy / 100.0) / 365.0
                        accrued = base_bal_eur * (daily_rate * days)
                        base_bal_eur += accrued
                        subtext = f"+€{accrued:,.2f} accrued ({apy}% APY)"
                except Exception:
                    pass
            acc_balances[acc["id"]] = base_bal_eur
            acc_subtexts[acc["id"]] = subtext
        else:
            tx_sum = conn.execute(
                "SELECT SUM(amount_eur_minor) AS total FROM transactions WHERE account_id = ?",
                (acc["id"],),
            ).fetchone()
            acc_balances[acc["id"]] = (tx_sum["total"] or 0) / 100.0
            acc_subtexts[acc["id"]] = ""

    # Liability balance & Property Asset
    lib_row = conn.execute(
        "SELECT original_principal_minor, home_value_minor, balance_override_minor, balance_override_date FROM liabilities LIMIT 1"
    ).fetchone()
    home_value = 0.0
    mortgage_balance = 0.0
    home_equity = 0.0
    if lib_row:
        orig_p = (lib_row["original_principal_minor"] /
                  100.0) if lib_row["original_principal_minor"] else 0.0
        home_value = (lib_row["home_value_minor"] /
                      100.0) if lib_row["home_value_minor"] is not None else orig_p
        if lib_row["balance_override_minor"]:
            mortgage_balance = lib_row["balance_override_minor"] / 100.0
        else:
            today_str = date.today().isoformat()
            mortgage_bal_row = conn.execute(
                "SELECT balance_minor FROM liability_schedule WHERE due_date <= ? ORDER BY due_date DESC LIMIT 1",
                (today_str,),
            ).fetchone()
            if not mortgage_bal_row:
                mortgage_bal_row = conn.execute(
                    "SELECT balance_minor FROM liability_schedule ORDER BY due_date ASC LIMIT 1").fetchone()
            mortgage_balance = (
                mortgage_bal_row["balance_minor"] / 100.0) if mortgage_bal_row else 0.0
        home_equity = home_value - mortgage_balance

    # Total cash & invested
    liquid_cash = sum(
        bal for acc in accounts if acc.get("asset_class") == "cash" and (bal := acc_balances.get(acc["id"], 0.0))
    )
    holdings_acc_rows = conn.execute(
        "SELECT DISTINCT account_id FROM holdings").fetchall()
    holdings_acc_ids = {r["account_id"] for r in holdings_acc_rows}
    invested_row = conn.execute(
        "SELECT SUM(CASE WHEN value_eur > 0 THEN value_eur ELSE cost_basis END) as total FROM v_holdings"
    ).fetchone()
    invested_holdings = float(
        invested_row["total"] or 0.0) if invested_row else 0.0
    invested_other = sum(
        bal for acc in accounts
        if acc.get("asset_class") == "investment"
        and acc["id"] not in holdings_acc_ids
        and (bal := acc_balances.get(acc["id"], 0.0))
    )
    invested = invested_holdings + invested_other
    net_worth = liquid_cash + invested + home_equity

    # Monthly cashflow for runway calculation
    cf_query = """
    SELECT strftime('%Y-%m', t.booking_date) AS month,
           SUM(CASE WHEN c.kind IN ('fixed','discretionary') THEN -t.amount_eur_minor ELSE 0 END) / 100.0 AS expenses
    FROM transactions t
    LEFT JOIN categories c ON c.id = t.category_id
    WHERE t.is_internal_transfer = 0
    GROUP BY strftime('%Y-%m', t.booking_date)
    ORDER BY month ASC
    """
    cf_rows = conn.execute(cf_query).fetchall()
    monthly_expenses = [r["expenses"] for r in cf_rows if r["expenses"] > 0]
    burn_rate, runway_months, runway_days = calculate_burn_and_runway(
        monthly_expenses, liquid_cash)

    # Standardized 4-KPI Ribbon (Savings rate removed per user instructions)
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        nw_sub = f"Assets minus liabilities (Home equity: {format_money(home_equity)})" if lib_row else "Assets minus liabilities"
        kpi_card("Net Worth", format_money(net_worth), subtext=nw_sub)
    with c2:
        kpi_card("Liquid Cash", format_money(liquid_cash),
                 subtext="Checking & cash reserves")
    with c3:
        kpi_card("Investments", format_money(invested),
                 subtext="Securities & portfolio holdings")
    with c4:
        runway_txt = f"{runway_months:.1f} mo" if runway_months < 60 else "5+ yrs"
        kpi_card("Runway", runway_txt,
                 subtext=f"{int(runway_days)} days buffer")

    # Accounts & Balances Grid - Standardized layout & button alignment
    section_header("Accounts & Balances",
                   "Real-time balances and connection statuses across connected institutions")

    currency_symbols = {"EUR": "€", "USD": "$", "TRY": "₺", "GBP": "£"}

    COLS_PER_ROW = 4
    for i in range(0, len(accounts), COLS_PER_ROW):
        row_accounts = accounts[i:i + COLS_PER_ROW]
        cols = st.columns(COLS_PER_ROW)
        for idx, acc in enumerate(row_accounts):
            col = cols[idx]
            bal = acc_balances.get(acc["id"], 0.0)
            sub = acc_subtexts.get(acc["id"], "")
            curr = acc.get("currency", "EUR")
            sym = currency_symbols.get(curr, "€")
            badge_txt, badge_kind = get_account_status(acc, sync_logs)
            icon = get_institution_icon(acc.get("institution", ""))

            with col:
                with st.container(border=True):
                    # Top Row: Institution + Status Badge
                    st.markdown(
                        f"<div style='display: flex; justify-content: space-between; align-items: center;'><div>**{icon} {acc['institution']}**</div>{status_badge(badge_txt, badge_kind)}</div>",
                        unsafe_allow_html=True,
                    )

                    # Subtitle: Name & Currency
                    st.caption(f"{acc['name']} • {curr}")

                    # Balance
                    st.markdown(f"### {format_money(bal, sym)}")

                    # Informational line (consistent slot height)
                    if sub:
                        st.caption(f"✨ {sub}")
                    elif acc.get("apy"):
                        st.caption(f"📈 APY: {acc['apy']}%")
                    elif acc.get("asset_class") == "investment":
                        st.caption("📈 Trading & Holdings")
                    else:
                        st.caption("💳 Direct Checking Account")

                    # Standardized bottom popover button
                    if acc.get("asset_class") == "cash":
                        with st.popover("✏️ Adjust Balance", use_container_width=True):
                            with st.form(f"adjust_bal_dash_{acc['id']}"):
                                st.caption(
                                    f"Adjust balance for **{acc['name']}**")
                                new_adj_bal = st.number_input(
                                    f"Balance ({sym})",
                                    value=float(bal),
                                    min_value=0.0,
                                    step=50.0,
                                    format="%.2f",
                                    key=f"dash_bal_in_{acc['id']}",
                                )
                                if st.form_submit_button("Update Balance", type="primary"):
                                    val_min = int(round(new_adj_bal * 100))
                                    database.upsert_snapshots(conn, [{
                                        "account_id": acc["id"],
                                        "snapshot_date": today.isoformat(),
                                        "balance_minor": val_min,
                                        "balance_eur_minor": val_min,
                                    }])
                                    st.rerun()
                    else:
                        with st.popover("ℹ️ Account Details", use_container_width=True):
                            st.markdown(f"**{acc['name']}**")
                            st.write(f"**Institution:** {acc['institution']}")
                            st.write(
                                f"**Asset Class:** {acc.get('asset_class', 'investment').title()}")
                            st.write(f"**Currency:** {curr}")
                            st.caption(f"Status: {badge_txt}")

    # Main Chart: Net worth trend
    section_header("Net Worth Trend",
                   "Evolution of assets and liabilities over time")
    nw_query = """
    SELECT date, asset_class, value_eur
    FROM v_net_worth_daily
    ORDER BY date ASC
    """
    nw_df = pd.read_sql_query(nw_query, conn)
    if not nw_df.empty:
        st.plotly_chart(build_net_worth_area_chart(nw_df),
                        use_container_width=True, theme=None)
    else:
        st.info("Net worth historical daily snapshots will populate automatically as transactions and quotes accumulate.")

    # Lower Grid: Spending Donut + Recurring Bills
    col_left, col_right = st.columns([1, 1])

    with col_left:
        section_header("Spending by Category", "Last 30 days expenses")
        spend_query = """
        SELECT c.name AS category, -t.amount_eur_minor / 100.0 AS amount_eur
        FROM transactions t
        JOIN categories c ON c.id = t.category_id
        WHERE t.amount_eur_minor < 0
          AND c.kind IN ('fixed', 'discretionary')
          AND t.is_internal_transfer = 0
          AND t.booking_date >= date('now', '-30 days')
        """
        spend_df = pd.read_sql_query(spend_query, conn)
        if not spend_df.empty:
            st.plotly_chart(build_spending_donut(
                spend_df, group_col="category"), use_container_width=True, theme=None)
        else:
            st.caption("No expense transactions found in the last 30 days.")

    with col_right:
        section_header("Upcoming Recurring Bills",
                       "Detected automatically from transactions")
        all_tx_rows = [dict(r) for r in conn.execute(
            "SELECT * FROM v_transactions ORDER BY booking_date DESC LIMIT 500").fetchall()]
        recurring = detect_recurring_charges(all_tx_rows)
        if recurring:
            rec_df = pd.DataFrame(recurring[:6])[
                ["merchant", "cadence", "amount_eur", "next_expected_date"]]
            rec_df.columns = ["Merchant", "Cadence", "Amount", "Next Expected"]
            if is_hidden():
                rec_df["Amount"] = rec_df["Amount"].map(
                    lambda x: format_money(x))
                amt_cfg = st.column_config.TextColumn("Amount", disabled=True)
            else:
                amt_cfg = st.column_config.NumberColumn(
                    "Amount", format="€%.2f", disabled=True)
            st.dataframe(
                rec_df,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Merchant": st.column_config.TextColumn("Merchant", width="medium"),
                    "Amount": amt_cfg
                }
            )
        else:
            st.caption("No recurring subscriptions detected yet.")

    conn.close()
