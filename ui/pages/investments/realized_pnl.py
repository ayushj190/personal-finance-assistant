import sqlite3
from typing import Optional
import streamlit as st

import ui.pages.investments
from config import DB_PATH
from db import database
from db.repositories import HoldingRepository
from ui.components import format_money, kpi_card, section_header


def render_realized_pnl_panel(conn: Optional[sqlite3.Connection] = None) -> None:
    pnl_conn = conn
    should_close_pnl = False
    if not database.is_conn_open(pnl_conn):
        try:
            pnl_conn = database.connect(DB_PATH)
            should_close_pnl = True
        except Exception:
            pnl_conn = None

    if pnl_conn is None:
        return

    try:
        with section_header("Realized Profit & Loss", "Historical returns and proceeds from closed positions"):
            pnl_summary = HoldingRepository.get_realized_pnl_summary(pnl_conn)
            closed_df = HoldingRepository.get_closed_holdings_df(pnl_conn)

            r_pnl = float(pnl_summary.get("realized_pnl_eur", 0.0))
            r_proc = float(pnl_summary.get("total_proceeds_eur", 0.0))
            r_count = int(pnl_summary.get("closed_count", 0))
            r_cost = r_proc - r_pnl
            r_pct = (r_pnl / r_cost * 100.0) if r_cost > 0 else 0.0

            rc1, rc2, rc3 = st.columns(3)
            with rc1:
                pnl_str = f"{'+' if r_pnl >= 0 else ''}{format_money(r_pnl)}"
                kpi_card("Cumulative Realized P&L", pnl_str, delta_str=f"{r_pct:+.1f}%")
            with rc2:
                kpi_card("Total Closed Proceeds", format_money(r_proc))
            with rc3:
                cnt_str = "**** closed" if ui.pages.investments.is_hidden() else f"{r_count} positions closed"
                kpi_card("Closed Positions", cnt_str)

            if not closed_df.empty:
                disp_closed = closed_df.copy()
                if ui.pages.investments.is_hidden():
                    disp_closed["Cost Basis (€)"] = "€****"
                    disp_closed["Proceeds (€)"] = "€****"
                    disp_closed["Realized P&L (€)"] = "€****"
                    disp_closed["Return (%)"] = "****%"
                else:
                    disp_closed["Cost Basis (€)"] = disp_closed["cost_basis"].map(lambda x: f"€{x:,.2f}")
                    disp_closed["Proceeds (€)"] = disp_closed["proceeds"].map(lambda x: f"€{x:,.2f}")
                    disp_closed["Realized P&L (€)"] = disp_closed["realized_pnl"].map(
                        lambda x: f"{'+' if x >= 0 else ''}€{x:,.2f}"
                    )
                    disp_closed["Return (%)"] = disp_closed["return_pct"].map(lambda x: f"{x:+.2f}%")

                cols_to_show = [
                    "ticker",
                    "name",
                    "closed_date",
                    "Cost Basis (€)",
                    "Proceeds (€)",
                    "Realized P&L (€)",
                    "Return (%)",
                ]
                st.dataframe(
                    disp_closed[[c for c in cols_to_show if c in disp_closed.columns]],
                    use_container_width=True,
                    hide_index=True,
                )
            else:
                st.caption("No closed positions recorded yet.")
    finally:
        if should_close_pnl:
            pnl_conn.close()
