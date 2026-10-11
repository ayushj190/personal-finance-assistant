import pandas as pd
import streamlit as st
import plotly.express as px

from config import DB_PATH
from db import database
from db.repositories import AccountRepository, HoldingRepository, TransactionRepository
from services.portfolio import allocate_contribution, calculate_drift, full_rebalance, rebalance_without_selling
from services.dividend_service import calculate_dividend_projections
from ui.charts import build_drift_bar_chart
from ui.components import format_money, is_hidden, kpi_card, section_header
from ui.theme import render_chart
from connectors.market_data_service import update_quotes, get_ticker_logo_url, enrich_ticker_metadata, classify_asset
import streamlit.components.v1 as components
import json
from pathlib import Path


@st.cache_data(ttl=60)
def load_cached_json(file_path: Path):
    if file_path.exists():
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return None

@st.fragment(run_every="30s")
def render_copy_portfolios(copy_df, usd_to_eur):
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
        a_types = {}
        total_val = val_usd
        for p in underlying:
            sym = p.get("symbol") or f"ID_{p.get('instrument_id')}"
            m_info = meta_map.get(sym, {})
            a_type = m_info.get("asset_type")
            if not a_type:
                a_type = "etf" if "ETF" in (p.get("name") or "").upper() else "stock"
            p_val = p.get("amount_usd", 0.0) + p.get("pnl_usd", 0.0)
            a_types[a_type] = a_types.get(a_type, 0.0) + p_val
            
        breakdown_str = " | ".join([f"{k.upper()}: {(v/total_val*100):.1f}%" for k,v in a_types.items() if total_val > 0])
        
        if is_hidden():
            label = f"👤 {username}  |  Invested: €****  |  Value: €****  |  P&L: €****"
        else:
            label = f"👤 {username}  |  Invested: €{invested_eur:,.2f}  |  Value: €{val_eur:,.2f}  |  P&L: {pnl_sign}€{abs(pnl_eur):,.2f} ({pnl_sign}{ret_pct:.1f}%)  |  🎯 {breakdown_str}"

        with st.expander(label, expanded=False):
            st.caption(f"**Positions:** {mirror_info.get('positions_count', len(underlying))}  |  **Available Cash:** ${mirror_info.get('available_cash_usd', 0.0):,.2f}")
            show_all = st.checkbox("Show all assets", key=f"show_all_{username}")
            
            underlying = mirror_info.get("positions", [])
            if underlying:
                tv_symbols_underlying = []
                for p in underlying:
                    sym = p.get("symbol") or f"ID_{p.get('instrument_id')}"
                    if sym and not sym.startswith("ID_"):
                        tv_symbols_underlying.append({"name": sym.split('.')[0] if isinstance(sym, str) and '.' in sym else sym})

                if tv_symbols_underlying:
                    theme = st.get_option("theme.base")
                    tv_height = max(300, len(tv_symbols_underlying) * 45 + 90) if show_all else 300
                    blur_overlay = """<div style="position: absolute; top: 0; right: 0; width: 60%; height: 100%; backdrop-filter: blur(8px); z-index: 1000; pointer-events: none;"></div>""" if is_hidden() else ""
                    tv_html_u = f"""
                    <div style="position: relative; width: 100%; height: {tv_height}px;">
                        {blur_overlay}
                        <!-- TradingView Widget BEGIN -->
                        <div class="tradingview-widget-container">
                          <div class="tradingview-widget-container__widget"></div>
                          <script type="text/javascript" src="https://s3.tradingview.com/external-embedding/embed-widget-market-quotes.js" async>
                          {{
                          "width": "100%",
                          "height": {tv_height},
                          "symbolsGroups": [
                            {{
                              "name": "Live Market Prices",
                              "originalName": "Holdings",
                              "symbols": {json.dumps(tv_symbols_underlying)}
                            }}
                          ],
                          "showSymbolLogo": true,
                          "isTransparent": true,
                          "colorTheme": "{'light' if theme == 'light' else 'dark'}",
                          "locale": "en"
                        }}
                          </script>
                        </div>
                        <!-- TradingView Widget END -->
                    </div>
                    """
                    st.components.v1.html(tv_html_u, height=tv_height)


