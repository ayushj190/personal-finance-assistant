import sqlite3
from typing import Optional
import pandas as pd
import plotly.express as px
import streamlit as st

import ui.pages.investments
from config import DB_PATH
from db import database
from db.repositories import AccountRepository, HoldingRepository, TransactionRepository
from services.dividend_service import calculate_dividend_projections
from services.portfolio import calculate_drift, get_smart_allocation_profiles
from ui.charts import build_drift_bar_chart
from ui.components import format_money, kpi_card, section_header
from ui.theme import render_chart
from ui.allocation_ui import render_allocation_management
from ui.pages.investments.holdings import render_copy_portfolios, render_holdings_table
from ui.pages.investments.exposure import render_exposure_visualizer
from ui.pages.investments.watchlist import render_live_quotes_and_watchlist
from ui.pages.investments.realized_pnl import render_realized_pnl_panel


@st.fragment
def _render_portfolio_fragment(
    holdings_df: pd.DataFrame,
    copy_df: pd.DataFrame,
    direct_df: pd.DataFrame,
    consolidated_df: pd.DataFrame,
    usd_to_eur: float,
    active_positions_count: int | None = None,
    conn: Optional[sqlite3.Connection] = None,
) -> None:
    # 1. 4-KPI ribbon
    total_value = float(holdings_df["value_eur"].sum())
    total_cost = float(holdings_df["cost_basis"].sum())
    total_pnl = float(holdings_df["unrealized_pnl_eur"].sum())
    pnl_pct = (total_pnl / total_cost * 100.0) if total_cost > 0 else 0.0
    unquoted_count = int((holdings_df["latest_close"] <= 0).sum()) if "latest_close" in holdings_df.columns else 0

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        ui.pages.investments.kpi_card("Portfolio Value", format_money(total_value))
    with c2:
        ui.pages.investments.kpi_card("Total Cost Basis", format_money(total_cost))
    with c3:
        pnl_str = f"{'+' if total_pnl >= 0 else ''}{format_money(total_pnl)}"
        ui.pages.investments.kpi_card("Unrealized P&L", pnl_str, delta_str=f"{pnl_pct:+.1f}%")
    with c4:
        sub = (
            f"⏱️ {unquoted_count} quote delayed"
            if unquoted_count > 0
            else "All quotes live"
        )
        if active_positions_count is None:
            if not consolidated_df.empty and "ticker" in consolidated_df.columns:
                active_positions_count = consolidated_df["ticker"].nunique()
            else:
                active_positions_count = len(holdings_df)
        pos_str = f"{active_positions_count} assets"
        ui.pages.investments.kpi_card("Active Positions", pos_str, subtext=sub)

    # 2. Multi-dimension Exposure Visualizer
    render_exposure_visualizer(consolidated_df)

    # 3. Active Holdings Table
    with section_header("Portfolio Holdings"):
        render_holdings_table(holdings_df)

    # 4. Copy Portfolios Section
    if not copy_df.empty:
        with section_header("eToro Copied Traders"):
            render_copy_portfolios(copy_df, usd_to_eur)

    # 5. Live Quotes & Watchlist
    render_live_quotes_and_watchlist(direct_df, consolidated_df)

    # 6. Realized P&L Panel
    render_realized_pnl_panel(conn)


@st.fragment
def _render_allocation_fragment(conn, consolidated_df: pd.DataFrame) -> None:
    alloc_conn = conn
    should_close_alloc = False
    if not database.is_conn_open(alloc_conn):
        try:
            alloc_conn = database.connect(DB_PATH)
            should_close_alloc = True
        except Exception:
            alloc_conn = None

    if alloc_conn is None:
        return

    try:
        profiles = get_smart_allocation_profiles(alloc_conn, consolidated_df)
        if not profiles:
            st.info("No allocation profiles configured.")
            return

        prof_map = {p["name"]: p for p in profiles}
        col_prof, col_desc = st.columns([1, 1], vertical_alignment="center")
        with col_prof:
            selected_name = st.selectbox(
                "Target Allocation Strategy",
                options=list(prof_map.keys()),
                index=0,
                key="investments_allocation_profile_select",
            )
        profile = prof_map[selected_name]
        with col_desc:
            desc = profile.get("description", "")
            dim_lbl = profile.get("dimension", "").title()
            st.caption(f"**Strategy Focus:** {desc} • Dimension: `{dim_lbl}`")

        targets = profile.get("targets", {})
        if not targets and "id" in profile:
            targets = HoldingRepository.get_allocation_targets(alloc_conn, profile["id"])

        dimension = profile.get("dimension", "asset_type")
        current_values: dict[str, float] = {}

        if not consolidated_df.empty:
            col_to_check = dimension if dimension in consolidated_df.columns else "asset_type"
            for _, row in consolidated_df.iterrows():
                b_key = str(row.get(col_to_check) or "other")
                current_values[b_key] = current_values.get(b_key, 0.0) + float(row.get("value_eur", 0.0))

        if profile.get("include_cash"):
            current_values["cash"] = AccountRepository.get_total_cash_balance(alloc_conn)

        if not current_values:
            st.warning("No value to balance for this profile.")
            return

        drift_data = calculate_drift(current_values, targets, drift_band_pct=profile["drift_band_pct"])

        col_chart, col_targets = st.columns([1, 1])
        with col_chart:
            with st.container(border=True):
                st.markdown("##### ⚖️ Target vs Actual Drift")
                render_chart(
                    build_drift_bar_chart(drift_data, drift_band_pct=profile["drift_band_pct"]),
                    width="stretch",
                )

        with col_targets:
            drift_df = pd.DataFrame(drift_data)[["bucket", "actual_pct", "target_pct", "drift_pp", "alert"]]
            drift_df.columns = ["Bucket", "Actual %", "Target %", "Drift (pp)", "Action Needed"]
            if ui.pages.investments.is_hidden():
                drift_df["Actual %"] = "****%"
                drift_df["Target %"] = "****%"
                drift_df["Drift (pp)"] = "**** pp"
            else:
                drift_df["Actual %"] = drift_df["Actual %"].map(lambda x: f"{x:.1f}%")
                drift_df["Target %"] = drift_df["Target %"].map(lambda x: f"{x:.1f}%")
                drift_df["Drift (pp)"] = drift_df["Drift (pp)"].map(lambda x: f"{x:+.1f} pp")
            drift_df["Action Needed"] = drift_df["Action Needed"].map(lambda x: "⚠️ Rebalance" if x else "✅ On Target")
            st.dataframe(drift_df, width="stretch", hide_index=True)

        st.divider()
        render_allocation_management(alloc_conn)
    finally:
        if should_close_alloc:
            alloc_conn.close()


