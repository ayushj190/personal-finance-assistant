from datetime import date, datetime
import json
from typing import Any
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from config import DATA_DIR, DB_PATH
from db import database
from db.repositories import AccountRepository, HoldingRepository, LiabilityRepository, TransactionRepository
from services.analytics import calculate_burn_and_runway, detect_recurring_charges, calculate_current_net_worth
from ui.charts import build_spending_donut
from ui.components import empty_state, format_money, is_hidden, kpi_card, section_header, status_badge
from ui.logos import get_institution_logo_svg
from ui.theme import render_chart
from connectors.etoro_service import EtoroService


@st.cache_data(ttl=300)
def fetch_cached_news():
    etoro = EtoroService()
    return etoro.fetch_news(limit=10), etoro.is_configured()

def get_account_status(acc: dict[str, Any], sync_logs: list[dict[str, Any]]) -> tuple[str, str]:
    """Derive status badge label and kind for any bank or investment account."""
    provider = acc.get("provider", "manual")
    inst = (acc.get("institution") or "").lower()

    matched_log = None
    for log in sync_logs:
        connector = (log.get("connector") or "").lower()
        if provider == "enable_banking":
            if "enable_banking" in connector and any(w in connector for w in inst.split() if len(w) > 2):
                matched_log = log
                break
            elif "enable_banking" in connector and not matched_log:
                matched_log = log
        elif provider == "etoro" and "etoro" in connector:
            matched_log = log
            break
        elif provider == "manual" and any(w in connector for w in inst.split() if len(w) > 2):
            matched_log = log
            break

    if matched_log:
        status = matched_log.get("status")
        if status == "needs_reauth":
            return ("🟡 Re-auth", "warning")
        elif status == "error":
            return ("🔴 Error", "danger")

    if provider == "manual":
        return ("📝 Manual", "neutral")
    return ("🟢 Connected", "success")


def clean_account_name(acc: dict[str, Any], all_accounts: list[dict[str, Any]]) -> str:
    """Return concise and unambiguous name for an account without duplicate clutter."""
    inst = (acc.get("institution") or "").strip()
    name = (acc.get("name") or "").strip()
    curr = acc.get("currency") or "EUR"
    asset_class = acc.get("asset_class") or "cash"

    if "etoro" in inst.lower():
        if asset_class == "investment" or "investment" in name.lower():
            return "eToro (Invest)"
        return "eToro (Cash)"

    same_inst = [
        a for a in all_accounts
        if (a.get("institution") or "").strip().lower() == inst.lower()
    ]

    if len(same_inst) > 1:
        return f"{inst} ({curr})"

    return inst


