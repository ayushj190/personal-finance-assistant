import pandas as pd
import streamlit as st

from config import DB_PATH
from db import database
from services.portfolio import allocate_contribution, calculate_drift, full_rebalance, rebalance_without_selling
from ui.charts import build_drift_bar_chart
from ui.components import format_money, is_hidden, kpi_card, section_header


def render():
    st.title("Investments & Portfolio")

    conn = database.connect(DB_PATH)

    # 1. Fetch Holdings
    holdings_df = pd.read_sql_query("SELECT * FROM v_holdings", conn)

    if holdings_df.empty:
        conn.close()
        st.info(
            "No holdings found. Sync an investment connector or add holdings in Settings.")
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
        kpi_card("Unrealized P&L",
                 f"{'+' if total_pnl >= 0 else ''}€{total_pnl:,.2f}", delta_str=f"{pnl_pct:+.1f}%")

    # Split into direct holdings and copy portfolios
    copy_mask = holdings_df["ticker"].str.startswith("COPY:", na=False)
    copy_df = holdings_df[copy_mask].copy()
    direct_df = holdings_df[~copy_mask].copy()

    # FX rate for USD display
    fx_row = conn.execute(
        "SELECT close FROM market_quotes WHERE ticker = 'EURUSD=X' ORDER BY quote_date DESC LIMIT 1").fetchone()
    usd_to_eur = (1.0 / float(fx_row["close"])
                  ) if fx_row and fx_row["close"] else 0.892

    # 1. Copy Portfolios Section
    if not copy_df.empty:
        section_header("eToro Copied Traders",
                       "CopyPortfolios and automated trader mirroring")

        # Try loading mirror positions cache
        from pathlib import Path
        import json
        cache_path = Path(__file__).resolve(
        ).parent.parent.parent / "data" / "etoro_mirrors_cache.json"
        mirrors_map = {}
        if cache_path.exists():
            try:
                with open(cache_path, "r", encoding="utf-8") as f:
                    mirrors_data = json.load(f)
                    mirrors_map = {m["ticker"]: m for m in mirrors_data}
            except Exception:
                pass

        for _, row in copy_df.iterrows():
            ticker = row["ticker"]
            username = ticker.replace("COPY:", "")
            mirror_info = mirrors_map.get(ticker, {})

            invested_usd = mirror_info.get(
                "invested_usd", float(row["cost_basis"]))
            val_usd = mirror_info.get(
                "value_usd", float(row["value_eur"]) / usd_to_eur)
            pnl_usd = mirror_info.get(
                "unrealized_pnl_usd", val_usd - invested_usd)
            ret_pct = (pnl_usd / invested_usd *
                       100.0) if invested_usd > 0 else 0.0

            invested_eur = invested_usd * usd_to_eur
            val_eur = val_usd * usd_to_eur
            pnl_eur = pnl_usd * usd_to_eur

            pnl_color = "normal" if pnl_eur >= 0 else "off"
            pnl_sign = "+" if pnl_eur >= 0 else ""

            with st.container(border=True):
                col_u1, col_u2, col_u3, col_u4, col_u5 = st.columns(
                    [2, 2, 2, 2, 2])
                with col_u1:
                    st.markdown(f"### 👤 {username}")
                    st.caption(
                        f"{mirror_info.get('positions_count', 'N/A')} open positions")
                with col_u2:
                    st.metric("Invested", format_money(invested_eur,
                              "€"), format_money(invested_usd, "$"))
                with col_u3:
                    st.metric("Current Value", format_money(
                        val_eur, "€"), format_money(val_usd, "$"))
                with col_u4:
                    pnl_eur_str = f"{pnl_sign}{format_money(abs(pnl_eur), '€')}" if not is_hidden(
                    ) else "€****"
                    pnl_usd_str = f"{pnl_sign}{format_money(abs(pnl_usd), '$')}" if not is_hidden(
                    ) else "$****"
                    st.metric("Unrealized P&L", pnl_eur_str,
                              pnl_usd_str, delta_color=pnl_color)
                with col_u5:
                    st.metric(
                        "Total Return", f"{pnl_sign}{ret_pct:.2f}%", delta_color=pnl_color)

                # Underlying positions expander
                underlying = mirror_info.get("positions", [])
                if underlying:
                    with st.expander(f"View {username}'s Top Holdings ({len(underlying)} positions)"):
                        pos_rows = []
                        for p in underlying:
                            p_amt = p.get("amount_usd", 0.0)
                            p_pnl = p.get("pnl_usd", 0.0)
                            p_ret = (p_pnl / p_amt *
                                     100.0) if p_amt > 0 else 0.0
                            pos_rows.append({
                                "Symbol": p.get("symbol") or f"ID_{p.get('instrument_id')}",
                                "Name": p.get("name") or "-",
                                "Amount ($)": format_money(p_amt, "$"),
                                "Amount (€)": format_money(p_amt * usd_to_eur, "€"),
                                "P&L ($)": (f"{'+' if p_pnl >= 0 else ''}{format_money(abs(pnl_usd), '$')}") if not is_hidden() else "$****",
                                "Return": f"{'+' if p_ret >= 0 else ''}{p_ret:.1f}%",
                            })
                        st.dataframe(
                            pd.DataFrame(pos_rows),
                            use_container_width=True,
                            hide_index=True,
                            column_config={"Name": st.column_config.TextColumn(
                                "Name", width="medium")}
                        )

    # 2. Direct Holdings Section
    section_header("Direct Holdings", "Stocks, ETFs, and assets held directly")
    if not direct_df.empty:
        display_df = direct_df[["ticker", "name", "institution", "asset_type", "quantity",
                                "cost_basis", "latest_close", "value_eur", "unrealized_pnl_eur"]].copy()
        display_df.columns = ["Ticker", "Name", "Institution", "Asset Type",
                              "Qty", "Cost Basis (€)", "Price", "Value (€)", "P&L (€)"]
        if is_hidden():
            for c in ["Cost Basis (€)", "Price", "Value (€)", "P&L (€)"]:
                display_df[c] = "€****"
            st.dataframe(display_df, use_container_width=True, hide_index=True)
        else:
            num_cfg = st.column_config.NumberColumn(
                "Amount", format="€%.2f", disabled=True)
            st.dataframe(
                display_df,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Name": st.column_config.TextColumn("Name", width="medium"),
                    "Institution": st.column_config.TextColumn("Institution", width="medium"),
                    "Cost Basis (€)": num_cfg,
                    "Price": num_cfg,
                    "Value (€)": num_cfg,
                    "P&L (€)": num_cfg,
                }
            )
    else:
        st.caption("No direct holdings found.")

    # 2. Allocation & Drift Analysis
    section_header("Allocation & Rebalancing",
                   "Track drift from targets and generate buy/sell recommendations")

    # Fetch allocation profiles
    profiles = conn.execute(
        "SELECT * FROM allocation_profiles ORDER BY is_active DESC, name ASC").fetchall()
    if not profiles:
        conn.close()
        st.caption("No allocation profiles configured.")
        return

    prof_map = {p["name"]: p for p in profiles}
    selected_name = st.selectbox(
        "Allocation Profile", options=list(prof_map.keys()), index=0)
    profile = prof_map[selected_name]

    # Fetch targets
    targets_rows = conn.execute(
        "SELECT bucket, target_pct FROM allocation_targets WHERE profile_id = ?", (profile["id"],)).fetchall()
    targets = {r["bucket"]: r["target_pct"] for r in targets_rows}

    # Calculate actual values per bucket based on profile dimension
    # 'asset_type', 'ticker', 'region', 'asset_class', etc.
    dimension = profile["dimension"]
    current_values: dict[str, float] = {}

    for _, row in holdings_df.iterrows():
        b_key = str(row.get(dimension) or "other")
        current_values[b_key] = current_values.get(
            b_key, 0.0) + float(row.get("value_eur", 0.0))

    if profile["include_cash"]:
        cash_val_row = conn.execute(
            "SELECT SUM(balance_eur_minor)/100.0 AS val FROM account_snapshots WHERE account_id IN (SELECT id FROM accounts WHERE asset_class = 'cash')"
        ).fetchone()
        current_values["cash"] = float(cash_val_row["val"] or 0.0)

    drift_data = calculate_drift(
        current_values, targets, drift_band_pct=profile["drift_band_pct"])

    col_chart, col_targets = st.columns([1, 1])
    with col_chart:
        st.plotly_chart(build_drift_bar_chart(
            drift_data, drift_band_pct=profile["drift_band_pct"]), use_container_width=True, theme=None)

    with col_targets:
        drift_df = pd.DataFrame(drift_data)[
            ["bucket", "actual_pct", "target_pct", "drift_pp", "alert"]]
        drift_df.columns = ["Bucket", "Actual %",
                            "Target %", "Drift (pp)", "Action Needed"]
        drift_df["Actual %"] = drift_df["Actual %"].map(lambda x: f"{x:.1f}%")
        drift_df["Target %"] = drift_df["Target %"].map(lambda x: f"{x:.1f}%")
        drift_df["Drift (pp)"] = drift_df["Drift (pp)"].map(
            lambda x: f"{x:+.1f} pp")
        drift_df["Action Needed"] = drift_df["Action Needed"].map(
            lambda x: "⚠️ Rebalance" if x else "✅ On Target")
        st.dataframe(drift_df, use_container_width=True, hide_index=True)

    # 3. Rebalance Engine Tabs
    st.subheader("Rebalance Calculator")
    tab1, tab2, tab3 = st.tabs(
        ["No-Sell Cash Injection", "Monthly Deposit Allocation", "Full Rebalance"])

    with tab1:
        st.markdown(
            "Calculates minimum new capital required to restore all target weights without triggering taxable sales.")
        needed_cash, buys = rebalance_without_selling(current_values, targets)
        st.write(f"**Required New Capital:** €{needed_cash:,.2f}")
        for b, amt in buys.items():
            if amt > 0.01:
                st.write(f"- Buy **{b}**: €{amt:,.2f}")

    with tab2:
        deposit = st.number_input(
            "Deposit Amount (€)", value=500.0, step=50.0, min_value=0.0)
        allocations = allocate_contribution(current_values, targets, deposit)
        st.markdown("**Deposit Allocation (Water-filling):**")
        for b, amt in allocations.items():
            if amt > 0.01:
                st.write(
                    f"- Invest **€{amt:,.2f}** into **{b}** ({(amt/deposit*100):.1f}%)")

    with tab3:
        st.markdown(
            "Rebalance to exact targets by selling overweight buckets and buying underweight buckets.")
        deltas = full_rebalance(current_values, targets)
        for b, delta in deltas.items():
            action = "BUY" if delta > 0 else "SELL"
            st.write(f"- {action} **€{abs(delta):,.2f}** of **{b}**")

    conn.close()