@st.fragment
def _render_income_fragment(conn, holdings_df: pd.DataFrame) -> None:
    inc_conn = conn
    should_close_inc = False
    if not database.is_conn_open(inc_conn):
        try:
            inc_conn = database.connect(DB_PATH)
            should_close_inc = True
        except Exception:
            inc_conn = None

    if inc_conn is None:
        return

    try:
        with section_header("Dividend & Passive Income Forecast"):
            div_data = calculate_dividend_projections(inc_conn)

        d1, d2, d3 = st.columns(3)
        with d1:
            ann_str = "€****" if ui.pages.investments.is_hidden() else f"€{div_data['projected_annual_dividends_eur']:,.2f}"
            ui.pages.investments.kpi_card("Projected Annual Income", ann_str, subtext="Estimated forward dividends")
        with d2:
            yield_str = "****" if ui.pages.investments.is_hidden() else f"{div_data['average_dividend_yield_pct']:.2f}%"
            ui.pages.investments.kpi_card("Portfolio Yield", yield_str, subtext="Weighted average forward yield")
        with d3:
            mo_str = "€****" if ui.pages.investments.is_hidden() else f"€{div_data['monthly_average_eur']:,.2f}"
            ui.pages.investments.kpi_card("Monthly Average", mo_str, subtext="Projected passive monthly flow")

        if div_data["monthly_distribution"]:
            m_dist_df = pd.DataFrame(div_data["monthly_distribution"])
            col_m_chart, col_m_table = st.columns([1, 1])

            with col_m_chart:
                dist_fig = px.bar(
                    m_dist_df,
                    x="month",
                    y="payout_eur",
                    title="Projected Monthly Dividend Calendar (€)",
                    text=m_dist_df["payout_eur"].map(lambda x: "€****" if ui.pages.investments.is_hidden() else f"€{x:,.0f}"),
                    color_discrete_sequence=["#2DD4BF"],
                )
                dist_fig.update_layout(
                    margin=dict(t=35, l=55, r=20, b=25),
                    xaxis=dict(title="Month", automargin=True),
                    yaxis=dict(title="Projected Payout (€)", tickprefix="€", automargin=True),
                )
                if ui.pages.investments.is_hidden():
                    dist_fig.update_traces(hovertemplate="Censored<extra></extra>")
                with st.container(border=True):
                    render_chart(dist_fig, width="stretch")

            with col_m_table:
                h_df = div_data["holdings_df"]
                if not h_df.empty:
                    disp_h = h_df[["ticker", "name", "value_eur", "yield_pct", "annual_dividend_eur"]].copy()
                    disp_h.columns = ["Ticker", "Asset", "Value (€)", "Est. Yield", "Annual Div (€)"]
                    if ui.pages.investments.is_hidden():
                        disp_h["Value (€)"] = "€****"
                        disp_h["Est. Yield"] = "****%"
                        disp_h["Annual Div (€)"] = "€****"
                        disp_h["Asset"] = "****"
                        disp_h["Ticker"] = "****"
                    else:
                        disp_h["Value (€)"] = disp_h["Value (€)"].map(lambda x: f"€{x:,.2f}")
                        disp_h["Est. Yield"] = disp_h["Est. Yield"].map(lambda x: f"{x:.1f}%")
                        disp_h["Annual Div (€)"] = disp_h["Annual Div (€)"].map(lambda x: f"€{x:,.2f}")
                    st.dataframe(disp_h, width="stretch", hide_index=True)
                else:
                    st.caption("No dividend-generating assets tracked.")

            with section_header("Tax-Loss Harvesting Assistant"):
                loss_df = holdings_df[holdings_df["unrealized_pnl_eur"] < -50].sort_values(by="unrealized_pnl_eur")
                if not loss_df.empty:
                    disp_loss = loss_df[["ticker", "name", "value_eur", "unrealized_pnl_eur"]].copy()
                    disp_loss.columns = ["Ticker", "Asset", "Value (€)", "Unrealized P&L (€)"]
                    if ui.pages.investments.is_hidden():
                        disp_loss["Value (€)"] = "€****"
                        disp_loss["Unrealized P&L (€)"] = "€****"
                        disp_loss["Asset"] = "****"
                        disp_loss["Ticker"] = "****"
                    else:
                        disp_loss["Value (€)"] = disp_loss["Value (€)"].map(lambda x: f"€{x:,.2f}")
                        disp_loss["Unrealized P&L (€)"] = disp_loss["Unrealized P&L (€)"].map(lambda x: f"€{x:,.2f}")
                    st.dataframe(disp_loss, hide_index=True, width="stretch")
                else:
                    st.caption("No significant unrealized losses available for harvesting.")
    finally:
        if should_close_inc:
            inc_conn.close()