def render():
    conn = database.connect(DB_PATH)

    # 1. Accounts & Balances
    accounts = AccountRepository.get_active_accounts(conn)
    if not accounts:
        conn.close()
        empty_state(
            "No Accounts Found",
            "Get started by importing your bank or brokerage statements in the 'Import' page, or connect an API in 'Settings'.",
        )
        return

    # Convert to list of dicts for compatible template access
    accounts_dicts = [
        {
            "id": a.id,
            "provider": a.provider,
            "institution": a.institution,
            "name": a.name,
            "currency": a.currency,
            "asset_class": a.asset_class,
            "external_id": a.external_id,
            "iban": a.iban,
            "apy": a.apy,
            "is_active": a.is_active,
        }
        for a in accounts
    ]

    # 0. Scrolling Ticker Tape Widget (relocated from Investments page)
    all_tickers = []
    try:
        h_tickers = HoldingRepository.get_distinct_tickers(conn)
        cache_path = DATA_DIR / "etoro_mirrors_cache.json"
        mirrors_map = {}
        if cache_path.exists():
            try:
                with open(cache_path, "r", encoding="utf-8") as f:
                    mirrors_data = json.load(f)
                    if isinstance(mirrors_data, list):
                        mirrors_map = {m["ticker"]: m for m in mirrors_data if "ticker" in m}
            except Exception:
                pass

        for t in h_tickers:
            if not t:
                continue
            if str(t).startswith("COPY:"):
                mirror = mirrors_map.get(t, {})
                for pos in mirror.get("positions", []):
                    sym = pos.get("symbol")
                    if sym and not str(sym).startswith("ID_"):
                        all_tickers.append(sym)
            elif not str(t).startswith("ID_"):
                all_tickers.append(t)
    except Exception:
        pass

    deduped_tickers = list(dict.fromkeys(all_tickers))
    symbols = []
    for ticker in deduped_tickers:
        clean_ticker = ticker.split(".")[0] if isinstance(ticker, str) and "." in ticker else ticker
        symbols.append({"proName": clean_ticker, "description": ticker})

    if not symbols:
        symbols = [
            {"proName": "SPY", "description": "S&P 500"},
            {"proName": "QQQ", "description": "Nasdaq 100"},
            {"proName": "FX:EURUSD", "description": "EUR / USD"},
        ]

    theme = st.get_option("theme.base")
    tape_html = f"""
    <!-- TradingView Widget BEGIN -->
    <div class="tradingview-widget-container" style="margin-bottom: 8px;">
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

    # Fetch sync logs to derive status for all bank & investment accounts
    sync_logs = AccountRepository.get_recent_sync_logs(conn, limit=50)

    # Compute current balances
    nw_data = calculate_current_net_worth(conn)
    acc_balances = nw_data["acc_balances"]
    liquid_cash = nw_data["liquid_cash"]
    invested = nw_data["invested"]
    home_equity = nw_data["home_equity"]
    net_worth = nw_data["net_worth"]

    acc_subtexts: dict[int, str] = {}
    today = date.today()
    latest_snapshots = AccountRepository.get_all_latest_snapshots(conn)

    for acc in accounts:
        row = latest_snapshots.get(acc.id)
        subtext = ""
        if row:
            base_bal_eur = row["balance_eur_minor"] / 100.0
            apy = acc.apy
            if apy and apy > 0:
                snap_date_str = str(row["snapshot_date"])[:10]
                try:
                    snap_date = datetime.strptime(
                        snap_date_str, "%Y-%m-%d").date()
                    days = (today - snap_date).days
                    if days > 0:
                        daily_rate = (apy / 100.0) / 365.0
                        accrued = base_bal_eur * (daily_rate * days)
                        subtext = f"+€{accrued:,.2f} accrued ({apy}% APY)"
                except Exception:
                    pass
        acc_subtexts[acc.id] = subtext

    # Liability balance & Property Asset
    liabilities = LiabilityRepository.get_all_liabilities(conn)
    lib_row = liabilities[0] if liabilities else None

    # Monthly cashflow for runway calculation
    monthly_expenses = TransactionRepository.get_monthly_expenses(conn)
    burn_rate, runway_months, runway_days = calculate_burn_and_runway(
        monthly_expenses, liquid_cash)

    # Standardized 4-KPI Ribbon
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        nw_sub = f"Assets minus liabilities (Home equity: {format_money(home_equity)})" if lib_row else "Assets minus liabilities"
        kpi_card("Net Worth", format_money(net_worth), subtext=nw_sub)
    with c2:
        kpi_card("Liquid Cash", format_money(liquid_cash),
                 subtext="Checking & cash reserves")

    with c3:
        kpi_card("Investments", format_money(invested),
                 subtext="Securities & portfolio holdings")
    with c4:
        runway_txt = f"{runway_months:.1f} mo" if runway_months < 60 else "5+ yrs"
        kpi_card("Runway", runway_txt,
                 subtext=f"{int(runway_days)} days buffer")

    # Accounts & Balances Grid - Compact, authentic logos, top-right settings cog
    with section_header("Accounts & Balances",
                   "Real-time balances and connection statuses across connected institutions"):

        currency_symbols = {"EUR": "€", "USD": "$", "TRY": "₺", "GBP": "£"}

        COLS_PER_ROW = 4
        for i in range(0, len(accounts), COLS_PER_ROW):
            row_accounts = accounts[i:i + COLS_PER_ROW]
            cols = st.columns(COLS_PER_ROW)
            for idx, acc in enumerate(row_accounts):
                col = cols[idx]
                bal = acc_balances.get(acc.id, 0.0)
                sub = acc_subtexts.get(acc.id, "")
                curr = acc.currency or "EUR"
                sym = currency_symbols.get(curr, "€")
                badge_txt, badge_kind = get_account_status(
                    {"provider": acc.provider, "institution": acc.institution},
                    sync_logs,
                )
                disp_name = clean_account_name(
                    {"institution": acc.institution, "name": acc.name, "currency": acc.currency, "asset_class": acc.asset_class},
                    accounts_dicts,
                )
                logo_svg = get_institution_logo_svg(acc.institution or "", size=20)

                with col:
                    with st.container(border=True):
                        # Top Row: Authentic Vector Logo + Clean Bank Name + Status Dot & Settings Cog
                        c_header_info, c_header_cog = st.columns([0.88, 0.12], gap=0, vertical_alignment="center", wrap=False)
                        with c_header_info:
                            st.markdown(
                                f"""<div class='account-card-marker'>
                                    {logo_svg}
                                    <span class='account-card-name' title='{disp_name}'>{disp_name}</span>
                                    {status_badge(badge_txt, badge_kind)}
                                </div>""",
                                unsafe_allow_html=True,
                            )
                        with c_header_cog:
                            with st.popover("", icon=":material/settings:", help="Account Settings"):
                                st.markdown(f"**{acc.name}**")
                                st.write(f"**Institution:** {acc.institution}")
                                st.write(f"**Asset Class:** {(acc.asset_class or 'cash').title()}")
                                st.write(f"**Currency:** {curr}")
                                st.caption(f"Status: {badge_txt}")

                                if acc.asset_class == "cash":
                                    st.divider()
                                    with st.form(f"adjust_bal_dash_{acc.id}"):
                                        st.caption(f"Adjust balance ({sym})")
                                        new_adj_bal = st.number_input(
                                            f"New Balance ({sym})",
                                            value=float(bal),
                                            min_value=0.0,
                                            step=50.0,
                                            format="%.2f",
                                            key=f"dash_bal_in_{acc.id}",
                                        )
                                        if st.form_submit_button("Update Balance", type="primary", use_container_width=True):
                                            val_min = int(round(new_adj_bal * 100))
                                            database.upsert_snapshots(conn, [{
                                                "account_id": acc.id,
                                                "snapshot_date": today.isoformat(),
                                                "balance_minor": val_min,
                                                "balance_eur_minor": val_min,
                                            }])
                                            st.rerun()

                        # Balance and fixed Subtext Slot (guarantees identical standard card alignment)
                        val_display = "****" if is_hidden() else f"{bal:,.2f}"
                        if sub:
                            sub_content = f"<span style='color: #10B981; font-weight: 600;'>✨ {sub}</span>"
                        elif acc.apy:
                            sub_content = f"<span style='color: var(--text-muted); font-weight: 500;'>📈 APY: {acc.apy}%</span>"
                        else:
                            sub_content = "&nbsp;"

                        card_body_html = f"""<div class='account-card-body'>
                            <div class='account-balance-text'><span class='account-currency-symbol'>{sym}</span><span class='account-balance-number'>{val_display}</span></div>
                            <div class='account-subtext-slot'>{sub_content}</div>
                        </div>"""
                        st.markdown(card_body_html, unsafe_allow_html=True)

        # Lower Grid: Spending Donut + Recurring Bills
        col_left, col_right = st.columns([1, 1])

        with col_left:
            with section_header("Spending by Category", "Last 30 days expenses"):
                spend_df = TransactionRepository.get_recent_spending_df(conn, days=30)
                if not spend_df.empty:
                    drill_key = "donut_drilldown_dashboard"
                    if drill_key not in st.session_state:
                        st.session_state[drill_key] = None

                    if st.session_state[drill_key]:
                        if st.button("← Back to Categories"):
                            st.session_state[drill_key] = None
                            st.rerun()

                    fig = build_spending_donut(spend_df, drilldown_category=st.session_state[drill_key])
            
                    selection = render_chart(
                        fig, 
                        use_container_width=True, 
                        on_select="rerun", 
                        selection_mode="points"
                    )

                    if selection and hasattr(selection, "selection") and selection.selection.get("points"):
                        clicked_point = selection.selection["points"][0]
                        clicked_label = clicked_point.get("label") or clicked_point.get("x")
                        if isinstance(clicked_label, str):
                            clicked_label = clicked_label.replace("&amp;", "&")
                
                        # Only drill down if we are at the top level
                        if st.session_state[drill_key] is None and clicked_label:
                            st.session_state[drill_key] = clicked_label
                            st.rerun()
                    elif selection and isinstance(selection, dict) and selection.get("selection", {}).get("points"):
                        clicked_point = selection["selection"]["points"][0]
                        clicked_label = clicked_point.get("label") or clicked_point.get("x")
                        if isinstance(clicked_label, str):
                            clicked_label = clicked_label.replace("&amp;", "&")
                
                        if st.session_state[drill_key] is None and clicked_label:
                            st.session_state[drill_key] = clicked_label
                            st.rerun()
                else:
                    st.caption("No expense transactions found in the last 30 days.")

        with col_right:
            with section_header("Upcoming Recurring Bills",
                           "Detected automatically from transactions"):
                all_tx_rows = TransactionRepository.get_v_transactions(conn, limit=500)
                recurring = detect_recurring_charges(all_tx_rows)
                if recurring:
                    rec_df = pd.DataFrame(recurring[:10])[
                        ["merchant", "cadence", "amount_eur", "next_expected_date"]]
                    rec_df.columns = ["Merchant", "Cadence", "Amount", "Next Expected"]
                    if is_hidden():
                        rec_df["Amount"] = rec_df["Amount"].map(
                            lambda x: format_money(x))
                        amt_cfg = st.column_config.TextColumn("Amount", disabled=True)
                    else:
                        amt_cfg = st.column_config.NumberColumn(
                            "Amount", format="€%.2f", disabled=True)
                    st.dataframe(
                        rec_df,
                        use_container_width=True,
                        hide_index=True,
                        column_config={
                            "Merchant": st.column_config.TextColumn("Merchant", width="medium"),
                            "Amount": amt_cfg
                        }
                    )
                else:
                    st.caption("No recurring subscriptions detected yet.")

            # Market News (Moved to bottom)
    with section_header("Market News",
                   "Latest updates from eToro feed"):
        news, is_configured = fetch_cached_news()
    
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
                        text = item['text']
                        if len(text) > 200:
                            text = text[:200] + "..."
                        st.markdown(
                            f"**@{item['username']}** <span style='color: gray; font-size: 0.8em;'>• {item['created'][:10]}</span><br/>"
                            f"<span style='font-size: 0.9em;'>{text}</span>", 
                            unsafe_allow_html=True
                        )
                    st.divider()
        else:
            if not is_configured:
                st.info("Connect eToro in Settings to view market news.")
            else:
                st.info("No news available right now.")

        conn.close()