@st.fragment(run_every="60s")
def render():

    conn = database.connect(DB_PATH)

    # 1. Fetch Holdings
    holdings_df = HoldingRepository.get_v_holdings_df(conn)

    if holdings_df.empty:
        st.info("No investments found.")
        conn.close()
        return

    # Update quotes for real-time prices
    direct_tickers = [t for t in holdings_df["ticker"].unique() if not t.startswith("COPY:") and not t.startswith("ID_")]
    if direct_tickers:
        update_quotes(direct_tickers, conn)
        # Re-fetch after update to get latest prices in v_holdings
        holdings_df = HoldingRepository.get_v_holdings_df(conn)

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
    fx_close = HoldingRepository.get_latest_fx_quote(conn, "EURUSD=X")
    usd_to_eur = (1.0 / fx_close) if fx_close else 0.892


    # Build consolidated drill-down DataFrame
    import plotly.express as px
    from pathlib import Path
    
    cache_path = Path(__file__).resolve().parent.parent.parent / "data" / "etoro_mirrors_cache.json"
    meta_path = Path(__file__).resolve().parent.parent.parent / "data" / "ticker_metadata.json"
    
    mirrors_data = load_cached_json(cache_path)
    mirrors_map = {m["ticker"]: m for m in mirrors_data} if mirrors_data else {}
    meta_map = load_cached_json(meta_path) or {}

    consolidated_items = []
    for _, row in holdings_df.iterrows():
        t = row["ticker"]
        if t.startswith("COPY:"):
            m = mirrors_map.get(t, {})
            positions = m.get("positions", [])
            copy_user = m.get("username") or t.replace("COPY:", "")
            source_name = f"Copy: {copy_user}"
            for p in positions:
                sym = p.get("symbol") or f"ID_{p.get('instrument_id')}"
                p_name = p.get("name") or sym
                m_info = meta_map.get(sym, {})
                a_type, sec = classify_asset(sym, p_name, m_info)
                reg = m_info.get("country") or "Unknown"
                cur = m_info.get("currency") or "USD"
                exc = m_info.get("exchange") or "Unknown"

                val_usd = float(p.get("amount_usd", 0.0)) + float(p.get("pnl_usd", 0.0))
                val_eur = val_usd * usd_to_eur
                consolidated_items.append({
                    "ticker": sym,
                    "name": p_name,
                    "value_eur": val_eur,
                    "asset_class": "investment",
                    "asset_type": a_type,
                    "asset_type_display": a_type.upper(),
                    "region": reg,
                    "sector": sec,
                    "currency": cur,
                    "exchange": exc,
                    "source": source_name,
                    "display_label": p_name if p_name and not p_name.startswith("ID_") else sym
                })
        else:
            m_info = meta_map.get(t, {})
            d_name = row.get("name") or t
            a_type, sec = classify_asset(t, d_name, m_info)
            reg = m_info.get("country") or row.get("region") or "Unknown"
            cur = m_info.get("currency") or row.get("currency") or "EUR"
            exc = m_info.get("exchange") or "Unknown"
            consolidated_items.append({
                "ticker": t,
                "name": d_name,
                "value_eur": row.get("value_eur", 0.0),
                "asset_class": row.get("asset_class") or "investment",
                "asset_type": a_type,
                "asset_type_display": a_type.upper(),
                "region": reg,
                "sector": sec,
                "currency": cur,
                "exchange": exc,
                "source": "Direct Holdings",
                "display_label": d_name if d_name else t
            })

    all_syms = [item["ticker"] for item in consolidated_items if not item["ticker"].startswith("ID_")]
    names_map = {item["ticker"]: item["name"] for item in consolidated_items}
    if all_syms:
        enrich_ticker_metadata(list(set(all_syms)), names_map=names_map)

    consolidated_df = pd.DataFrame(consolidated_items)

    # 2. True Exposure Visualizer & Breakdown Section
    with section_header("True Exposure & Thematic Breakdown"):

        if not consolidated_df.empty:
            total_portfolio_eur = consolidated_df["value_eur"].sum()
            theme_totals = consolidated_df.groupby("sector")["value_eur"].sum().to_dict()

            # View Mode Selector
            view_col, _ = st.columns([3, 1])
            with view_col:
                view_mode = st.radio(
                    "Exposure Visualizer View:",
                    options=[
                        "By Sector & Theme",
                        "By Portfolio / Source",
                        "By Asset Type",
                        "By Region",
                        "All Assets (Flat)"
                    ],
                    index=0,
                    horizontal=True,
                    help="Group by Copy Portfolio for copied assets (keeping Direct Holdings grouped), or view by Sector/Theme, Asset Type, or Geography."
                )

            if view_mode == "By Sector & Theme":
                treemap_path = [px.Constant("Portfolio"), 'sector', 'display_label']
                chart_title = 'Consolidated True Exposure by Sector & Theme'
            elif view_mode == "By Portfolio / Source":
                treemap_path = [px.Constant("Portfolio"), 'source', 'display_label']
                chart_title = 'Consolidated True Exposure Grouped by Copy Portfolio / Source & Asset'
            elif view_mode == "By Asset Type":
                treemap_path = [px.Constant("Portfolio"), 'asset_type_display', 'display_label']
                chart_title = 'Consolidated True Exposure by Asset Type'
            elif view_mode == "By Region":
                treemap_path = [px.Constant("Portfolio"), 'region', 'display_label']
                chart_title = 'Consolidated True Exposure by Geographic Region'
            else:
                treemap_path = [px.Constant("Portfolio"), 'display_label']
                chart_title = 'All Consolidated Holdings (Weighted by Size)'

            SECTOR_COLORS = {
                "Technology": "#38BDF8", 
                "Gold & Metals": "#FBBF24", 
                "Energy": "#FB7185", 
                "Defense & Aerospace": "#A78BFA", 
                "Cryptocurrency": "#34D399", 
                "Broad Market ETF": "#2DD4BF"
            }
            PALETTE_SOURCES = ["#38BDF8", "#818CF8", "#A78BFA", "#34D399", "#FBBF24", "#FB7185", "#2DD4BF"]
            PALETTE_REGIONS = ["#38BDF8", "#2DD4BF", "#A78BFA", "#FBBF24", "#FB7185", "#34D399", "#818CF8"]
            ASSET_TYPE_COLORS = {
                "STOCK": "#38BDF8",
                "ETF": "#2DD4BF",
                "CRYPTO": "#34D399",
                "COMMODITY": "#FBBF24",
                "BOND": "#A78BFA",
                "CASH": "#94A3B8"
            }
        
            plot_df = consolidated_df.copy()
            if is_hidden():
                plot_df['display_label'] = [
                    ("█" * min(8, max(4, len(str(row['display_label']))))) + ("\u200b" * i)
                    for i, row in plot_df.iterrows()
                ]
                texttemplate = "%{label}<br>€**** (****)"
                hovertemplate = "<b>%{label}</b><extra></extra>"
            else:
                texttemplate = "%{label}<br>€%{value:,.2f} (%{percentRoot:.2%})"
                hovertemplate = "<b>%{label}</b><br>Value: €%{value:,.2f}<br>%{percentRoot:.2%} of Portfolio<extra></extra>"

            if view_mode == "By Sector & Theme":
                fig = px.treemap(
                    plot_df,
                    path=treemap_path,
                    values='value_eur',
                    color='sector',
                    color_discrete_map=SECTOR_COLORS,
                    title=chart_title
                )
            elif view_mode == "By Portfolio / Source":
                fig = px.treemap(
                    plot_df,
                    path=treemap_path,
                    values='value_eur',
                    color='source',
                    color_discrete_sequence=PALETTE_SOURCES,
                    title=chart_title
                )
            elif view_mode == "By Asset Type":
                fig = px.treemap(
                    plot_df,
                    path=treemap_path,
                    values='value_eur',
                    color='asset_type_display',
                    color_discrete_map=ASSET_TYPE_COLORS,
                    title=chart_title
                )
            elif view_mode == "By Region":
                fig = px.treemap(
                    plot_df,
                    path=treemap_path,
                    values='value_eur',
                    color='region',
                    color_discrete_sequence=PALETTE_REGIONS,
                    title=chart_title
                )
            else:
                # All Assets (Flat) - color-coded by sector for sleek thematic distinctions
                fig = px.treemap(
                    plot_df,
                    path=treemap_path,
                    values='value_eur',
                    color='sector',
                    color_discrete_map=SECTOR_COLORS,
                    title=chart_title
                )

            theme_opt = st.get_option("theme.base")
            border_color = "rgba(0, 0, 0, 0.15)" if theme_opt == "light" else "rgba(255, 255, 255, 0.18)"

            EXPOSURE_FONT_SIZE = 12

            fig.update_traces(
                root_color="lightgrey",
                texttemplate=texttemplate,
                hovertemplate=hovertemplate,
                textfont=dict(size=EXPOSURE_FONT_SIZE),
                insidetextfont=dict(size=EXPOSURE_FONT_SIZE),
                outsidetextfont=dict(size=EXPOSURE_FONT_SIZE),
                pathbar=dict(textfont=dict(size=EXPOSURE_FONT_SIZE)),
                marker=dict(
                    cornerradius=8,
                    pad=dict(b=4, l=4, r=4, t=28),
                    line=dict(color=border_color, width=1.5)
                )
            )
            fig.update_layout(
                margin=dict(t=50, l=10, r=10, b=10),
                height=700,
                font=dict(size=EXPOSURE_FONT_SIZE),
                title=dict(text=chart_title, font=dict(size=14)),
            )
            render_chart(fig, use_container_width=True)



            def get_theme_stat(sector_name):
                val = theme_totals.get(sector_name, 0.0)
                pct = (val / total_portfolio_eur * 100.0) if total_portfolio_eur > 0 else 0.0
                return val, pct

            st.markdown("<div style='margin-top: 10px; margin-bottom: 20px;'>", unsafe_allow_html=True)
            k1, k2, k3, k4, k5, k6 = st.columns(6)
        
            def render_colored_kpi(col, title, sector_name):
                val, pct = get_theme_stat(sector_name)
                color = SECTOR_COLORS.get(sector_name, "#94A3B8")
                if is_hidden():
                    val_str = "€****"
                    pct_str = "****"
                else:
                    val_str = f"€{val:,.0f}"
                    pct_str = f"{pct:.1f}% wt"
                with col:
                    st.markdown(f"""
                    <div style="border-top: 4px solid {color}; background-color: var(--secondary-background-color); border-radius: 8px; padding: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); border-left: 1px solid var(--tab-border); border-right: 1px solid var(--tab-border); border-bottom: 1px solid var(--tab-border);">
                        <div style="color: var(--text-muted); font-size: 0.85rem; font-weight: 600; margin-bottom: 4px;">{title}</div>
                        <div style="color: var(--text-color); font-size: 1.25rem; font-weight: 700; margin-bottom: 4px;">{val_str}</div>
                        <div style="color: {color}; font-size: 0.8rem; font-weight: 600;">{pct_str}</div>
                    </div>
                    """, unsafe_allow_html=True)

            render_colored_kpi(k1, "Technology", "Technology")
            render_colored_kpi(k2, "Gold & Metals", "Gold & Metals")
            render_colored_kpi(k3, "Energy", "Energy")
            render_colored_kpi(k4, "Defense & Aero", "Defense & Aerospace")
            render_colored_kpi(k5, "Crypto", "Cryptocurrency")
            render_colored_kpi(k6, "Broad ETFs", "Broad Market ETF")
            st.markdown("</div>", unsafe_allow_html=True)

            # Exposure Breakdown (Bar Chart + Table)
            c_chart, c_table = st.columns([1, 1])

            sec_df = consolidated_df.groupby("sector").agg(
                value_eur=("value_eur", "sum"),
                count=("ticker", "count"),
                top_asset=("ticker", lambda x: ", ".join(x.iloc[:3]))
            ).reset_index()
            sec_df["weight_pct"] = (sec_df["value_eur"] / total_portfolio_eur * 100.0) if total_portfolio_eur > 0 else 0.0
            sec_df = sec_df.sort_values(by="value_eur", ascending=True)

            with c_chart:
                bar_fig = px.bar(
                    sec_df,
                    x="weight_pct",
                    y="sector",
                    orientation="h",
                    text=sec_df["weight_pct"].map(lambda x: "****" if is_hidden() else f"{x:.1f}%"),
                    labels={"weight_pct": "Weight (%)", "sector": "Theme / Sector"},
                    title="Weight by Theme / Sector (%)",
                    color="sector",
                    color_discrete_map=SECTOR_COLORS
                )
                bar_fig.update_traces(
                    textfont=dict(size=EXPOSURE_FONT_SIZE)
                )
                bar_fig.update_layout(
                    showlegend=False,
                    margin=dict(t=40, l=10, r=10, b=10),
                    font=dict(size=EXPOSURE_FONT_SIZE),
                    title=dict(font=dict(size=14)),
                    xaxis=dict(
                        title=dict(text="Weight (%)", font=dict(size=EXPOSURE_FONT_SIZE)),
                        tickfont=dict(size=EXPOSURE_FONT_SIZE)
                    ),
                    yaxis=dict(
                        title=dict(text="", font=dict(size=EXPOSURE_FONT_SIZE)),
                        tickfont=dict(size=EXPOSURE_FONT_SIZE)
                    )
                )
            
                if is_hidden():
                    bar_fig.update_traces(hovertemplate="Censored<extra></extra>")
            
                render_chart(bar_fig, use_container_width=True)


            with c_table:
                display_sec_df = sec_df.sort_values(by="value_eur", ascending=False).copy()
                if is_hidden():
                    display_sec_df["Value (€)"] = "€****"
                    display_sec_df["Weight (%)"] = "****"
                    display_sec_df["Sample Holdings"] = "****"
                else:
                    display_sec_df["Value (€)"] = display_sec_df["value_eur"].map(lambda x: f"€{x:,.2f}")
                    display_sec_df["Weight (%)"] = display_sec_df["weight_pct"].map(lambda x: f"{x:.1f}%")
                    display_sec_df["Sample Holdings"] = display_sec_df["top_asset"]
            
                display_sec_df = display_sec_df.rename(columns={
                    "sector": "Theme / Sector",
                    "count": "Assets",
                })[["Theme / Sector", "Weight (%)", "Value (€)", "Assets", "Sample Holdings"]]
                st.dataframe(display_sec_df, use_container_width=True, hide_index=True)

            with st.expander("🔍 Consolidated Underlying Holdings Table (All Sources)"):
                disp_cols = ["ticker", "name", "asset_type_display", "sector", "region", "value_eur", "source"]
                tbl_df = consolidated_df[disp_cols].copy()
                tbl_df.columns = ["Asset Ticker", "Asset Name", "Asset Class", "Sector / Theme", "Geographic Region", "Position Value (€)", "Account / Source"]
                if is_hidden():
                    tbl_df["Position Value (€)"] = "€****"
                    tbl_df["Asset Name"] = "****"
                    tbl_df["Asset Ticker"] = "****"
                else:
                    tbl_df["Position Value (€)"] = tbl_df["Position Value (€)"].map(lambda x: f"€{x:,.2f}")
                st.dataframe(tbl_df, use_container_width=True, hide_index=True)


        # 3. Copy Portfolios Section
        if not copy_df.empty:
            with section_header("eToro Copied Traders"):
                render_copy_portfolios(copy_df, usd_to_eur)

            # 4. Direct Holdings Section
    with section_header("Direct Holdings"):
        if not direct_df.empty:
            t_data, t_market = st.tabs(["📊 Holdings Data", "📈 Market Quotes"])
        
            with t_data:
                df_disp = direct_df.copy()
                df_disp["average_open_rate"] = (df_disp["cost_basis_native"] / df_disp["quantity"]).fillna(0)
                df_disp["opened_at"] = pd.to_datetime(df_disp["updated_at"], errors='coerce').dt.strftime('%Y-%m-%d')
            
                # Formatting
                df_disp["P&L (€)"] = df_disp["unrealized_pnl_eur"]
                df_disp["P&L (%)"] = (df_disp["unrealized_pnl_eur"] / df_disp["cost_basis"] * 100).fillna(0)
            
                disp_cols = {
                    "ticker": "Ticker",
                    "name": "Asset Name",
                    "asset_type": "Asset Class",
                    "opened_at": "Last Updated",
                    "quantity": "Units",
                    "average_open_rate": "Avg Open Price",
                    "cost_basis": "Cost Basis (€)",
                    "latest_close": "Current Price",
                    "value_eur": "Current Value (€)",
                    "P&L (€)": "P&L (€)",
                    "P&L (%)": "P&L (%)"
                }
            
                out_df = df_disp.rename(columns=disp_cols)[list(disp_cols.values())]
            
                if is_hidden():
                    out_df["Asset Name"] = "****"
                    out_df["Ticker"] = "****"
                    for col in ["Units", "Avg Open Price", "Cost Basis (€)", "Current Price", "Current Value (€)", "P&L (€)", "P&L (%)"]:
                        out_df[col] = "****"
                else:
                    out_df["Units"] = out_df["Units"].map(lambda x: f"{x:,.4f}")
                    for col in ["Avg Open Price", "Current Price"]:
                        out_df[col] = out_df[col].map(lambda x: f"{x:,.2f}")
                    for col in ["Cost Basis (€)", "Current Value (€)", "P&L (€)"]:
                        out_df[col] = out_df[col].map(lambda x: f"€{x:,.2f}")
                    out_df["P&L (%)"] = out_df["P&L (%)"].map(lambda x: f"{x:+.1f}%")
            
                st.dataframe(out_df, use_container_width=True, hide_index=True)

            with t_market:
                st.caption("Live asset market streaming quotes from TradingView with your portfolio values and total returns:")

                perf_df = direct_df.copy()
                perf_df["unrealized_return_pct"] = (perf_df["unrealized_pnl_eur"] / perf_df["cost_basis"] * 100).fillna(0)

                disp_perf = perf_df[["ticker", "name", "latest_close", "value_eur", "unrealized_pnl_eur", "unrealized_return_pct"]].copy()
                disp_perf.columns = ["Ticker", "Asset Name", "Market Price", "Your Value (€)", "Total P&L (€)", "Total Growth (%)"]

                if is_hidden():
                    disp_perf["Asset Name"] = "****"
                    disp_perf["Ticker"] = "****"
                    disp_perf["Market Price"] = "****"
                    disp_perf["Your Value (€)"] = "€****"
                    disp_perf["Total P&L (€)"] = "€****"
                    disp_perf["Total Growth (%)"] = "****"
                else:
                    disp_perf["Market Price"] = disp_perf["Market Price"].map(lambda x: f"{x:,.2f}" if pd.notnull(x) else "—")
                    disp_perf["Your Value (€)"] = disp_perf["Your Value (€)"].map(lambda x: f"€{x:,.2f}")
                    disp_perf["Total P&L (€)"] = disp_perf["Total P&L (€)"].map(lambda x: f"{'+' if x >= 0 else ''}€{x:,.2f}")
                    disp_perf["Total Growth (%)"] = disp_perf["Total Growth (%)"].map(lambda x: f"{x:+.2f}%")

                st.dataframe(disp_perf, use_container_width=True, hide_index=True)

                st.markdown("<div style='margin-top: 10px; margin-bottom: 6px;'><b>TradingView Live Quotes Feed</b></div>", unsafe_allow_html=True)

                tv_symbols = []
                for t in direct_df["ticker"].unique():
                    tv_symbols.append({"name": t.split('.')[0] if '.' in t else t})
                
                theme = st.get_option("theme.base")
                tv_height = max(300, len(tv_symbols) * 45 + 90)
                blur_overlay = """<div style="position: absolute; top: 0; right: 0; width: 60%; height: 100%; backdrop-filter: blur(8px); z-index: 1000; pointer-events: none;"></div>""" if is_hidden() else ""
                tv_html = f"""
                <div style="position: relative; width: 100%; height: {tv_height}px;">
                    {blur_overlay}
                    <!-- TradingView Widget BEGIN -->
                    <div class="tradingview-widget-container">
                      <div class="tradingview-widget-container__widget"></div>
                      <script type="text/javascript" src="https://s3.tradingview.com/external-embedding/embed-widget-market-quotes.js" async>
                      {{
                      "width": "100%",
                      "height": {tv_height},
                      "symbolsGroups": [
                        {{
                          "name": "Live Market Prices",
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
                    <!-- TradingView Widget END -->
                </div>
                """
                st.components.v1.html(tv_html, height=tv_height)
        else:
            st.caption("No direct holdings found.")

        # 5. Allocation & Rebalancing Section
    with section_header("Allocation & Rebalancing"):

        # Fetch allocation profiles
        profiles = HoldingRepository.get_allocation_profiles(conn)
        if not profiles:
            st.caption("No allocation profiles configured.")
            return

        prof_map = {p["name"]: p for p in profiles}
        selected_name = st.selectbox(
            "Allocation Profile", options=list(prof_map.keys()), index=0)
        profile = prof_map[selected_name]

        # Fetch targets
        targets = HoldingRepository.get_allocation_targets(conn, profile["id"])

        # Calculate actual values per bucket based on profile dimension
        # 'asset_type', 'ticker', 'region', 'asset_class', etc.
        dimension = profile["dimension"]
        current_values: dict[str, float] = {}

        if not consolidated_df.empty:
            for _, row in consolidated_df.iterrows():
                b_key = str(row.get(dimension) or "other")
                current_values[b_key] = current_values.get(
                    b_key, 0.0) + float(row.get("value_eur", 0.0))

        if profile["include_cash"]:
            current_values["cash"] = AccountRepository.get_total_cash_balance(conn)

        if not current_values:
            st.warning("No value to balance for this profile.")
            return

        drift_data = calculate_drift(
            current_values, targets, drift_band_pct=profile["drift_band_pct"])

        col_chart, col_targets = st.columns([1, 1])
        with col_chart:
            render_chart(
                build_drift_bar_chart(drift_data, drift_band_pct=profile["drift_band_pct"]),
                use_container_width=True,
            )


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

        # 4. Dividend Tracking & Cash Flow Projections
    with section_header("Dividend & Cash Flow Projections"):
        div_data = calculate_dividend_projections(conn)

        d1, d2, d3 = st.columns(3)
        with d1:
            ann_str = "€****" if is_hidden() else f"€{div_data['projected_annual_dividends_eur']:,.2f}"
            kpi_card("Projected Annual Income", ann_str, subtext="Estimated forward dividends")
        with d2:
            yield_str = "****" if is_hidden() else f"{div_data['average_dividend_yield_pct']:.2f}%"
            kpi_card("Portfolio Yield", yield_str, subtext="Weighted average forward yield")
        with d3:
            mo_str = "€****" if is_hidden() else f"€{div_data['monthly_average_eur']:,.2f}"
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
                    text=m_dist_df["payout_eur"].map(lambda x: "€****" if is_hidden() else f"€{x:,.0f}"),
                    color_discrete_sequence=["#2DD4BF"],
                )
                dist_fig.update_layout(
                    margin=dict(t=35, l=10, r=10, b=10),
                    xaxis_title="Month",
                    yaxis_title="Projected Payout (€)",
                )
                if is_hidden():
                    dist_fig.update_traces(hovertemplate="Censored<extra></extra>")
                render_chart(dist_fig, use_container_width=True)

            with col_m_table:
                h_df = div_data["holdings_df"]
                if not h_df.empty:
                    disp_h = h_df[["ticker", "name", "value_eur", "yield_pct", "annual_dividend_eur"]].copy()
                    disp_h.columns = ["Ticker", "Asset", "Value (€)", "Est. Yield", "Annual Div (€)"]
                    if is_hidden():
                        disp_h["Value (€)"] = "€****"
                        disp_h["Est. Yield"] = "****"
                        disp_h["Annual Div (€)"] = "€****"
                        disp_h["Asset"] = "****"
                        disp_h["Ticker"] = "****"
                    else:
                        disp_h["Value (€)"] = disp_h["Value (€)"].map(lambda x: f"€{x:,.2f}")
                        disp_h["Est. Yield"] = disp_h["Est. Yield"].map(lambda x: f"{x:.1f}%")
                        disp_h["Annual Div (€)"] = disp_h["Annual Div (€)"].map(lambda x: f"€{x:,.2f}")
                    st.dataframe(disp_h, use_container_width=True, hide_index=True)
                else:
                    st.caption("No dividend-generating assets tracked.")


        # --- TAX LOSS HARVESTING ---
    with section_header("Tax-Loss Harvesting Assistant"):
        loss_df = holdings_df[holdings_df["unrealized_pnl_eur"] < -50].sort_values(by="unrealized_pnl_eur")
        if not loss_df.empty:
            disp_loss = loss_df[["ticker", "name", "value_eur", "unrealized_pnl_eur"]].copy()
            disp_loss.columns = ["Ticker", "Asset", "Value (€)", "Unrealized P&L (€)"]
            if is_hidden():
                disp_loss["Value (€)"] = "€****"
                disp_loss["Unrealized P&L (€)"] = "€****"
                disp_loss["Asset"] = "****"
                disp_loss["Ticker"] = "****"
            else:
                disp_loss["Value (€)"] = disp_loss["Value (€)"].map(lambda x: f"€{x:,.2f}")
                disp_loss["Unrealized P&L (€)"] = disp_loss["Unrealized P&L (€)"].map(lambda x: f"€{x:,.2f}")
            st.dataframe(disp_loss, hide_index=True, use_container_width=True)
        else:
            st.caption("No significant unrealized losses available for harvesting.")

        # --- FIRE & GOALS ---
    with section_header("FIRE & Financial Goals"):
        c_fire, c_goals = st.columns([1, 1])
    
        with c_fire:
            st.subheader("🔥 FIRE Trajectory")
            # Estimate expenses
            m_exp = TransactionRepository.get_average_monthly_expenses(conn)
            annual_exp = abs(m_exp) * 12
            fi_number = annual_exp * 25
        
            # Estimate savings
            m_sav = TransactionRepository.get_average_monthly_savings(conn)
            curr_nw = AccountRepository.get_latest_net_worth_snapshot(conn)
        
            c_sl1, c_sl2 = st.columns(2)
            with c_sl1:
                ret_rate = st.slider("Expected Annual Return (%)", 1.0, 15.0, 7.0, 0.5)
            with c_sl2:
                inf_rate = st.slider("Expected Inflation (%)", 0.0, 10.0, 2.0, 0.5)
            real_return = (ret_rate - inf_rate) / 100.0
        
            if is_hidden():
                st.metric("FI Number (25x)", "€****")
            else:
                st.metric("FI Number (25x)", f"€{fi_number:,.2f}")
            
            # Chart
            years = list(range(31))
            proj = []
            val = curr_nw
            for y in years:
                proj.append(val)
                val = val * (1 + real_return) + (m_sav * 12)
            
            fig_fire = px.line(x=years, y=proj, title="Net Worth Projection (Real)")
            fig_fire.add_hline(y=fi_number, line_dash="dash", annotation_text="FI Target", line_color="#2DD4BF")
            fig_fire.update_layout(xaxis_title="Years from Now", yaxis_title="Net Worth (€)", margin=dict(t=35, l=10, r=10, b=10))
            if is_hidden():
                fig_fire.update_traces(hovertemplate="Censored<extra></extra>")
            render_chart(fig_fire, use_container_width=True)

        with c_goals:
            st.subheader("🎯 Savings Goals")
        
            with st.expander("➕ Add New Goal", expanded=False):
                with st.form("new_goal_form"):
                    g_name = st.text_input("Goal Name")
                    g_target = st.number_input("Target Amount (€)", min_value=1.0, step=100.0)
                    cash_accounts = AccountRepository.get_cash_accounts(conn)
                    acc_options = {a.id: a.name for a in cash_accounts}
                    g_acc = st.selectbox("Linked Account", options=list(acc_options.keys()), format_func=lambda x: acc_options[x])
                
                    if st.form_submit_button("Save Goal"):
                        TransactionRepository.add_goal(conn, g_name, g_target, g_acc)
                        st.success("Goal added!")
                        st.rerun(scope="app")
                    
            goals = TransactionRepository.get_goals(conn)
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
                    st.write(f"**{g['name']}** — €{bal:,.0f} / €{tar:,.0f} ({pct*100:.1f}%) in {g['account_name'] or 'None'}")
                    st.progress(pct)

        conn.close()


