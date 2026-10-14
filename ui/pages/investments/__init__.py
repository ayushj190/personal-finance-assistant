"""Investments page package re-exporting render entrypoint, fragments, and components."""

from datetime import date
import streamlit as st
from config import DB_PATH
from connectors.market_data_service import update_quotes
from db import database
from db.repositories import HoldingRepository
from services.navigation import TAB_MAP
from services.portfolio import get_consolidated_holdings_df
from ui import state

# Submodule re-exports
from ui.pages.investments.tabs import (
    _render_portfolio_fragment,
    _render_allocation_fragment,
    _render_income_fragment,
    _render_goals_fragment,
)
from ui.pages.investments.news import _render_market_news_fragment
from ui.pages.investments.holdings import render_copy_portfolios, render_holdings_table
from ui.pages.investments.exposure import render_exposure_visualizer
from ui.pages.investments.watchlist import render_live_quotes_and_watchlist
from ui.pages.investments.realized_pnl import render_realized_pnl_panel
from ui.pages.investments.live import render_live_portfolio_view
from ui.page_panel import render_page_panel

# Re-exports for test compatibility and patch mocking
from ui.components import format_money, is_hidden, kpi_card, section_header
from ui.charts import ASSET_TYPE_COLORS, SECTOR_COLORS, build_drift_bar_chart, build_investments_market_carpet


def render() -> None:
    render_page_panel("investments")
    conn = database.connect(DB_PATH)
    try:
        holdings_df = HoldingRepository.get_v_holdings_df(conn)

        if holdings_df.empty:
            st.info("No investments found.")
            return

        direct_tickers = [
            t
            for t in holdings_df["ticker"].unique()
            if not t.startswith("COPY:") and not t.startswith("ID_")
        ]
        if direct_tickers:
            today_str = date.today().isoformat()
            placeholders = ",".join("?" for _ in direct_tickers)
            try:
                row = conn.execute(
                    f"SELECT COUNT(DISTINCT ticker) FROM market_quotes WHERE quote_date = ? AND ticker IN ({placeholders})",
                    (today_str, *direct_tickers),
                ).fetchone()
                quotes_today = row[0] if row else 0
            except Exception:
                quotes_today = 0

            if quotes_today < len(direct_tickers):
                update_quotes(direct_tickers, conn)
                holdings_df = HoldingRepository.get_v_holdings_df(conn)

        copy_mask = holdings_df["ticker"].str.startswith("COPY:", na=False)
        copy_df = holdings_df[copy_mask].copy()
        direct_df = holdings_df[~copy_mask].copy()

        fx_close = HoldingRepository.get_latest_fx_quote(conn, "EURUSD=X")
        usd_to_eur = (1.0 / fx_close) if fx_close else 0.892

        consolidated_df = get_consolidated_holdings_df(conn)

        active_positions_count = (
            int(consolidated_df["ticker"].nunique())
            if not consolidated_df.empty and "ticker" in consolidated_df.columns
            else len(holdings_df)
        )

        t_port, t_alloc, t_inc, t_goals = st.tabs(
            list(TAB_MAP.values()),
            default=TAB_MAP.get(
                st.session_state.pop(state.K.INVESTMENTS_ACTIVE_TAB, None)
            ),
            key=f"investments_tabs_{st.session_state.get(state.K.INVESTMENTS_TABS_GENERATION, 0)}",
        )

        with t_port:
            _render_portfolio_fragment(
                holdings_df,
                copy_df,
                direct_df,
                consolidated_df,
                usd_to_eur,
                active_positions_count=active_positions_count,
                conn=conn,
            )

        with t_alloc:
            _render_allocation_fragment(conn, consolidated_df)

        with t_inc:
            _render_income_fragment(conn, holdings_df)

        with t_goals:
            _render_goals_fragment(conn)

        st.divider()
        _render_market_news_fragment()

    finally:
        conn.close()


__all__ = [
    "render",
    "_render_portfolio_fragment",
    "_render_allocation_fragment",
    "_render_income_fragment",
    "_render_goals_fragment",
    "_render_market_news_fragment",
    "render_copy_portfolios",
    "render_holdings_table",
    "render_live_portfolio_view",
    "render_exposure_visualizer",
    "render_live_quotes_and_watchlist",
    "render_realized_pnl_panel",
    "format_money",
    "is_hidden",
    "kpi_card",
    "section_header",
    "update_quotes",
    "DB_PATH",
]
