import json
from pathlib import Path
from typing import Any, Optional
import pandas as pd
import plotly.express as px
import streamlit as st

from config import DB_PATH
from connectors.market_data_service import classify_asset, enrich_ticker_metadata, update_quotes
from db import database
from db.repositories import AccountRepository, HoldingRepository, TransactionRepository
from services.dividend_service import calculate_dividend_projections
from services.portfolio import calculate_drift, get_consolidated_holdings_df
from ui.charts import ASSET_TYPE_COLORS, SECTOR_COLORS, build_drift_bar_chart
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

    # 2. Exposure Visualizer (AC-3: Donut chart and horizontal exposure bar)
    if not consolidated_df.empty:
        with section_header("Portfolio Allocation & Exposure"):
            col_donut, col_bar = st.columns([1, 1])
            total_portfolio_eur = consolidated_df["value_eur"].sum()

            with col_donut:
                # Group by Asset Class for clean allocation donut
                asset_summary = (
                    consolidated_df.groupby("asset_type_display")["value_eur"]
                    .sum()
                    .reset_index()
                )
                asset_summary.columns = ["Asset Class", "value_eur"]

                donut_fig = px.pie(
                    asset_summary,
                    names="Asset Class",
                    values="value_eur",
                    hole=0.55,
                    color="Asset Class",
                    color_discrete_map=ASSET_TYPE_COLORS,
                    title="Allocation by Asset Class",
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
                    showlegend=True,
                    margin=dict(t=40, l=10, r=10, b=10),
                    height=340,
                )
                render_chart(donut_fig, use_container_width=True)

            with col_bar:
                # Group by sector/theme for horizontal exposure bar
                sec_df = (
                    consolidated_df.groupby("sector")["value_eur"]
                    .sum()
                    .reset_index()
                )
                sec_df["weight_pct"] = (
                    (sec_df["value_eur"] / total_portfolio_eur * 100.0)
                    if total_portfolio_eur > 0
                    else 0.0
                )
                sec_df = sec_df.sort_values(by="weight_pct", ascending=True)

                bar_fig = px.bar(
                    sec_df,
                    x="weight_pct",
                    y="sector",
                    orientation="h",
                    text=sec_df["weight_pct"].map(
                        lambda x: "****%" if is_hidden() else f"{x:.1f}%"
                    ),
                    color="sector",
                    color_discrete_map=SECTOR_COLORS,
                    title="Sector & Thematic Exposure (%)",
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
                    height=340,
                    xaxis=dict(ticksuffix="%", automargin=True),
                    yaxis=dict(automargin=True),
                )
                render_chart(bar_fig, use_container_width=True)

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

            # AC-4: On-demand toggle prevents heavy external iframe embed unless requested
            show_tv = st.toggle(
                "Show external TradingView live quote stream",
                value=False,
                key="toggle_tv_quotes",
                help="Loads the external TradingView widget on demand.",
            )
            if show_tv:
                tv_symbols = [
                    {"name": t.split(".")[0] if "." in t else t}
                    for t in direct_df["ticker"].unique()
                ]
                theme = st.get_option("theme.base")
                tv_height = max(300, len(tv_symbols) * 45 + 90)
                blur_overlay = (
                    """<div style="position: absolute; top: 0; right: 0; width: 60%; height: 100%; backdrop-filter: blur(8px); z-index: 1000; pointer-events: none;"></div>"""
                    if is_hidden()
                    else ""
                )
                tv_html = f"""
                <div style="position: relative; width: 100%; height: {tv_height}px;">
                    {blur_overlay}
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
                </div>
                """
                st.components.v1.html(tv_html, height=tv_height)
        else:
            st.caption("No direct broker holdings found.")


@st.fragment
def _render_allocation_fragment(conn, consolidated_df: pd.DataFrame) -> None:
    # Fetch allocation profiles
    profiles = HoldingRepository.get_allocation_profiles(conn)
    if not profiles:
        st.info("No allocation profiles configured.")
        return

    prof_map = {p["name"]: p for p in profiles}
    selected_name = st.selectbox(
        "Allocation Profile",
        options=list(prof_map.keys()),
        index=0,
        key="investments_allocation_profile_select",
    )
    profile = prof_map[selected_name]

    # Fetch targets
    targets = HoldingRepository.get_allocation_targets(conn, profile["id"])

    # Calculate actual values per bucket
    dimension = profile["dimension"]
    current_values: dict[str, float] = {}

    if not consolidated_df.empty:
        for _, row in consolidated_df.iterrows():
            b_key = str(row.get(dimension) or "other")
            current_values[b_key] = current_values.get(
                b_key, 0.0
            ) + float(row.get("value_eur", 0.0))

    if profile["include_cash"]:
        current_values["cash"] = AccountRepository.get_total_cash_balance(conn)

    if not current_values:
        st.warning("No value to balance for this profile.")
        return

    drift_data = calculate_drift(
        current_values, targets, drift_band_pct=profile["drift_band_pct"]
    )

    col_chart, col_targets = st.columns([1, 1])
    with col_chart:
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


@st.fragment
def _render_income_fragment(conn, holdings_df: pd.DataFrame) -> None:
    # 1. Dividend Tracking & Cash Flow Projections
    with section_header("Dividend & Passive Income Forecast"):
        div_data = calculate_dividend_projections(conn)

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

    # 2. Tax-Loss Harvesting Assistant
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


@st.fragment
def _render_goals_fragment(conn) -> None:
    c_fire, c_goals = st.columns([1, 1])

    with c_fire:
        st.subheader("🔥 FIRE Trajectory")
        m_exp = TransactionRepository.get_average_monthly_expenses(conn)
        annual_exp = abs(m_exp) * 12
        fi_number = annual_exp * 25

        m_sav = TransactionRepository.get_average_monthly_savings(conn)
        curr_nw = AccountRepository.get_latest_net_worth_snapshot(conn)

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
        render_chart(fig_fire, use_container_width=True)

    with c_goals:
        st.subheader("🎯 Savings Goals")

        with st.expander("➕ Add New Goal", expanded=False):
            with st.form("new_goal_form_investments"):
                g_name = st.text_input("Goal Name")
                g_target = st.number_input(
                    "Target Amount (€)", min_value=1.0, step=100.0
                )
                cash_accounts = AccountRepository.get_cash_accounts(conn)
                acc_options = {a.id: a.name for a in cash_accounts}
                g_acc = st.selectbox(
                    "Linked Account",
                    options=list(acc_options.keys()),
                    format_func=lambda x: acc_options[x],
                )

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
                st.write(
                    f"**{g['name']}** — €{bal:,.0f} / €{tar:,.0f} ({pct*100:.1f}%) in {g['account_name'] or 'None'}"
                )
                st.progress(pct)


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
            )

        with t_alloc:
            _render_allocation_fragment(conn, consolidated_df)

        with t_inc:
            _render_income_fragment(conn, holdings_df)

        with t_goals:
            _render_goals_fragment(conn)

    finally:
        conn.close()
