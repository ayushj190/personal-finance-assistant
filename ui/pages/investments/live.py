"""Live portfolio table, movers strip, and portfolio analytics views.

Implements AC-1 to AC-14:
- 5-KPI ribbon with Day P&L and Quote Status.
- Generated offline ticker chip movers strip.
- Live positions table with sorting, search, sparklines, and numeric-safe masking.
- Equity curve from portfolio_snapshots.
- Ranked P&L contribution and sector performance heat.
"""

from __future__ import annotations

import html
import sqlite3
from typing import Any
import pandas as pd
import streamlit as st

from db.repositories import HoldingRepository
from ui import state
from ui.charts import (
    build_equity_curve,
    build_investments_market_carpet,
    build_pnl_contribution_chart,
    build_sector_performance_heat,
)
from ui.components import format_money, is_hidden, kpi_card, section_header
from ui.page_panel import scroll_selector_into_view
from ui.theme import render_chart

SORT_COLUMNS = (
    "value_eur",
    "day_change_pct",
    "day_pnl_eur",
    "unrealized_pnl_eur",
    "total_pnl_pct",
    "quantity",
    "price",
    "cost_basis",
    "name",
    "ticker",
)

MOVERS = ("gainers", "losers", "all")


def render_kpi_ribbon(
    live_rows: pd.DataFrame,
    total_val: float,
    total_cost: float,
    total_pnl: float,
    quote_state: dict[str, Any],
) -> None:
    """Render the 5-card KPI ribbon (AC-7)."""
    pnl_pct = (total_pnl / total_cost * 100.0) if total_cost > 0 else 0.0

    # Day P&L sum across priced rows (AC-3)
    priced_mask = live_rows["is_priced"] if "is_priced" in live_rows.columns else pd.Series([True] * len(live_rows))
    priced_rows = live_rows[priced_mask]
    total_day_pnl = float(priced_rows["day_pnl_eur"].sum() or 0.0) if not priced_rows.empty else 0.0

    prev_close_val = total_val - total_day_pnl
    day_pnl_pct = (total_day_pnl / prev_close_val * 100.0) if prev_close_val > 0 else 0.0

    # Quote status card logic (AC-4, AC-5)
    session_st = quote_state.get("session_state", "open")
    last_date = quote_state.get("last_price_date", "")
    poll_failed = quote_state.get("last_poll_failed", False)

    unpriced_mask = (~live_rows["is_priced"] & ~live_rows["is_mirror_valued"]) if "is_mirror_valued" in live_rows.columns else ~live_rows["is_priced"]
    unpriced_count = int(unpriced_mask.sum()) if not live_rows.empty else 0

    if session_st == "closed":
        status_title = f"Closed ({last_date})"
        status_sub = "Frozen at last close"
    elif poll_failed:
        status_title = "Delayed"
        status_sub = f"{unpriced_count} unpriced" if unpriced_count > 0 else "Using cached quotes"
    else:
        status_title = "Live"
        status_sub = f"{unpriced_count} unpriced" if unpriced_count > 0 else "All quotes fresh"

    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        kpi_card("Portfolio Value", format_money(total_val))
    with c2:
        kpi_card("Total Cost Basis", format_money(total_cost))
    with c3:
        pnl_str = f"{'+' if total_pnl >= 0 else ''}{format_money(total_pnl)}"
        kpi_card("Unrealized P&L", pnl_str, delta_str=f"{pnl_pct:+.1f}%")
    with c4:
        day_str = f"{'+' if total_day_pnl >= 0 else ''}{format_money(total_day_pnl)}"
        day_sub = f"{'+' if day_pnl_pct >= 0 else ''}{day_pnl_pct:+.2f}% vs prev close"
        kpi_card("Day P&L", day_str, delta_str=day_sub)
    with c5:
        kpi_card("Quote Status", status_title, subtext=status_sub)


