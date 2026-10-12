import json
from pathlib import Path
from typing import Any, Optional
import pandas as pd
import plotly.express as px
import streamlit as st

from config import DB_PATH
from connectors.etoro_service import EtoroService
from connectors.market_data_service import classify_asset, enrich_ticker_metadata, update_quotes
from db import database
from db.repositories import AccountRepository, HoldingRepository, TransactionRepository
from services.dividend_service import calculate_dividend_projections
from services.portfolio import (
    calculate_drift,
    get_consolidated_holdings_df,
    get_dimension_exposure_df,
    get_smart_allocation_profiles,
)
from ui.charts import ASSET_TYPE_COLORS, SECTOR_COLORS, build_drift_bar_chart, build_investments_market_carpet
from ui.components import format_money, is_hidden, kpi_card, section_header
from ui.theme import render_chart

# Theme palette maps
ASSET_TYPE_COLORS = {
    "STOCK": "#38BDF8",
    "ETF": "#2DD4BF",
    "CRYPTO": "#34D399",
    "COMMODITY": "#FBBF24",
    "BOND": "#A78BFA",
    "CASH": "#94A3B8",
    "OTHER": "#CBD5E1",
}

SECTOR_COLORS = {
    "Technology": "#38BDF8",
    "Gold & Metals": "#FBBF24",
    "Energy": "#FB7185",
    "Defense & Aerospace": "#A78BFA",
    "Cryptocurrency": "#34D399",
    "Broad Market ETF": "#2DD4BF",
    "Financial Services": "#818CF8",
    "Diversified": "#64748B",
}


@st.cache_data(ttl=60)
def load_cached_json(file_path: Path) -> Optional[Any]:
    if file_path.exists():
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return None