@st.fragment
def _render_goals_fragment(conn) -> None:
    goals_conn = conn
    should_close_goals = False
    if not database.is_conn_open(goals_conn):
        try:
            goals_conn = database.connect(DB_PATH)
            should_close_goals = True
        except Exception:
            goals_conn = None

    if goals_conn is None:
        return

    try:
        c_fire, c_goals = st.columns([1, 1])

        with c_fire:
            st.subheader("🔥 FIRE Trajectory")
            m_exp = TransactionRepository.get_average_monthly_expenses(goals_conn)
            annual_exp = abs(m_exp) * 12
            fi_number = annual_exp * 25

            m_sav = TransactionRepository.get_average_monthly_savings(goals_conn)
            curr_nw = AccountRepository.get_latest_net_worth_snapshot(goals_conn)

            c_sl1, c_sl2 = st.columns(2)
            with c_sl1:
                ret_rate = st.slider("Expected Annual Return (%)", 1.0, 15.0, 7.0, 0.5, key="fire_return_slider")
            with c_sl2:
                inf_rate = st.slider("Expected Inflation (%)", 0.0, 10.0, 2.0, 0.5, key="fire_inflation_slider")
            real_return = (ret_rate - inf_rate) / 100.0

            if ui.pages.investments.is_hidden():
                st.metric("FI Number (25x)", "€****")
            else:
                st.metric("FI Number (25x)", f"€{fi_number:,.2f}")

            years = list(range(31))
            proj = []
            val = curr_nw
            for _ in years:
                proj.append(val)
                val = val * (1 + real_return) + (m_sav * 12)

            fig_fire = px.line(x=years, y=proj, title="Net Worth Projection (Real)")
            fig_fire.add_hline(y=fi_number, line_dash="dash", annotation_text="FI Target", line_color="#2DD4BF")
            fig_fire.update_layout(
                xaxis=dict(title="Years from Now", automargin=True),
                yaxis=dict(title="Net Worth (€)", tickprefix="€", tickformat="~s", automargin=True),
                margin=dict(t=35, l=55, r=20, b=25),
            )
            if ui.pages.investments.is_hidden():
                fig_fire.update_traces(hovertemplate="Censored<extra></extra>")
            with st.container(border=True):
                render_chart(fig_fire, width="stretch")

        with c_goals:
            st.subheader("🎯 Savings Goals")

            with st.expander("➕ Add New Goal", expanded=False):
                with st.form("new_goal_form_investments"):
                    g_name = st.text_input("Goal Name")
                    g_target = st.number_input("Target Amount (€)", min_value=1.0, step=100.0)
                    cash_accounts = AccountRepository.get_cash_accounts(goals_conn)
                    acc_options = {a.id: a.name for a in cash_accounts}
                    g_acc = st.selectbox("Linked Account", options=list(acc_options.keys()), format_func=lambda x: acc_options[x])

                    if st.form_submit_button("Save Goal"):
                        TransactionRepository.add_goal(goals_conn, g_name, g_target, g_acc)
                        st.success("Goal added!")
                        st.rerun(scope="app")

            goals = TransactionRepository.get_goals(goals_conn)
            if not goals:
                st.caption("No financial goals tracked yet.")
            for g in goals:
                tar = float(g["target_amount"])
                bal = float(g["current_balance"] or 0)
                pct = min(1.0, max(0.0, bal / tar)) if tar > 0 else 0
                if ui.pages.investments.is_hidden():
                    st.write(f"**{g['name']}** — █% (in ****)")
                    st.progress(pct)
                else:
                    st.write(f"**{g['name']}** — €{bal:,.0f} / €{tar:,.0f} ({pct*100:.1f}%) in {g['account_name'] or 'None'}")
                    st.progress(pct)
    finally:
        if should_close_goals:
            goals_conn.close()