def render_movers_strip(live_rows: pd.DataFrame) -> None:
    """Render top 3 gainers and top 3 losers as generated offline chips (AC-8)."""
    if live_rows.empty or "day_change_pct" not in live_rows.columns:
        return

    priced = live_rows[live_rows["is_priced"] & (live_rows["day_change_pct"].notna())].copy()
    if priced.empty:
        return

    gainers = (
        priced[priced["day_change_pct"] > 0]
        .sort_values(by=["day_change_pct", "value_eur"], ascending=[False, False])
        .head(3)
    )
    losers = (
        priced[priced["day_change_pct"] < 0]
        .sort_values(by=["day_change_pct", "value_eur"], ascending=[True, False])
        .head(3)
    )

    if gainers.empty and losers.empty:
        return

    chips_html = []
    for _, r in gainers.iterrows():
        tick = html.escape(str(r["ticker"]))
        pct = float(r["day_change_pct"])
        chips_html.append(
            f"<span style='background: rgba(16, 185, 129, 0.15); color: #10b981; border: 1px solid rgba(16, 185, 129, 0.3); padding: 2px 8px; border-radius: 12px; font-size: 0.75rem; font-weight: 600; font-family: monospace;'>"
            f"▲ {tick} +{pct:.2f}%</span>"
        )
    for _, r in losers.iterrows():
        tick = html.escape(str(r["ticker"]))
        pct = float(r["day_change_pct"])
        chips_html.append(
            f"<span style='background: rgba(239, 68, 68, 0.15); color: #ef4444; border: 1px solid rgba(239, 68, 68, 0.3); padding: 2px 8px; border-radius: 12px; font-size: 0.75rem; font-weight: 600; font-family: monospace;'>"
            f"▼ {tick} {pct:.2f}%</span>"
        )

    st.html(
        "<div style='display: flex; gap: 8px; flex-wrap: wrap; align-items: center; margin-top: 4px; margin-bottom: 12px;'>"
        "<span style='font-size: 0.8rem; font-weight: 600; color: #94a3b8;'>Movers:</span>"
        f"{''.join(chips_html)}"
        "</div>"
    )


def render_live_table(live_rows: pd.DataFrame) -> None:
    """Render the fixed-height scrollable live portfolio table (AC-1, AC-12, AC-13, AC-14)."""
    if live_rows.empty:
        st.info("No investment positions available.")
        return

    # Check for Copilot pending view parameters (AC-17)
    copilot_sort = state.pop(state.K.INVESTMENTS_SORT_COL, None)
    copilot_movers = state.pop(state.K.INVESTMENTS_MOVERS, None)
    copilot_search = state.pop(state.K.INVESTMENTS_SEARCH, None)

    # Search & Mover filters
    col_search, col_filter, col_dim_info = st.columns([2, 1.5, 2], vertical_alignment="center")
    with col_search:
        search_query = st.text_input(
            "Search",
            value=copilot_search or "",
            placeholder="Search symbol or name...",
            label_visibility="collapsed",
            key="live_table_search_input",
        )

    with col_filter:
        mover_filter = st.selectbox(
            "Filter Movers",
            options=["All", "Gainers", "Losers"],
            index=1 if copilot_movers == "gainers" else (2 if copilot_movers == "losers" else 0),
            label_visibility="collapsed",
            key="live_table_mover_select",
        )

    df_disp = live_rows.copy()

    # 1. Filter by search query
    if search_query and str(search_query).strip():
        q = str(search_query).strip().lower()
        mask = (
            df_disp["ticker"].astype(str).str.lower().str.contains(q)
            | df_disp["name"].astype(str).str.lower().str.contains(q)
        )
        df_disp = df_disp[mask]

    # 2. Filter by mover
    if mover_filter == "Gainers":
        df_disp = df_disp[df_disp["day_change_pct"] > 0]
    elif mover_filter == "Losers":
        df_disp = df_disp[df_disp["day_change_pct"] < 0]

    # 3. Sort
    sort_col = copilot_sort if copilot_sort in df_disp.columns else "value_eur"
    ascending = False if sort_col in ("value_eur", "day_pnl_eur", "day_change_pct", "unrealized_pnl_eur", "total_pnl_pct", "weight_pct") else True
    df_disp = df_disp.sort_values(by=sort_col, ascending=ascending)

    # 4. Column configuration with render-time masking (AC-12, AC-13, AC-14)
    hidden = is_hidden()
    money_fmt = "€****" if hidden else "€%.2f"
    pnl_fmt = "€****" if hidden else "%+,.2f"

    column_config = {
        "name_with_ticker": st.column_config.TextColumn("Asset", width="medium"),
        "is_copy": st.column_config.CheckboxColumn("Copy", width="small", help="Copied trader position"),
        "quantity": st.column_config.NumberColumn("Quantity", format="%.4f", width="small"),
        "avg_open_price": st.column_config.NumberColumn("Avg Open", format=money_fmt, width="small"),
        "price": st.column_config.NumberColumn("Price", format="€%.2f", width="small"),
        "day_change_pct": st.column_config.NumberColumn("Day %", format="%+.2f%%", width="small"),
        "day_pnl_eur": st.column_config.NumberColumn("Day P&L", format=pnl_fmt, width="small"),
        "cost_basis": st.column_config.NumberColumn("Cost Basis", format=money_fmt, width="small"),
        "value_eur": st.column_config.NumberColumn("Market Value", format=money_fmt, width="small"),
        "unrealized_pnl_eur": st.column_config.NumberColumn("Total P&L", format=pnl_fmt, width="small"),
        "total_pnl_pct": st.column_config.NumberColumn("Total %", format="%+.2f%%", width="small"),
        "weight_pct": st.column_config.NumberColumn("Weight", format="%.1f%%", width="small"),
        "sparkline": st.column_config.LineChartColumn("Trend (1M)", width="small"),
    }

    display_cols = [
        "name_with_ticker",
        "is_copy",
        "quantity",
        "avg_open_price",
        "price",
        "day_change_pct",
        "day_pnl_eur",
        "cost_basis",
        "value_eur",
        "unrealized_pnl_eur",
        "total_pnl_pct",
        "weight_pct",
        "sparkline",
    ]

    with st.container(key="investments_live_table_panel"):
        st.dataframe(
            df_disp[display_cols],
            column_config=column_config,
            hide_index=True,
            height=420,
            use_container_width=True,
        )

    # If Copilot scrolled here, trigger scroll helper (AC-17)
    if copilot_sort or copilot_movers or copilot_search:
        scroll_selector_into_view("investments_live_table_panel")