def render_copy_portfolios(copy_df: pd.DataFrame, usd_to_eur: float) -> None:
    cache_path = Path(__file__).resolve().parent.parent.parent / "data" / "etoro_mirrors_cache.json"
    meta_path = Path(__file__).resolve().parent.parent.parent / "data" / "ticker_metadata.json"

    mirrors_data = load_cached_json(cache_path)
    mirrors_map = {m["ticker"]: m for m in mirrors_data} if mirrors_data else {}
    meta_map = load_cached_json(meta_path) or {}

    for _, row in copy_df.iterrows():
        ticker = row["ticker"]
        username = ticker.replace("COPY:", "")
        mirror_info = mirrors_map.get(ticker, {})

        invested_usd = mirror_info.get("invested_usd", float(row["cost_basis"]))
        val_usd = mirror_info.get("value_usd", float(row["value_eur"]) / usd_to_eur)
        pnl_usd = mirror_info.get("unrealized_pnl_usd", val_usd - invested_usd)
        ret_pct = (pnl_usd / invested_usd * 100.0) if invested_usd > 0 else 0.0

        invested_eur = invested_usd * usd_to_eur
        val_eur = val_usd * usd_to_eur
        pnl_eur = pnl_usd * usd_to_eur
        pnl_sign = "+" if pnl_eur >= 0 else ""

        underlying = mirror_info.get("positions", [])
        a_types: dict[str, float] = {}
        total_val = val_usd
        for p in underlying:
            sym = p.get("symbol") or f"ID_{p.get('instrument_id')}"
            m_info = meta_map.get(sym, {})
            a_type = m_info.get("asset_type")
            if not a_type:
                a_type = "etf" if "ETF" in (p.get("name") or "").upper() else "stock"
            p_val = float(p.get("amount_usd", 0.0)) + float(p.get("pnl_usd", 0.0))
            a_types[a_type] = a_types.get(a_type, 0.0) + p_val

        breakdown_str = " | ".join(
            [f"{k.upper()}: {(v / total_val * 100):.1f}%" for k, v in a_types.items() if total_val > 0]
        )

        if is_hidden():
            label = f"👤 {username}  |  Invested: €****  |  Value: €****  |  P&L: €****"
        else:
            label = (
                f"👤 {username}  |  Invested: €{invested_eur:,.2f}  |  "
                f"Value: €{val_eur:,.2f}  |  P&L: {pnl_sign}€{abs(pnl_eur):,.2f} ({pnl_sign}{ret_pct:.1f}%)  |  🎯 {breakdown_str}"
            )

        with st.expander(label, expanded=False):
            st.caption(
                f"**Positions:** {mirror_info.get('positions_count', len(underlying))}  |  "
                f"**Available Cash:** ${mirror_info.get('available_cash_usd', 0.0):,.2f}"
            )

            if underlying:
                u_items = []
                for p in underlying:
                    sym = p.get("symbol") or f"ID_{p.get('instrument_id')}"
                    p_val_usd = float(p.get("amount_usd", 0.0)) + float(p.get("pnl_usd", 0.0))
                    u_items.append({
                        "Symbol": sym,
                        "Name": p.get("name") or sym,
                        "Value ($)": f"${p_val_usd:,.2f}" if not is_hidden() else "$****",
                        "Value (€)": f"€{p_val_usd * usd_to_eur:,.2f}" if not is_hidden() else "€****",
                    })
                u_df = pd.DataFrame(u_items)
                st.dataframe(u_df, use_container_width=True, hide_index=True)


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
    # 1. 4-KPI ribbon (AC-1, AC-7)
    total_value = float(holdings_df["value_eur"].sum())
    total_cost = float(holdings_df["cost_basis"].sum())
    total_pnl = float(holdings_df["unrealized_pnl_eur"].sum())
    pnl_pct = (total_pnl / total_cost * 100.0) if total_cost > 0 else 0.0
    unquoted_count = int((holdings_df["latest_close"] <= 0).sum()) if "latest_close" in holdings_df.columns else 0

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        kpi_card("Portfolio Value", format_money(total_value))
    with c2:
        kpi_card("Total Cost Basis", format_money(total_cost))
    with c3:
        pnl_str = f"{'+' if total_pnl >= 0 else ''}{format_money(total_pnl)}"
        kpi_card("Unrealized P&L", pnl_str, delta_str=f"{pnl_pct:+.1f}%")
    with c4:
        sub = (
            ("⏱️ **** quote delayed" if is_hidden() else f"⏱️ {unquoted_count} quote delayed")
            if unquoted_count > 0
            else "All quotes live"
        )
        if active_positions_count is None:
            if not consolidated_df.empty and "ticker" in consolidated_df.columns:
                active_positions_count = consolidated_df["ticker"].nunique()
            else:
                active_positions_count = len(holdings_df)
        pos_str = "**** assets" if is_hidden() else f"{active_positions_count} assets"
        kpi_card("Active Positions", pos_str, subtext=sub)

    # 2. Multi-dimension Exposure Visualizer (Sector & Heatmap prominent, Asset Class collapsible)
    if not consolidated_df.empty:
        with section_header("Sector & Strategic Allocation", "Portfolio exposure heatmap and multi-dimension distribution"):
            # Prominent Market Carpet Heatmap
            with st.container(border=True, key="investments_exposure_heatmap_panel"):
                st.markdown("##### 🗺️ Portfolio Exposure Heatmap")
                carpet_fig = build_investments_market_carpet(consolidated_df, height=380)
                render_chart(carpet_fig, use_container_width=True, key="investments_market_carpet")

            dim_options = ["Sector", "Region", "Currency", "Nature"]
            selected_dim = st.pills(
                "Exposure Dimension",
                options=dim_options,
                default="Sector",
                key="portfolio_exposure_dim_pills",
                label_visibility="collapsed",
            ) or "Sector"

            dim_df = get_dimension_exposure_df(consolidated_df, selected_dim)
            col_donut, col_bar = st.columns([1, 1])

            with col_donut:
                with st.container(border=True):
                    color_map = SECTOR_COLORS if selected_dim == "Sector" else None
                    donut_fig = px.pie(
                        dim_df,
                        names="bucket",
                        values="value_eur",
                        hole=0.55,
                        color="bucket" if color_map else None,
                        color_discrete_map=color_map,
                        title=f"Allocation by {selected_dim}",
                    )
                    if is_hidden():
                        donut_fig.update_traces(
                            texttemplate="%{label}<br>****%",
                            hovertemplate="Censored<extra></extra>",
                        )
                    else:
                        donut_fig.update_traces(
                            texttemplate="%{label}<br>%{percent:.1%}",
                            hovertemplate="<b>%{label}</b><br>Value: €%{value:,.2f}<br>%{percent:.1%}<extra></extra>",
                        )
                    donut_fig.update_layout(
                        showlegend=False,
                        margin=dict(t=40, l=10, r=10, b=10),
                        height=320,
                    )
                    render_chart(donut_fig, use_container_width=True)

            with col_bar:
                with st.container(border=True):
                    bar_data = dim_df.sort_values(by="weight_pct", ascending=True)
                    bar_fig = px.bar(
                        bar_data,
                        x="weight_pct",
                        y="bucket",
                        orientation="h",
                        text=bar_data["weight_pct"].map(
                            lambda x: "****%" if is_hidden() else f"{x:.1f}%"
                        ),
                        color="bucket" if color_map else None,
                        color_discrete_map=color_map,
                        title=f"{selected_dim} Breakdown (%)",
                    )
                    if is_hidden():
                        bar_fig.update_traces(hovertemplate="Censored<extra></extra>")
                    else:
                        bar_fig.update_traces(
                            hovertemplate="<b>%{y}</b><br>Weight: %{x:.1f}%<extra></extra>"
                        )
                    bar_fig.update_layout(
                        showlegend=False,
                        margin=dict(t=40, l=110, r=20, b=20),
                        height=320,
                        xaxis=dict(ticksuffix="%", automargin=True),
                        yaxis=dict(automargin=True),
                    )
                    render_chart(bar_fig, use_container_width=True)

            # Collapsible Asset Class Breakdown (default minimized)
            with st.expander("💼 Asset Class Breakdown (Stocks, ETFs, Crypto, Commodities)", expanded=False):
                ac_dim_df = get_dimension_exposure_df(consolidated_df, "Asset Class")
                ac_c1, ac_c2 = st.columns([1, 1])
                with ac_c1:
                    with st.container(border=True):
                        ac_fig = px.pie(
                            ac_dim_df,
                            names="bucket",
                            values="value_eur",
                            hole=0.5,
                            color="bucket",
                            color_discrete_map=ASSET_TYPE_COLORS,
                            title="Asset Class Distribution",
                        )
                        ac_fig.update_layout(height=280, margin=dict(t=30, l=10, r=10, b=10))
                        render_chart(ac_fig, use_container_width=True)
                with ac_c2:
                    table_ac = ac_dim_df.copy()
                    if is_hidden():
                        table_ac["Value (€)"] = "€****"
                        table_ac["Weight (%)"] = "****%"
                    else:
                        table_ac["Value (€)"] = table_ac["value_eur"].map(lambda v: f"€{v:,.2f}")
                        table_ac["Weight (%)"] = table_ac["weight_pct"].map(lambda w: f"{w:.1f}%")
                    table_ac.rename(columns={"bucket": "Asset Class"}, inplace=True)
                    st.dataframe(
                        table_ac[["Asset Class", "Value (€)", "Weight (%)"]],
                        use_container_width=True,
                        hide_index=True,
                    )

            with st.expander(f"📋 View {selected_dim} Details Table", expanded=False):
                table_df = dim_df.copy()
                if is_hidden():
                    table_df["Value (€)"] = "€****"
                    table_df["Weight (%)"] = "****%"
                else:
                    table_df["Value (€)"] = table_df["value_eur"].map(lambda v: f"€{v:,.2f}")
                    table_df["Weight (%)"] = table_df["weight_pct"].map(lambda w: f"{w:.1f}%")
                table_df.rename(columns={"bucket": selected_dim}, inplace=True)
                st.dataframe(
                    table_df[[selected_dim, "Value (€)", "Weight (%)"]],
                    use_container_width=True,
                    hide_index=True,
                )

    # 3. Active Holdings Table (AC-2, AC-7)
    with section_header("Portfolio Holdings"):
        df_disp = holdings_df.copy()
        is_copy = df_disp["ticker"].str.startswith("COPY:", na=False)
        df_disp["Position Type"] = is_copy.map(
            lambda c: f"Copy: {c.replace('COPY:', '')}" if str(c).startswith("COPY:") else "Direct Holding"
        )
        df_disp["Position Type"] = [
            f"Copy: {t.replace('COPY:', '')}" if t.startswith("COPY:") else "Direct Holding"
            for t in df_disp["ticker"]
        ]

        # Calculate average open price safely
        df_disp["Avg Open Price"] = (
            df_disp["cost_basis_native"] / df_disp["quantity"]
        ).fillna(0)

        # Missing quote fallback & delayed indicator (AC-7)
        delayed_mask = (df_disp["latest_close"] <= 0) | df_disp["latest_close"].isna()
        df_disp["Quote Status"] = delayed_mask.map(
            lambda d: "⏱️ Quote delayed" if d else "🟢 Live"
        )
        df_disp["Market Price"] = df_disp["latest_close"]
        df_disp.loc[delayed_mask, "Market Price"] = df_disp.loc[delayed_mask, "Avg Open Price"]

        df_disp["P&L (€)"] = df_disp["unrealized_pnl_eur"]
        df_disp["P&L (%)"] = (
            df_disp["unrealized_pnl_eur"] / df_disp["cost_basis"] * 100
        ).fillna(0)

        disp_cols = {
            "ticker": "Ticker",
            "name": "Asset Name",
            "Position Type": "Type",
            "asset_type": "Asset Class",
            "quantity": "Units",
            "Avg Open Price": "Avg Open",
            "cost_basis": "Cost Basis (€)",
            "Market Price": "Current Price",
            "value_eur": "Value (€)",
            "P&L (€)": "P&L (€)",
            "P&L (%)": "P&L (%)",
            "Quote Status": "Status",
        }
        out_df = df_disp.rename(columns=disp_cols)[list(disp_cols.values())]

        if is_hidden():
            out_df["Asset Name"] = "****"
            out_df["Ticker"] = "****"
            for col in [
                "Units",
                "Avg Open",
                "Cost Basis (€)",
                "Current Price",
                "Value (€)",
                "P&L (€)",
            ]:
                out_df[col] = "****"
            out_df["P&L (%)"] = "****%"
        else:
            out_df["Units"] = out_df["Units"].map(lambda x: f"{x:,.4f}")
            for col in ["Avg Open", "Current Price"]:
                out_df[col] = out_df[col].map(lambda x: f"{x:,.2f}")
            for col in ["Cost Basis (€)", "Value (€)"]:
                out_df[col] = out_df[col].map(lambda x: f"€{x:,.2f}")
            out_df["P&L (€)"] = out_df["P&L (€)"].map(
                lambda x: f"{'+' if x >= 0 else ''}€{x:,.2f}"
            )
            out_df["P&L (%)"] = out_df["P&L (%)"].map(lambda x: f"{x:+.1f}%")

        st.dataframe(out_df, use_container_width=True, hide_index=True)

    # 4. Copy Portfolios Section (if present)
    if not copy_df.empty:
        with section_header("eToro Copied Traders"):
            render_copy_portfolios(copy_df, usd_to_eur)

    # 5. Market Quotes Section & On-demand Toggle (AC-4)
    with section_header("Live Market Quotes"):
        if not direct_df.empty:
            perf_df = direct_df.copy()
            perf_df["unrealized_return_pct"] = (
                perf_df["unrealized_pnl_eur"] / perf_df["cost_basis"] * 100
            ).fillna(0)

            disp_perf = perf_df[
                ["ticker", "name", "latest_close", "value_eur", "unrealized_pnl_eur", "unrealized_return_pct"]
            ].copy()
            disp_perf.columns = [
                "Ticker",
                "Asset Name",
                "Market Price",
                "Position Value (€)",
                "Total P&L (€)",
                "Return (%)",
            ]

            if is_hidden():
                disp_perf["Asset Name"] = "****"
                disp_perf["Ticker"] = "****"
                disp_perf["Market Price"] = "****"
                disp_perf["Position Value (€)"] = "€****"
                disp_perf["Total P&L (€)"] = "€****"
                disp_perf["Return (%)"] = "****%"
            else:
                disp_perf["Market Price"] = disp_perf["Market Price"].map(
                    lambda x: f"{x:,.2f}" if pd.notnull(x) and x > 0 else "Delayed"
                )
                disp_perf["Position Value (€)"] = disp_perf["Position Value (€)"].map(
                    lambda x: f"€{x:,.2f}"
                )
                disp_perf["Total P&L (€)"] = disp_perf["Total P&L (€)"].map(
                    lambda x: f"{'+' if x >= 0 else ''}€{x:,.2f}"
                )
                disp_perf["Return (%)"] = disp_perf["Return (%)"].map(lambda x: f"{x:+.2f}%")

            st.dataframe(disp_perf, use_container_width=True, hide_index=True)

        # 4. Minimizable live TradingView watchlist card (AC-3)
        # Extract unique symbols from all active holdings (both direct and prominent copy assets)
        all_tickers: list[str] = []
        if not consolidated_df.empty and "ticker" in consolidated_df.columns:
            for t in consolidated_df["ticker"].dropna().unique():
                ts = str(t).replace("COPY:", "").strip()
                if ts and not ts.startswith("ID_") and ts not in all_tickers:
                    all_tickers.append(ts)
        elif not direct_df.empty:
            for t in direct_df["ticker"].dropna().unique():
                ts = str(t).strip()
                if ts and not ts.startswith("ID_") and ts not in all_tickers:
                    all_tickers.append(ts)

        if all_tickers:
            if "tv_watchlist_minimized" not in st.session_state:
                st.session_state["tv_watchlist_minimized"] = False

            c_tv_head, c_tv_act = st.columns([0.85, 0.15], vertical_alignment="center")
            with c_tv_head:
                section_header("Live Market Quotes & TradingView Watchlist", f"{len(all_tickers)} distinct active assets • Real-time market stream")
            with c_tv_act:
                is_min = st.session_state["tv_watchlist_minimized"]
                btn_txt = "➕ Expand" if is_min else "➖ Minimize"
                if st.button(btn_txt, key="btn_toggle_tv_watchlist"):
                    st.session_state["tv_watchlist_minimized"] = not is_min
                    st.rerun()

            if not st.session_state["tv_watchlist_minimized"]:
                tv_symbols = []
                for t in all_tickers[:30]:  # Up to 30 distinct prominent assets
                    sym_clean = t.split(".")[0] if "." in t else t
                    tv_symbols.append({"name": sym_clean, "displayName": sym_clean})

                theme = st.get_option("theme.base")
                tv_content_height = max(360, len(tv_symbols) * 44 + 80)
                blur_overlay = (
                    """<div style="position: absolute; top: 0; right: 0; width: 60%; height: 100%; backdrop-filter: blur(8px); z-index: 1000; pointer-events: none;"></div>"""
                    if is_hidden()
                    else ""
                )
                tv_html = f"""
                <div style="position: relative; width: 100%; height: 380px; max-height: 380px; overflow-y: auto; overflow-x: hidden; border-radius: 12px; border: 1px solid rgba(128,128,128,0.2); box-shadow: 0 4px 16px rgba(0,0,0,0.15);">
                    {blur_overlay}
                    <div class="tradingview-widget-container">
                      <div class="tradingview-widget-container__widget"></div>
                      <script type="text/javascript" src="https://s3.tradingview.com/external-embedding/embed-widget-market-quotes.js" async>
                      {{
                      "width": "100%",
                      "height": {tv_content_height},
                      "symbolsGroups": [
                        {{
                          "name": "Portfolio Assets",
                          "originalName": "Holdings",
                          "symbols": {json.dumps(tv_symbols)}
                        }}
                      ],
                      "showSymbolLogo": true,
                      "isTransparent": true,
                      "colorTheme": "{'light' if theme == 'light' else 'dark'}",
                      "locale": "en"
                    }}
                      </script>
                    </div>
                </div>
                """
                st.components.v1.html(tv_html, height=390)
        else:
            st.caption("No active holdings found for live market feed.")

    # 5. Dedicated Realized P&L Panel and closed positions (AC-6)
    pnl_conn = conn
    should_close_pnl = False
    if not database.is_conn_open(pnl_conn):
        try:
            pnl_conn = database.connect(DB_PATH)
            should_close_pnl = True
        except Exception:
            pnl_conn = None

    if pnl_conn is not None:
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
                    cnt_str = "**** closed" if is_hidden() else f"{r_count} positions closed"
                    kpi_card("Closed Positions", cnt_str)

                if not closed_df.empty:
                    disp_closed = closed_df.copy()
                    if is_hidden():
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

                    cols_to_show = ["ticker", "name", "closed_date", "Cost Basis (€)", "Proceeds (€)", "Realized P&L (€)", "Return (%)"]
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
        # Fetch smart risk-tailored and saved allocation profiles
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

        # Fetch targets from profile object
        targets = profile.get("targets", {})
        if not targets and "id" in profile:
            targets = HoldingRepository.get_allocation_targets(alloc_conn, profile["id"])

        # Calculate actual values per bucket
        dimension = profile.get("dimension", "asset_type")
        current_values: dict[str, float] = {}

        if not consolidated_df.empty:
            col_to_check = dimension if dimension in consolidated_df.columns else "asset_type"
            for _, row in consolidated_df.iterrows():
                b_key = str(row.get(col_to_check) or "other")
                current_values[b_key] = current_values.get(
                    b_key, 0.0
                ) + float(row.get("value_eur", 0.0))

        if profile.get("include_cash"):
            current_values["cash"] = AccountRepository.get_total_cash_balance(alloc_conn)

        if not current_values:
            st.warning("No value to balance for this profile.")
            return

        drift_data = calculate_drift(
            current_values, targets, drift_band_pct=profile["drift_band_pct"]
        )

        col_chart, col_targets = st.columns([1, 1])
        with col_chart:
            with st.container(border=True):
                st.markdown("##### ⚖️ Target vs Actual Drift")
                render_chart(
                    build_drift_bar_chart(
                        drift_data, drift_band_pct=profile["drift_band_pct"]
                    ),
                    use_container_width=True,
                )

        with col_targets:
            drift_df = pd.DataFrame(drift_data)[
                ["bucket", "actual_pct", "target_pct", "drift_pp", "alert"]
            ]
            drift_df.columns = [
                "Bucket",
                "Actual %",
                "Target %",
                "Drift (pp)",
                "Action Needed",
            ]
            if is_hidden():
                drift_df["Actual %"] = "****%"
                drift_df["Target %"] = "****%"
                drift_df["Drift (pp)"] = "**** pp"
            else:
                drift_df["Actual %"] = drift_df["Actual %"].map(lambda x: f"{x:.1f}%")
                drift_df["Target %"] = drift_df["Target %"].map(lambda x: f"{x:.1f}%")
                drift_df["Drift (pp)"] = drift_df["Drift (pp)"].map(lambda x: f"{x:+.1f} pp")
            drift_df["Action Needed"] = drift_df["Action Needed"].map(
                lambda x: "⚠️ Rebalance" if x else "✅ On Target"
            )
            st.dataframe(drift_df, use_container_width=True, hide_index=True)
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
        # 1. Dividend Tracking & Cash Flow Projections
        with section_header("Dividend & Passive Income Forecast"):
            div_data = calculate_dividend_projections(inc_conn)

        d1, d2, d3 = st.columns(3)
        with d1:
            ann_str = (
                "€****"
                if is_hidden()
                else f"€{div_data['projected_annual_dividends_eur']:,.2f}"
            )
            kpi_card("Projected Annual Income", ann_str, subtext="Estimated forward dividends")
        with d2:
            yield_str = (
                "****"
                if is_hidden()
                else f"{div_data['average_dividend_yield_pct']:.2f}%"
            )
            kpi_card("Portfolio Yield", yield_str, subtext="Weighted average forward yield")
        with d3:
            mo_str = (
                "€****"
                if is_hidden()
                else f"€{div_data['monthly_average_eur']:,.2f}"
            )
            kpi_card("Monthly Average", mo_str, subtext="Projected passive monthly flow")

        if div_data["monthly_distribution"]:
            m_dist_df = pd.DataFrame(div_data["monthly_distribution"])
            col_m_chart, col_m_table = st.columns([1, 1])

            with col_m_chart:
                dist_fig = px.bar(
                    m_dist_df,
                    x="month",
                    y="payout_eur",
                    title="Projected Monthly Dividend Calendar (€)",
                    text=m_dist_df["payout_eur"].map(
                        lambda x: "€****" if is_hidden() else f"€{x:,.0f}"
                    ),
                    color_discrete_sequence=["#2DD4BF"],
                )
                dist_fig.update_layout(
                    margin=dict(t=35, l=55, r=20, b=25),
                    xaxis=dict(title="Month", automargin=True),
                    yaxis=dict(
                        title="Projected Payout (€)",
                        tickprefix="€",
                        automargin=True,
                    ),
                )
                if is_hidden():
                    dist_fig.update_traces(hovertemplate="Censored<extra></extra>")
                with st.container(border=True):
                    render_chart(dist_fig, use_container_width=True)

            with col_m_table:
                h_df = div_data["holdings_df"]
                if not h_df.empty:
                    disp_h = h_df[
                        ["ticker", "name", "value_eur", "yield_pct", "annual_dividend_eur"]
                    ].copy()
                    disp_h.columns = [
                        "Ticker",
                        "Asset",
                        "Value (€)",
                        "Est. Yield",
                        "Annual Div (€)",
                    ]
                    if is_hidden():
                        disp_h["Value (€)"] = "€****"
                        disp_h["Est. Yield"] = "****%"
                        disp_h["Annual Div (€)"] = "€****"
                        disp_h["Asset"] = "****"
                        disp_h["Ticker"] = "****"
                    else:
                        disp_h["Value (€)"] = disp_h["Value (€)"].map(
                            lambda x: f"€{x:,.2f}"
                        )
                        disp_h["Est. Yield"] = disp_h["Est. Yield"].map(
                            lambda x: f"{x:.1f}%"
                        )
                        disp_h["Annual Div (€)"] = disp_h["Annual Div (€)"].map(
                            lambda x: f"€{x:,.2f}"
                        )
                    st.dataframe(disp_h, use_container_width=True, hide_index=True)
                else:
                    st.caption("No dividend-generating assets tracked.")

            with section_header("Tax-Loss Harvesting Assistant"):
                loss_df = holdings_df[holdings_df["unrealized_pnl_eur"] < -50].sort_values(
                    by="unrealized_pnl_eur"
                )
                if not loss_df.empty:
                    disp_loss = loss_df[
                        ["ticker", "name", "value_eur", "unrealized_pnl_eur"]
                    ].copy()
                    disp_loss.columns = ["Ticker", "Asset", "Value (€)", "Unrealized P&L (€)"]
                    if is_hidden():
                        disp_loss["Value (€)"] = "€****"
                        disp_loss["Unrealized P&L (€)"] = "€****"
                        disp_loss["Asset"] = "****"
                        disp_loss["Ticker"] = "****"
                    else:
                        disp_loss["Value (€)"] = disp_loss["Value (€)"].map(
                            lambda x: f"€{x:,.2f}"
                        )
                        disp_loss["Unrealized P&L (€)"] = disp_loss[
                            "Unrealized P&L (€)"
                        ].map(lambda x: f"€{x:,.2f}")
                    st.dataframe(disp_loss, hide_index=True, use_container_width=True)
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
                ret_rate = st.slider(
                    "Expected Annual Return (%)",
                    1.0,
                    15.0,
                    7.0,
                    0.5,
                    key="fire_return_slider",
                )
            with c_sl2:
                inf_rate = st.slider(
                    "Expected Inflation (%)",
                    0.0,
                    10.0,
                    2.0,
                    0.5,
                    key="fire_inflation_slider",
                )
            real_return = (ret_rate - inf_rate) / 100.0

            if is_hidden():
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
            fig_fire.add_hline(
                y=fi_number,
                line_dash="dash",
                annotation_text="FI Target",
                line_color="#2DD4BF",
            )
            fig_fire.update_layout(
                xaxis=dict(title="Years from Now", automargin=True),
                yaxis=dict(
                    title="Net Worth (€)",
                    tickprefix="€",
                    tickformat="~s",
                    automargin=True,
                ),
                margin=dict(t=35, l=55, r=20, b=25),
            )
            if is_hidden():
                fig_fire.update_traces(hovertemplate="Censored<extra></extra>")
            with st.container(border=True):
                render_chart(fig_fire, use_container_width=True)

        with c_goals:
            st.subheader("🎯 Savings Goals")

            with st.expander("➕ Add New Goal", expanded=False):
                with st.form("new_goal_form_investments"):
                    g_name = st.text_input("Goal Name")
                    g_target = st.number_input(
                        "Target Amount (€)", min_value=1.0, step=100.0
                    )
                    cash_accounts = AccountRepository.get_cash_accounts(goals_conn)
                    acc_options = {a.id: a.name for a in cash_accounts}
                    g_acc = st.selectbox(
                        "Linked Account",
                        options=list(acc_options.keys()),
                        format_func=lambda x: acc_options[x],
                    )

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
                if is_hidden():
                    st.write(f"**{g['name']}** — █% (in ****)")
                    st.progress(pct)
                else:
                    st.write(
                        f"**{g['name']}** — €{bal:,.0f} / €{tar:,.0f} ({pct*100:.1f}%) in {g['account_name'] or 'None'}"
                    )
                    st.progress(pct)
    finally:
        if should_close_goals:
            goals_conn.close()


