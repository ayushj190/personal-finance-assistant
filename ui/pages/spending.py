import pandas as pd
import streamlit as st

from config import DB_PATH
from db import database
from services.analytics import detect_recurring_charges
from ui.charts import build_monthly_spending_bar, build_spending_donut, build_spending_sunburst
from ui.components import format_money, kpi_card, section_header
from ui.filters import build_where_clause, render_sidebar_filters



def render():
    st.title("Spending Analysis")
    filters = render_sidebar_filters()

    conn = database.connect(DB_PATH)
    where_sql, params = build_where_clause(filters, table_alias="t")

    # Strictly exclude internal transfers, savings/investments, and inflows from spending
    where_parts = []
    if where_sql:
        where_parts.append(where_sql.replace("WHERE ", "", 1))
    where_parts.append("t.amount_eur_minor < 0")
    where_parts.append("t.is_internal_transfer = 0")
    where_parts.append("(c.kind IS NULL OR c.kind NOT IN ('savings', 'transfer', 'income'))")

    base_where = "WHERE " + " AND ".join(where_parts)

    # 1. Fetch Monthly Summary Aggregation
    monthly_query = f"""
    SELECT strftime('%Y-%m', t.booking_date) as month,
           COUNT(*) as tx_count,
           SUM(-t.amount_eur_minor) / 100.0 as total_spent,
           SUM(CASE WHEN c.kind = 'fixed' THEN -t.amount_eur_minor ELSE 0 END) / 100.0 as fixed_spent,
           SUM(CASE WHEN c.kind = 'discretionary' THEN -t.amount_eur_minor ELSE 0 END) / 100.0 as disc_spent,
           SUM(CASE WHEN c.id IS NULL THEN -t.amount_eur_minor ELSE 0 END) / 100.0 as uncat_spent
    FROM transactions t
    LEFT JOIN categories c ON c.id = t.category_id
    {base_where}
    GROUP BY month
    ORDER BY month DESC
    """
    monthly_df = pd.read_sql_query(monthly_query, conn, params=params)

    if monthly_df.empty:
        conn.close()
        st.info("No spending transactions found for the selected filter criteria.")
        return

    # 2. Fetch Detailed Spending Transactions
    detail_query = f"""
    SELECT t.booking_date,
           strftime('%Y-%m', t.booking_date) as month,
           t.merchant_normalized AS merchant,
           COALESCE(c.name, 'Uncategorized') AS category,
           COALESCE(p.name, c.name, 'Uncategorized') AS parent_category,
           COALESCE(c.kind, 'discretionary') AS category_kind,
           -t.amount_eur_minor / 100.0 AS amount_eur
    FROM transactions t
    LEFT JOIN categories c ON c.id = t.category_id
    LEFT JOIN categories p ON p.id = c.parent_id
    {base_where}
    """
    df_all = pd.read_sql_query(detail_query, conn, params=params)

    # 3. Monthly Scope Selector
    months = monthly_df["month"].tolist()
    month_options = months + ["All Months (Monthly Average)"]
    
    col_sel, col_empty = st.columns([2, 3])
    with col_sel:
        selected_scope = st.selectbox("View Scope", options=month_options, index=0)

    # Filter data according to selected scope
    if selected_scope == "All Months (Monthly Average)":
        display_df = df_all.copy()
        n_months = max(1, len(months))
        total_spent = monthly_df["total_spent"].sum() / n_months
        fixed_spent = monthly_df["fixed_spent"].sum() / n_months
        disc_spent = monthly_df["disc_spent"].sum() / n_months
        uncat_spent = monthly_df["uncat_spent"].sum() / n_months
        header_title = f"Average Monthly Expenses ({n_months} months)"
    else:
        display_df = df_all[df_all["month"] == selected_scope].copy()
        month_row = monthly_df[monthly_df["month"] == selected_scope].iloc[0]
        total_spent = float(month_row["total_spent"])
        fixed_spent = float(month_row["fixed_spent"])
        disc_spent = float(month_row["disc_spent"])
        uncat_spent = float(month_row["uncat_spent"])
        header_title = f"Monthly Expenses ({selected_scope})"

    # KPI Row
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        kpi_card("Total Expenses", f"€{total_spent:,.2f}", subtext=header_title)
    with c2:
        fixed_pct = (fixed_spent / total_spent * 100) if total_spent > 0 else 0
        kpi_card("Fixed Expenses", f"€{fixed_spent:,.2f}", subtext=f"{fixed_pct:.1f}% of total")
    with c3:
        disc_pct = (disc_spent / total_spent * 100) if total_spent > 0 else 0
        kpi_card("Discretionary", f"€{disc_spent:,.2f}", subtext=f"{disc_pct:.1f}% of total")
    with c4:
        uncat_pct = (uncat_spent / total_spent * 100) if total_spent > 0 else 0
        kpi_card("Uncategorized", f"€{uncat_spent:,.2f}", subtext=f"{uncat_pct:.1f}% of total", is_positive=uncat_spent == 0)

    # 4. Monthly Trend Chart & Summary Table
    section_header("Monthly Expenses Trend", "Month-by-month spending broken down by expense kind")
    col_chart, col_tbl = st.columns([3, 2])
    with col_chart:
        st.plotly_chart(build_monthly_spending_bar(monthly_df), use_container_width=True)
    with col_tbl:
        tbl_df = monthly_df[["month", "total_spent", "fixed_spent", "disc_spent", "uncat_spent"]].copy()
        tbl_df.columns = ["Month", "Total (€)", "Fixed (€)", "Discretionary (€)", "Uncategorized (€)"]
        for col in ["Total (€)", "Fixed (€)", "Discretionary (€)", "Uncategorized (€)"]:
            tbl_df[col] = tbl_df[col].map(lambda x: format_money(x))
        st.dataframe(tbl_df, use_container_width=True, hide_index=True)

    # 5. Expense Breakdown & Top Merchants
    section_header(f"Expense Breakdown ({selected_scope})", "Hierarchical spending across categories and merchants")
    if not display_df.empty:
        view_type = st.radio("Chart Type", options=["Sunburst", "Donut"], horizontal=True)
        if view_type == "Sunburst":
            st.plotly_chart(build_spending_sunburst(display_df), use_container_width=True)
        else:
            st.plotly_chart(build_spending_donut(display_df, group_col="category"), use_container_width=True)

        col_left, col_right = st.columns([1, 1])
        with col_left:
            section_header("Top Merchants", f"Highest spending in {selected_scope}")
            top_merchants = display_df.groupby("merchant")["amount_eur"].sum().reset_index()
            top_merchants = top_merchants.sort_values(by="amount_eur", ascending=False).head(10)
            top_merchants.columns = ["Merchant", "Spent (€)"]
            top_merchants["Spent (€)"] = top_merchants["Spent (€)"].map(lambda x: format_money(x))
            st.dataframe(top_merchants, use_container_width=True, hide_index=True)

        with col_right:
            section_header("Subscription Leak Detector", "Recurring services and annual commitments")
            all_tx_rows = [dict(r) for r in conn.execute("SELECT * FROM v_transactions ORDER BY booking_date DESC").fetchall()]
            recurring = detect_recurring_charges(all_tx_rows)
            if recurring:
                rec_df = pd.DataFrame(recurring)[["merchant", "cadence", "amount_eur", "annual_cost_eur"]]
                rec_df.columns = ["Merchant", "Cadence", "Cost / Cycle", "Annual Cost (€)"]
                rec_df["Cost / Cycle"] = rec_df["Cost / Cycle"].map(lambda x: format_money(x))
                rec_df["Annual Cost (€)"] = rec_df["Annual Cost (€)"].map(lambda x: format_money(x))
                st.dataframe(rec_df, use_container_width=True, hide_index=True)
            else:
                st.caption("No subscriptions detected.")

    conn.close()