def render_live_portfolio_view(
    live_rows: pd.DataFrame,
    quote_state: dict[str, Any],
    consolidated_df: pd.DataFrame,
    conn: sqlite3.Connection | None = None,
) -> None:
    """Primary render function for the updated Portfolio tab."""
    total_val = float(live_rows["value_eur"].sum() or 0.0) if not live_rows.empty else 0.0
    total_cost = float(live_rows["cost_basis"].sum() or 0.0) if not live_rows.empty else 0.0
    total_pnl = float(live_rows["unrealized_pnl_eur"].sum() or 0.0) if not live_rows.empty else 0.0

    # 1. KPI Ribbon (AC-7)
    render_kpi_ribbon(live_rows, total_val, total_cost, total_pnl, quote_state)

    # 2. Movers Strip (AC-8)
    render_movers_strip(live_rows)

    # 3. Live Positions Table (AC-1, AC-12, AC-13)
    with section_header("Live Portfolio Holdings", "Intraday position values and day moves"):
        render_live_table(live_rows)

    # 4. Exposure Treemap (AC-6)
    with section_header("Portfolio Exposure Heatmap", "Multi-dimension asset distribution"):
        dim_options = ["Sector", "Region", "Currency", "Nature"]
        # Pending Copilot exposure dimension (AC-17)
        pending_dim = state.get(state.K.INVESTMENTS_EXP_DIM)
        if pending_dim in dim_options:
            st.session_state["portfolio_treemap_dim_pills"] = pending_dim
            state.delete(state.K.INVESTMENTS_EXP_DIM)

        if "portfolio_treemap_dim_pills" not in st.session_state:
            st.session_state["portfolio_treemap_dim_pills"] = "Sector"

        selected_dim = st.pills(
            "Treemap Dimension",
            options=dim_options,
            key="portfolio_treemap_dim_pills",
            label_visibility="collapsed",
        ) or "Sector"

        with st.container(border=True, key="investments_treemap_panel"):
            carpet_fig = build_investments_market_carpet(
                consolidated_df, group_col=selected_dim, height=380
            )
            render_chart(carpet_fig, width="stretch", key="investments_market_carpet")

    # 5. Equity Curve (AC-9)
    with section_header("Portfolio Equity Curve", "Value over time and historical cost basis"):
        c_curve_hdr, c_curve_pills = st.columns([0.65, 0.35], vertical_alignment="center")
        with c_curve_pills:
            range_choice = st.pills(
                "Timeframe",
                options=["1M", "3M", "6M", "1Y", "All"],
                default="3M",
                key="portfolio_equity_curve_pills",
                label_visibility="collapsed",
            ) or "3M"

        snap_rows = []
        if conn is not None:
            try:
                snap_rows = HoldingRepository.get_portfolio_snapshots(conn)
            except Exception:
                snap_rows = []

        curve_fig = build_equity_curve(snap_rows, range_filter=range_choice, height=340)
        with st.container(border=True):
            render_chart(curve_fig, width="stretch", key="portfolio_equity_curve_chart")

    # 6. P&L Contribution & Sector Performance Heat (AC-11)
    col_pnl_cont, col_sec_heat = st.columns([1.1, 0.9], gap="medium")
    with col_pnl_cont:
        with section_header("P&L Contribution", "Unrealized profit/loss per holding"):
            with st.container(border=True):
                pnl_fig = build_pnl_contribution_chart(live_rows, height=320)
                render_chart(pnl_fig, width="stretch", key="portfolio_pnl_contrib_chart")

    with col_sec_heat:
        with section_header("Sector Day Move", "Weighted intraday move by sector"):
            with st.container(border=True):
                heat_fig = build_sector_performance_heat(live_rows, height=320)
                render_chart(heat_fig, width="stretch", key="portfolio_sector_heat_chart")
