import json
import sqlite3
from typing import Optional
import pandas as pd
import plotly.express as px
import streamlit as st

import ui.pages.investments
from config import DATA_DIR, DB_PATH
from db import database
from db.repositories import AccountRepository, HoldingRepository, TransactionRepository
from services.dividend_service import calculate_dividend_projections
from services.live_quotes import cached_quotes, market_clock, refresh_live_quotes
from services.portfolio import (
    aggregate_distinct_holdings,
    build_live_rows,
    calculate_drift,
    get_smart_allocation_profiles,
)
from ui import state
from ui.charts import build_drift_bar_chart
from ui.components import format_money, kpi_card, section_header
from ui.theme import render_chart
from ui.allocation_ui import render_allocation_management
from ui.pages.investments.holdings import render_copy_portfolios
from ui.pages.investments.live import render_live_portfolio_view
from ui.pages.investments.realized_pnl import render_realized_pnl_panel


@st.fragment(run_every=60)
def _render_portfolio_fragment(
    holdings_df: pd.DataFrame,
    copy_df: pd.DataFrame,
    direct_df: pd.DataFrame,
    consolidated_df: pd.DataFrame,
    usd_to_eur: float,
    active_positions_count: int | None = None,
    conn: Optional[sqlite3.Connection] = None,
) -> None:
    # 1. Market clock & quote polling (AC-2, AC-4, AC-5)
    clock_info = market_clock(conn=conn)
    tickers = (
        [
            str(t).strip()
            for t in holdings_df["ticker"].unique()
            if str(t).strip() and not str(t).startswith("COPY:") and not str(t).startswith("ID_")
        ]
        if not holdings_df.empty and "ticker" in holdings_df.columns
        else []
    )

    if clock_info["is_open"]:
        s_cache = state.get(state.K.LIVE_QUOTE_CACHE, {})
        updated_cache = refresh_live_quotes(tickers, session_cache=s_cache)
        state.set(state.K.LIVE_QUOTE_CACHE, updated_cache)
        quote_cache = updated_cache
    else:
        quote_cache = cached_quotes(conn=conn)

    # 2. Historical close series for sparklines (AC-1)
    series_map = {}
    if conn and tickers:
        try:
            series_map = HoldingRepository.get_ticker_close_series(conn, tickers, days=30)
        except Exception:
            series_map = {}

    # 3. Mirror cache
    mirror_cache = []
    cache_path = DATA_DIR / "etoro_mirrors_cache.json"
    if cache_path.exists():
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                mirror_cache = json.load(f)
        except Exception:
            mirror_cache = []

    # 4. Aggregated direct holdings
    agg_holdings, _ = aggregate_distinct_holdings(holdings_df)

    # 5. Build unified live rows (AC-1, AC-3, AC-5)
    live_rows = build_live_rows(
        holdings_df,
        agg_holdings,
        mirror_cache=mirror_cache,
        quote_cache=quote_cache,
        fx_rate=usd_to_eur,
        close_series=series_map,
    )

    # 6. Render live portfolio view (AC-1, AC-6, AC-7, AC-8, AC-9, AC-11, AC-12, AC-13)
    render_live_portfolio_view(live_rows, clock_info, consolidated_df, conn=conn)

    # 6b. Copy Trader constituent breakdowns
    if not copy_df.empty:
        with st.expander("👥 Copy Trader Breakdowns", expanded=False):
            render_copy_portfolios(copy_df, usd_to_eur)

    # 7. Realized P&L Panel
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
                    with st.expander("Dividend-generating holdings", expanded=False):
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