@st.fragment
def _render_market_news_fragment() -> None:
    """Render cached market news inside an isolated fragment at bottom of investments page."""
    with section_header("Market News", "Latest market news from eToro feed"):
        etoro = EtoroService()
        news = etoro.fetch_news(limit=10)
        is_configured = etoro.is_configured()

        if news:
            with st.container(height=300, border=True):
                for item in news:
                    c1, c2 = st.columns([1, 15])
                    with c1:
                        if item.get("avatar"):
                            st.image(item["avatar"], width=24)
                        else:
                            st.write("👤")
                    with c2:
                        text = item.get("text", "")
                        if len(text) > 200:
                            text = text[:200] + "..."
                        username = item.get("username", "eToro")
                        created = (item.get("created") or "")[:10]
                        st.markdown(
                            f"**@{username}** <span style='color: gray; font-size: 0.8em;'>• {created}</span><br/>"
                            f"<span style='font-size: 0.9em;'>{text}</span>",
                            unsafe_allow_html=True,
                        )
                    st.divider()
        else:
            if not is_configured:
                st.info("Connect eToro in Settings to view market news.")
            else:
                st.info("No news available right now.")


def render() -> None:
    conn = database.connect(DB_PATH)
    try:
        # Fetch active holdings
        holdings_df = HoldingRepository.get_v_holdings_df(conn)

        if holdings_df.empty:
            st.info("No investments found.")
            return

        # Update quotes for direct tickers
        direct_tickers = [
            t
            for t in holdings_df["ticker"].unique()
            if not t.startswith("COPY:") and not t.startswith("ID_")
        ]
        if direct_tickers:
            update_quotes(direct_tickers, conn)
            holdings_df = HoldingRepository.get_v_holdings_df(conn)

        # Split copy vs direct
        copy_mask = holdings_df["ticker"].str.startswith("COPY:", na=False)
        copy_df = holdings_df[copy_mask].copy()
        direct_df = holdings_df[~copy_mask].copy()

        # FX rate for USD display
        fx_close = HoldingRepository.get_latest_fx_quote(conn, "EURUSD=X")
        usd_to_eur = (1.0 / fx_close) if fx_close else 0.892

        consolidated_df = get_consolidated_holdings_df(conn)

        active_positions_count = (
            int(consolidated_df["ticker"].nunique())
            if not consolidated_df.empty and "ticker" in consolidated_df.columns
            else len(holdings_df)
        )

        # 4 top level tabs (AC-1)
        t_port, t_alloc, t_inc, t_goals = st.tabs([
            "📊 Portfolio & Holdings",
            "⚖️ Allocation & Drift",
            "💰 Income & Tax Strategy",
            "🎯 Goals & Planning",
        ])

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

