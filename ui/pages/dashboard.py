from datetime import date, datetime, timedelta
import pandas as pd
import streamlit as st

from config import DB_PATH
from db import database
from services.analytics import calculate_burn_and_runway, calculate_savings_rate, detect_recurring_charges
from ui.charts import build_net_worth_area_chart, build_spending_donut
from ui.components import empty_state, kpi_card, section_header
from ui.filters import build_where_clause, render_sidebar_filters


def render():
    conn = database.connect(DB_PATH)

    col_title, col_sync = st.columns([3, 1])
    with col_title:
        st.title("Financial Overview")
    with col_sync:
        st.write("")
        if st.button("🔄 Sync Now", use_container_width=True):
            with st.spinner("Syncing configured banks, brokers, and quotes..."):
                from services.sync_service import sync_all
                sync_all(conn)
                st.rerun()

    filters = render_sidebar_filters()

    # 1. Accounts & Balances
    accounts = conn.execute("SELECT * FROM accounts WHERE is_active = 1").fetchall()
    if not accounts:
        conn.close()
        empty_state(
            "No Accounts Found",
            "Get started by importing your bank or brokerage statements in the 'Import' page, or connect an API in 'Settings'.",
        )
        return

    # Compute current balances
    # Latest balance per account from account_snapshots or sum of transactions
    acc_balances: dict[str, float] = {}
    for acc in accounts:
        row = conn.execute(
            "SELECT balance_eur_minor FROM account_snapshots WHERE account_id = ? ORDER BY snapshot_date DESC LIMIT 1",
            (acc["id"],),
        ).fetchone()
        if row:
            acc_balances[acc["id"]] = row["balance_eur_minor"] / 100.0
        else:
            tx_sum = conn.execute(
                "SELECT SUM(amount_eur_minor) AS total FROM transactions WHERE account_id = ?",
                (acc["id"],),
            ).fetchone()
            acc_balances[acc["id"]] = (tx_sum["total"] or 0) / 100.0

    # Liability balance as of today or manual statement override
    lib_row = conn.execute("SELECT balance_override_minor, balance_override_date FROM liabilities LIMIT 1").fetchone()
    if lib_row and lib_row["balance_override_minor"]:
        mortgage_balance = lib_row["balance_override_minor"] / 100.0
    else:
        today_str = date.today().isoformat()
        mortgage_bal_row = conn.execute(
            "SELECT balance_minor FROM liability_schedule WHERE due_date <= ? ORDER BY due_date DESC LIMIT 1",
            (today_str,),
        ).fetchone()
        if not mortgage_bal_row:
            mortgage_bal_row = conn.execute("SELECT balance_minor FROM liability_schedule ORDER BY due_date ASC LIMIT 1").fetchone()
        mortgage_balance = (mortgage_bal_row["balance_minor"] / 100.0) if mortgage_bal_row else 0.0

    # Total cash & invested
    liquid_cash = sum(
        bal for acc in accounts if acc["asset_class"] == "cash" and (bal := acc_balances.get(acc["id"], 0.0))
    )
    # Calculate invested balance: use live holdings values (v_holdings), fallback to snapshots for accounts without holdings
    holdings_acc_rows = conn.execute("SELECT DISTINCT account_id FROM holdings").fetchall()
    holdings_acc_ids = {r["account_id"] for r in holdings_acc_rows}
    invested_row = conn.execute(
        "SELECT SUM(CASE WHEN value_eur > 0 THEN value_eur ELSE cost_basis END) as total FROM v_holdings"
    ).fetchone()
    invested_holdings = float(invested_row["total"] or 0.0) if invested_row else 0.0
    invested_other = sum(
        bal for acc in accounts
        if acc["asset_class"] == "investment"
        and acc["id"] not in holdings_acc_ids
        and (bal := acc_balances.get(acc["id"], 0.0))
    )
    invested = invested_holdings + invested_other
    net_worth = liquid_cash + invested - mortgage_balance

    # 2. Monthly cashflow for savings rate and burn rate
    where_sql, params = build_where_clause(filters, table_alias="t")
    cf_query = f"""
    SELECT strftime('%Y-%m', t.booking_date) AS month,
           SUM(CASE WHEN c.kind = 'income' THEN t.amount_eur_minor ELSE 0 END) / 100.0 AS income,
           SUM(CASE WHEN c.kind IN ('fixed','discretionary') THEN -t.amount_eur_minor ELSE 0 END) / 100.0 AS expenses
    FROM transactions t
    LEFT JOIN categories c ON c.id = t.category_id
    {where_sql}
    GROUP BY strftime('%Y-%m', t.booking_date)
    ORDER BY month ASC
    """
    cf_rows = conn.execute(cf_query, params).fetchall()
    monthly_expenses = [r["expenses"] for r in cf_rows if r["expenses"] > 0]
    burn_rate, runway_months, runway_days = calculate_burn_and_runway(monthly_expenses, liquid_cash)

    # Latest month savings rate
    savings_rate = 0.0
    if cf_rows:
        last_m = cf_rows[-1]
        savings_rate = calculate_savings_rate(last_m["income"], last_m["expenses"])

    # KPI Ribbon
    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        kpi_card("Net Worth", f"€{net_worth:,.2f}", subtext="Assets minus liabilities")
    with c2:
        kpi_card("Liquid Cash", f"€{liquid_cash:,.2f}", subtext="Checking & savings")
    with c3:
        kpi_card("Investments", f"€{invested:,.2f}", subtext="Securities & crypto")
    with c4:
        kpi_card("Savings Rate", f"{savings_rate:.1f}%", is_positive=savings_rate >= 20.0, subtext="Current period")
    with c5:
        runway_txt = f"{runway_months:.1f} mo" if runway_months < 60 else "5+ yrs"
        kpi_card("Runway", runway_txt, is_positive=runway_months >= 6.0, subtext=f"{int(runway_days)} days buffer")

    # Main Chart: Net worth trend
    section_header("Net Worth Trend", "Evolution of assets and liabilities over time")
    nw_query = """
    SELECT date, asset_class, value_eur
    FROM v_net_worth_daily
    ORDER BY date ASC
    """
    nw_df = pd.read_sql_query(nw_query, conn)
    if not nw_df.empty:
        st.plotly_chart(build_net_worth_area_chart(nw_df), use_container_width=True)
    else:
        st.info("Net worth historical daily snapshots will populate automatically as transactions and quotes accumulate.")

    # Lower Grid: Spending Donut + Recurring Bills
    col_left, col_right = st.columns([1, 1])

    with col_left:
        section_header("Spending by Category", "Current filtered range")
        spend_query = f"""
        SELECT c.name AS category, -t.amount_eur_minor / 100.0 AS amount_eur
        FROM transactions t
        JOIN categories c ON c.id = t.category_id
        {where_sql} AND t.amount_eur_minor < 0 AND c.kind IN ('fixed', 'discretionary')
        """
        spend_df = pd.read_sql_query(spend_query, conn, params=params)
        if not spend_df.empty:
            st.plotly_chart(build_spending_donut(spend_df, group_col="category"), use_container_width=True)
        else:
            st.caption("No expense transactions found for the selected filters.")

    with col_right:
        section_header("Upcoming Recurring Bills", "Detected automatically from transactions")
        all_tx_rows = [dict(r) for r in conn.execute("SELECT * FROM v_transactions ORDER BY booking_date DESC LIMIT 500").fetchall()]
        recurring = detect_recurring_charges(all_tx_rows)
        if recurring:
            rec_df = pd.DataFrame(recurring[:6])[["merchant", "cadence", "amount_eur", "next_expected_date"]]
            rec_df.columns = ["Merchant", "Cadence", "Amount (€)", "Next Expected"]
            st.dataframe(rec_df, use_container_width=True, hide_index=True)
        else:
            st.caption("No recurring subscriptions detected yet.")

    conn.close()
