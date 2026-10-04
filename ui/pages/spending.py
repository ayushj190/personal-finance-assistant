import pandas as pd
import plotly.express as px
import streamlit as st

from config import DB_PATH
from db import database
from services.analytics import detect_recurring_charges
from ui.charts import build_spending_donut, build_spending_sunburst
from ui.components import kpi_card, section_header
from ui.filters import build_where_clause, render_sidebar_filters


def render():
    st.title("Spending Analysis")
    filters = render_sidebar_filters()

    conn = database.connect(DB_PATH)
    where_sql, params = build_where_clause(filters, table_alias="t")

    where_prefix = f"{where_sql} AND " if where_sql else "WHERE "
    query = f"""
    SELECT t.booking_date, t.merchant_normalized AS merchant,
           COALESCE(c.name, 'Uncategorized') AS category,
           COALESCE(p.name, c.name, 'Uncategorized') AS parent_category,
           COALESCE(c.kind, 'discretionary') AS category_kind,
           -t.amount_eur_minor / 100.0 AS amount_eur
    FROM transactions t
    LEFT JOIN categories c ON c.id = t.category_id
    LEFT JOIN categories p ON p.id = c.parent_id
    {where_prefix} t.amount_eur_minor < 0 AND (c.kind IS NULL OR c.kind IN ('fixed', 'discretionary'))
    """
    df = pd.read_sql_query(query, conn, params=params)

    if df.empty:
        conn.close()
        st.info("No spending transactions found for the selected filter criteria.")
        return

    total_spent = df["amount_eur"].sum()
    fixed_spent = df[df["category_kind"] == "fixed"]["amount_eur"].sum()
    disc_spent = df[df["category_kind"] == "discretionary"]["amount_eur"].sum()

    c1, c2, c3 = st.columns(3)
    with c1:
        kpi_card("Total Expenses", f"€{total_spent:,.2f}")
    with c2:
        kpi_card("Fixed Expenses", f"€{fixed_spent:,.2f}", subtext=f"{(fixed_spent/total_spent*100):.1f}% of total")
    with c3:
        kpi_card("Discretionary", f"€{disc_spent:,.2f}", subtext=f"{(disc_spent/total_spent*100):.1f}% of total")

    # Chart toggle: Sunburst vs Donut
    section_header("Expense Breakdown", "Hierarchical spending across categories and merchants")
    view_type = st.radio("Chart Type", options=["Sunburst", "Donut"], horizontal=True)

    if view_type == "Sunburst":
        st.plotly_chart(build_spending_sunburst(df), use_container_width=True)
    else:
        st.plotly_chart(build_spending_donut(df, group_col="category"), use_container_width=True)

    # Top Merchants & Subscription Leak Table
    col_left, col_right = st.columns([1, 1])

    with col_left:
        section_header("Top Merchants", "Highest total spend")
        top_merchants = df.groupby("merchant")["amount_eur"].sum().reset_index()
        top_merchants = top_merchants.sort_values(by="amount_eur", ascending=False).head(10)
        top_merchants.columns = ["Merchant", "Total Spent (€)"]
        top_merchants["Total Spent (€)"] = top_merchants["Total Spent (€)"].map(lambda x: f"€{x:,.2f}")
        st.dataframe(top_merchants, use_container_width=True, hide_index=True)

    with col_right:
        section_header("Subscription Leak Detector", "Recurring services and annual commitments")
        all_tx_rows = [dict(r) for r in conn.execute("SELECT * FROM v_transactions ORDER BY booking_date DESC").fetchall()]
        recurring = detect_recurring_charges(all_tx_rows)
        if recurring:
            rec_df = pd.DataFrame(recurring)[["merchant", "cadence", "amount_eur", "annual_cost_eur"]]
            rec_df.columns = ["Merchant", "Cadence", "Cost / Cycle", "Annual Cost (€)"]
            rec_df["Cost / Cycle"] = rec_df["Cost / Cycle"].map(lambda x: f"€{x:,.2f}")
            rec_df["Annual Cost (€)"] = rec_df["Annual Cost (€)"].map(lambda x: f"€{x:,.2f}")
            st.dataframe(rec_df, use_container_width=True, hide_index=True)
        else:
            st.caption("No subscriptions detected.")

    conn.close()
