import pandas as pd
import streamlit as st

from config import DB_PATH
from db import database
from ui.charts import build_cashflow_sankey, build_monthly_cashflow_bar
from ui.components import kpi_card, section_header
from ui.filters import build_where_clause, render_sidebar_filters


def render():
    st.title("Cash Flow & Runway")
    filters = render_sidebar_filters()

    conn = database.connect(DB_PATH)
    where_sql, params = build_where_clause(filters, table_alias="t")

    # 1. Sankey Data
    query = f"""
    SELECT c.kind, c.name AS category, COALESCE(p.name, c.name) AS parent_category,
           t.amount_eur_minor / 100.0 AS amount_eur
    FROM transactions t
    JOIN categories c ON c.id = t.category_id
    LEFT JOIN categories p ON p.id = c.parent_id
    {where_sql}
    """
    df = pd.read_sql_query(query, conn, params=params)

    income_nodes: list[tuple[str, float]] = []
    fixed_nodes: list[tuple[str, float]] = []
    discretionary_nodes: list[tuple[str, float]] = []
    savings_nodes: list[tuple[str, float]] = []

    if not df.empty:
        # Income items
        inc_df = df[df["kind"] == "income"]
        for cat, grp in inc_df.groupby("category"):
            val = grp["amount_eur"].sum()
            if val > 0:
                income_nodes.append((cat, val))

        # Check mortgage schedule for interest / principal split if mortgage exists
        mortgage_rows = conn.execute("SELECT * FROM v_mortgage_payments ORDER BY due_date ASC LIMIT 1").fetchone()

        # Fixed items
        fix_df = df[df["kind"] == "fixed"]
        for cat, grp in fix_df.groupby("category"):
            val = abs(grp["amount_eur"].sum())
            if cat.lower() == "mortgage" and mortgage_rows:
                # Split mortgage into interest and principal
                tot_p = mortgage_rows["payment_eur"]
                int_ratio = (mortgage_rows["interest_eur"] / tot_p) if tot_p > 0 else 0.5
                fixed_nodes.append(("Mortgage Interest", val * int_ratio))
                fixed_nodes.append(("Mortgage Principal", val * (1.0 - int_ratio)))
            else:
                if val > 0:
                    fixed_nodes.append((cat, val))

        # Discretionary items
        disc_df = df[df["kind"] == "discretionary"]
        for cat, grp in disc_df.groupby("category"):
            val = abs(grp["amount_eur"].sum())
            if val > 0:
                discretionary_nodes.append((cat, val))

        # Savings items
        sav_df = df[df["kind"] == "savings"]
        for cat, grp in sav_df.groupby("category"):
            val = abs(grp["amount_eur"].sum())
            if val > 0:
                savings_nodes.append((cat, val))

    # Top KPIs
    total_in = sum(v for _, v in income_nodes)
    total_fix = sum(v for _, v in fixed_nodes)
    total_disc = sum(v for _, v in discretionary_nodes)
    total_sav = sum(v for _, v in savings_nodes)
    net_surplus = total_in - (total_fix + total_disc + total_sav)

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        kpi_card("Total Inflow", f"€{total_in:,.2f}")
    with c2:
        kpi_card("Fixed Outflow", f"€{total_fix:,.2f}")
    with c3:
        kpi_card("Discretionary", f"€{total_disc:,.2f}")
    with c4:
        kpi_card("Net Surplus", f"€{net_surplus:,.2f}", is_positive=net_surplus >= 0)

    section_header("Cash Flow Sankey", "Flow from income sources to expenses, mortgage split, and savings")
    if income_nodes or fixed_nodes or discretionary_nodes:
        fig_sankey = build_cashflow_sankey(income_nodes, fixed_nodes, discretionary_nodes, savings_nodes)
        st.plotly_chart(fig_sankey, use_container_width=True)
    else:
        st.info("No transaction data available for the Sankey flow.")

    section_header("Monthly Cash Flow Trend", "Income vs expenses and savings over time")
    cf_df = pd.read_sql_query("SELECT * FROM v_monthly_cashflow ORDER BY month ASC", conn)
    if not cf_df.empty:
        st.plotly_chart(build_monthly_cashflow_bar(cf_df), use_container_width=True)
    else:
        st.caption("No monthly summary data yet.")

    conn.close()
