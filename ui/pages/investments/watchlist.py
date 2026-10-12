import json
import pandas as pd
import streamlit as st

from ui.components import section_header
from ui import state
from ui.tickers import tradingview_symbol


def render_live_quotes_and_watchlist(
    direct_df: pd.DataFrame,
    consolidated_df: pd.DataFrame,
) -> None:
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
        is_min = bool(state.get(state.K.TV_WATCHLIST_MINIMIZED, False))

        c_tv_head, c_tv_act = st.columns([0.85, 0.15], vertical_alignment="center")
        with c_tv_head:
            section_header("Live Market Quotes & TradingView Watchlist", f"{len(all_tickers)} distinct active assets • Real-time market stream")
        with c_tv_act:
            btn_txt = "➕ Expand" if is_min else "➖ Minimize"
            if st.button(btn_txt, key="btn_toggle_tv_watchlist"):
                state.set(state.K.TV_WATCHLIST_MINIMIZED, not is_min)
                st.rerun()

        if not state.get(state.K.TV_WATCHLIST_MINIMIZED, False):
            tv_symbols = []
            for t in all_tickers[:30]:
                # AC-9: same exchange prefix mapping as the Dashboard ticker.
                sym = tradingview_symbol(t) or t
                tv_symbols.append({"name": sym, "displayName": t})

            theme = st.get_option("theme.base")
            tv_content_height = max(360, len(tv_symbols) * 44 + 80)
            # AC-10: market prices and symbols are public, so no privacy blur here.
            tv_html = f"""
            <div style="position: relative; width: 100%; height: 380px; max-height: 380px; overflow-y: auto; overflow-x: hidden; border-radius: 12px; border: 1px solid rgba(128,128,128,0.2); box-shadow: 0 4px 16px rgba(0,0,0,0.15);">
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
