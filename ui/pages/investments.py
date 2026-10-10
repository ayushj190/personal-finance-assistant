import pandas as pd
import streamlit as st

from config import DB_PATH
from db import database
from services.portfolio import allocate_contribution, calculate_drift, full_rebalance, rebalance_without_selling
from ui.charts import build_drift_bar_chart
from ui.components import format_money, is_hidden, kpi_card, section_header
from connectors.market_data_service import update_quotes, get_ticker_logo_url, enrich_ticker_metadata, classify_asset
import streamlit.components.v1 as components
import json

@st.fragment(run_every="5s")
def render_copy_portfolios(copy_df, usd_to_eur):
    from pathlib import Path
    cache_path = Path(__file__).resolve().parent.parent.parent / "data" / "etoro_mirrors_cache.json"
    meta_path = Path(__file__).resolve().parent.parent.parent / "data" / "ticker_metadata.json"
    mirrors_map = {}
    if cache_path.exists():
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                mirrors_data = json.load(f)
                mirrors_map = {m["ticker"]: m for m in mirrors_data}
        except Exception:
            pass
            
    meta_map = {}
    if meta_path.exists():
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                meta_map = json.load(f)
        except Exception:
            pass

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
    holdings_df = pd.read_sql_query("SELECT * FROM v_holdings", conn)

    if holdings_df.empty:
        conn.close()
        st.info(
            "No holdings found. Sync an investment connector or add holdings in Settings.")
        return

    # Update quotes for real-time prices
    direct_tickers = [t for t in holdings_df["ticker"].unique() if not t.startswith("COPY:") and not t.startswith("ID_")]
    if direct_tickers:
        update_quotes(direct_tickers, conn)
        # Re-fetch after update to get latest prices in v_holdings
        holdings_df = pd.read_sql_query("SELECT * FROM v_holdings", conn)
        
    # TradingView Ticker Tape Widget
    symbols = []
    for ticker in direct_tickers:
        clean_ticker = ticker.split(".")[0] if isinstance(ticker, str) and "." in ticker else ticker
        symbols.append({"proName": clean_ticker, "description": ticker})
        
    if not symbols:
        symbols = [{"proName": "SPY", "description": "S&P 500"}, {"proName": "QQQ", "description": "Nasdaq 100"}]
        
    theme = st.get_option("theme.base")
    tape_html = f"""
    <!-- TradingView Widget BEGIN -->
    <div class="tradingview-widget-container">
      <div class="tradingview-widget-container__widget"></div>
      <script type="text/javascript" src="https://s3.tradingview.com/external-embedding/embed-widget-ticker-tape.js" async>
      {{
      "symbols": {json.dumps(symbols)},
      "showSymbolLogo": true,
      "isTransparent": true,
      "displayMode": "adaptive",
      "colorTheme": "{'light' if theme == 'light' else 'dark'}",
      "locale": "en"
    }}
      </script>
    </div>
    <!-- TradingView Widget END -->
    """
    components.html(tape_html, height=44)

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

    # 2. Allocation & Drift Analysis
    section_header("Allocation & Rebalancing",
                   "Track drift from targets and generate buy/sell recommendations")

    # Build consolidated drill-down DataFrame
    import plotly.express as px
    from pathlib import Path
    
    cache_path = Path(__file__).resolve().parent.parent.parent / "data" / "etoro_mirrors_cache.json"
    meta_path = Path(__file__).resolve().parent.parent.parent / "data" / "ticker_metadata.json"
    mirrors_map = {}
    if cache_path.exists():
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                mirrors_map = {m["ticker"]: m for m in json.load(f)}
        except Exception:
            pass
    meta_map = {}
    if meta_path.exists():
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                meta_map = json.load(f)
        except Exception:
            pass

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
                    "display_label": f"{sym} ({p_name[:20]})" if p_name and p_name != sym else sym
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
                "display_label": f"{t} ({d_name[:20]})" if d_name and d_name != t else t
            })

    all_syms = [item["ticker"] for item in consolidated_items if not item["ticker"].startswith("ID_")]
    names_map = {item["ticker"]: item["name"] for item in consolidated_items}
    if all_syms:
        enrich_ticker_metadata(list(set(all_syms)), names_map=names_map)

    consolidated_df = pd.DataFrame(consolidated_items)

    # 3. True Exposure Visualizer & Breakdown Section
    section_header("True Exposure & Thematic Breakdown",
                   "Consolidated underlying exposure across Direct Holdings and Copy Portfolios")

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
        
        plot_df = consolidated_df.copy()
        if is_hidden():
            plot_df['display_label'] = [
                ("█" * min(8, max(4, len(str(row['display_label']))))) + ("\u200b" * i)
                for i, row in plot_df.iterrows()
            ]
            textinfo = "label"
            hovertemplate = "<b>%{label}</b><extra></extra>"
        else:
            textinfo = "label+value+percent parent"
            hovertemplate = "<b>%{label}</b><br>Value: €%{value:,.2f}<br>%{percentRoot:.1%} of Portfolio<extra></extra>"

        if view_mode == "By Sector & Theme":
            fig = px.treemap(
                plot_df,
                path=treemap_path,
                values='value_eur',
                color='sector',
                color_discrete_map=SECTOR_COLORS,
                title=chart_title
            )
        else:
            fig = px.treemap(
                plot_df,
                path=treemap_path,
                values='value_eur',
                color='value_eur',
                color_continuous_scale='Blues',
                title=chart_title
            )

        fig.update_traces(
            root_color="lightgrey",
            textinfo=textinfo,
            hovertemplate=hovertemplate,
            marker=dict(line=dict(color='black', width=1.5))
        )
        fig.update_layout(margin=dict(t=35, l=10, r=10, b=10), height=700) # Made it square/larger
        st.plotly_chart(fig, use_container_width=True)

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
        st.markdown("#### 📊 Thematic & Sector Exposure Breakdown")
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
            bar_fig.update_layout(showlegend=False, margin=dict(t=30, l=10, r=10, b=10), xaxis_title="Weight (%)", yaxis_title="")
            
            if is_hidden():
                bar_fig.update_traces(hovertemplate="Censored<extra></extra>")
            
            st.plotly_chart(bar_fig, use_container_width=True)

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
            tbl_df.columns = ["Ticker", "Name", "Type", "Theme / Sector", "Region", "Value (EUR)", "Source"]
            if is_hidden():
                tbl_df["Value (EUR)"] = "€****"
                tbl_df["Name"] = "****"
                tbl_df["Ticker"] = "****"
            else:
                tbl_df["Value (EUR)"] = tbl_df["Value (EUR)"].map(lambda x: f"€{x:,.2f}")
            st.dataframe(tbl_df, use_container_width=True, hide_index=True)

    # 1. Copy Portfolios Section
    if not copy_df.empty:
        section_header("eToro Copied Traders",
                       "CopyPortfolios and automated trader mirroring")
        render_copy_portfolios(copy_df, usd_to_eur)

    # 2. Direct Holdings Section
    section_header("Direct Holdings", "Stocks, ETFs, and assets held directly")
    if not direct_df.empty:
        # TradingView live market data widget
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

    # 4. Target Allocation & Drift Analysis Section
    section_header("Target Allocation & Drift",
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

    for _, row in consolidated_df.iterrows():
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

    # 3. Rebalance AI Integration
    st.subheader("Automated Rebalancing")
    st.info("💡 **Tip:** Use the AI Copilot chatbot to calculate rebalancing instructions. Just say: *\"Help me rebalance my portfolio for the selected profile.\"* or *\"I have €1000 to deposit, how should I allocate it based on my targets?\"*")

    conn.close()
