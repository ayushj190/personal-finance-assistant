import pandas as pd
import plotly.express as px
import streamlit as st

from config import DB_PATH
from db import database
from services.portfolio import allocate_contribution, calculate_drift, full_rebalance, rebalance_without_selling
from ui.charts import build_drift_bar_chart
from ui.components import kpi_card, section_header


def render():
    st.title("Investments & Portfolio")

    conn = database.connect(DB_PATH)

    # 1. Fetch Holdings
    holdings_df = pd.read_sql_query("SELECT * FROM v_holdings", conn)

    if holdings_df.empty:
        conn.close()
        st.info("No holdings found. Sync an investment connector or add holdings in Settings.")
        return

    total_value = holdings_df["value_eur"].sum()
    total_cost = holdings_df["cost_basis"].sum()
    total_pnl = holdings_df["unrealized_pnl_eur"].sum()
    pnl_pct = (total_pnl / total_cost * 100.0) if total_cost > 0 else 0.0

    c1, c2, c3 = st.columns(3)
    with c1:
        kpi_card("Portfolio Value", f"€{total_value:,.2f}")
    with c2:
        kpi_card("Total Cost Basis", f"€{total_cost:,.2f}")
    with c3:
        kpi_card("Unrealized P&L", f"{'+' if total_pnl >= 0 else ''}€{total_pnl:,.2f}", delta_str=f"{pnl_pct:+.1f}%", is_positive=total_pnl >= 0)

    section_header("Holdings", "Securities, ETFs, and assets across accounts")
    display_df = holdings_df[["ticker", "name", "institution", "asset_type", "quantity", "cost_basis", "latest_close", "value_eur", "unrealized_pnl_eur"]].copy()
    display_df.columns = ["Ticker", "Name", "Institution", "Asset Type", "Qty", "Cost Basis (€)", "Price", "Value (€)", "P&L (€)"]
    st.dataframe(display_df, use_container_width=True, hide_index=True)

    # 2. Allocation & Drift Analysis
    section_header("Allocation & Rebalancing", "Track drift from targets and generate buy/sell recommendations")

    # Fetch allocation profiles
    profiles = conn.execute("SELECT * FROM allocation_profiles ORDER BY is_active DESC, name ASC").fetchall()
    if not profiles:
        conn.close()
        st.caption("No allocation profiles configured.")
        return

    prof_map = {p["name"]: p for p in profiles}
    selected_name = st.selectbox("Allocation Profile", options=list(prof_map.keys()), index=0)
    profile = prof_map[selected_name]

    # Fetch targets
    targets_rows = conn.execute("SELECT bucket, target_pct FROM allocation_targets WHERE profile_id = ?", (profile["id"],)).fetchall()
    targets = {r["bucket"]: r["target_pct"] for r in targets_rows}

    # Calculate actual values per bucket based on profile dimension
    dimension = profile["dimension"]  # 'asset_type', 'ticker', 'region', 'asset_class', etc.
    current_values: dict[str, float] = {}

    for _, row in holdings_df.iterrows():
        b_key = str(row.get(dimension) or "other")
        current_values[b_key] = current_values.get(b_key, 0.0) + float(row.get("value_eur", 0.0))

    if profile["include_cash"]:
        cash_val_row = conn.execute(
            "SELECT SUM(balance_eur_minor)/100.0 AS val FROM account_snapshots WHERE account_id IN (SELECT id FROM accounts WHERE asset_class = 'cash')"
        ).fetchone()
        current_values["cash"] = float(cash_val_row["val"] or 0.0)

    drift_data = calculate_drift(current_values, targets, drift_band_pct=profile["drift_band_pct"])

    col_chart, col_targets = st.columns([1, 1])
    with col_chart:
        st.plotly_chart(build_drift_bar_chart(drift_data, drift_band_pct=profile["drift_band_pct"]), use_container_width=True)

    with col_targets:
        drift_df = pd.DataFrame(drift_data)[["bucket", "actual_pct", "target_pct", "drift_pp", "alert"]]
        drift_df.columns = ["Bucket", "Actual %", "Target %", "Drift (pp)", "Action Needed"]
        drift_df["Actual %"] = drift_df["Actual %"].map(lambda x: f"{x:.1f}%")
        drift_df["Target %"] = drift_df["Target %"].map(lambda x: f"{x:.1f}%")
        drift_df["Drift (pp)"] = drift_df["Drift (pp)"].map(lambda x: f"{x:+.1f} pp")
        drift_df["Action Needed"] = drift_df["Action Needed"].map(lambda x: "⚠️ Rebalance" if x else "✅ On Target")
        st.dataframe(drift_df, use_container_width=True, hide_index=True)

    # 3. Rebalance Engine Tabs
    st.subheader("Rebalance Calculator")
    tab1, tab2, tab3 = st.tabs(["No-Sell Cash Injection", "Monthly Deposit Allocation", "Full Rebalance"])

    with tab1:
        st.markdown("Calculates minimum new capital required to restore all target weights without triggering taxable sales.")
        needed_cash, buys = rebalance_without_selling(current_values, targets)
        st.write(f"**Required New Capital:** €{needed_cash:,.2f}")
        for b, amt in buys.items():
            if amt > 0.01:
                st.write(f"- Buy **{b}**: €{amt:,.2f}")

    with tab2:
        deposit = st.number_input("Deposit Amount (€)", value=500.0, step=50.0, min_value=0.0)
        allocations = allocate_contribution(current_values, targets, deposit)
        st.markdown("**Deposit Allocation (Water-filling):**")
        for b, amt in allocations.items():
            if amt > 0.01:
                st.write(f"- Invest **€{amt:,.2f}** into **{b}** ({(amt/deposit*100):.1f}%)")

    with tab3:
        st.markdown("Rebalance to exact targets by selling overweight buckets and buying underweight buckets.")
        deltas = full_rebalance(current_values, targets)
        for b, delta in deltas.items():
            action = "BUY" if delta > 0 else "SELL"
            st.write(f"- {action} **€{abs(delta):,.2f}** of **{b}**")

    conn.close()
