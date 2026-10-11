from datetime import date, datetime
import json
import sqlite3
from typing import Any
import streamlit as st
import streamlit.components.v1 as components

from config import DATA_DIR, DB_PATH
from db import database
from db.repositories import AccountRepository, HoldingRepository, LiabilityRepository, TransactionRepository
from services.analytics import calculate_current_net_worth
from ui.charts import render_cash_flow_sankey
from ui.components import empty_state, format_money, is_hidden, kpi_card, mask_if_hidden, section_header, status_badge
from ui.logos import get_institution_logo_svg
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


def _calculate_monthly_cash_flow(conn: sqlite3.Connection, days: int = 30) -> float:
    """Calculate net cash flow (income minus expenses) over specified trailing days."""
    try:
        query = f"""
        SELECT COALESCE(SUM(amount_eur_minor), 0) / 100.0 AS net_flow
        FROM transactions
        WHERE is_internal_transfer = 0
          AND booking_date >= date('now', '-{days} days')
        """
        row = conn.execute(query).fetchone()
        return float(row["net_flow"] if row else 0.0)
    except Exception:
        return 0.0


def _calculate_accrued_subtexts(
    accounts: list[Any], latest_snapshots: dict[int, Any], today: date
) -> dict[int, str]:
    """Calculate accrued interest subtext for accounts with an APY."""
    acc_subtexts: dict[int, str] = {}
    for acc in accounts:
        row = latest_snapshots.get(acc.id)
        subtext = ""
        if row:
            base_bal_eur = row["balance_eur_minor"] / 100.0
            apy = acc.apy
            if apy and apy > 0:
                snap_date_str = str(row["snapshot_date"])[:10]
                try:
                    snap_date = datetime.strptime(snap_date_str, "%Y-%m-%d").date()
                    days = (today - snap_date).days
                    if days > 0:
                        daily_rate = (apy / 100.0) / 365.0
                        accrued = base_bal_eur * (daily_rate * days)
                        subtext = f"+€{accrued:,.2f} accrued ({apy}% APY)"
                except Exception:
                    pass
        acc_subtexts[acc.id] = subtext
    return acc_subtexts


@st.fragment
def _render_ticker_fragment(conn: sqlite3.Connection | None = None) -> None:
    """Render TradingView scrolling ticker tape inside an isolated fragment."""
    should_close = False
    if conn is None:
        try:
            conn = database.connect(DB_PATH)
            should_close = True
        except Exception:
            return

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
    finally:
        if should_close:
            conn.close()

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


def _render_kpi_ribbon(
    conn: sqlite3.Connection,
    nw_data: dict[str, Any],
    liabilities: list[Any] | None = None,
) -> None:
    """Render top 4-KPI ribbon for Net Worth, Liquid Cash, Investments, and Monthly Cash Flow."""
    liquid_cash = nw_data.get("liquid_cash", 0.0)
    invested = nw_data.get("invested", 0.0)
    home_equity = nw_data.get("home_equity", 0.0)
    net_worth = nw_data.get("net_worth", 0.0)

    lib_row = liabilities[0] if liabilities else None
    nw_sub = (
        f"Assets minus liabilities (Home equity: {format_money(home_equity)})"
        if lib_row
        else "Assets minus liabilities"
    )

    monthly_cash_flow = _calculate_monthly_cash_flow(conn, days=30)
    flow_sub = "Net cash flow (last 30 days)"

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        kpi_card("Net Worth", format_money(net_worth), subtext=nw_sub)
    with c2:
        kpi_card("Liquid Cash", format_money(liquid_cash), subtext="Checking & cash reserves")
    with c3:
        kpi_card("Investments", format_money(invested), subtext="Securities & portfolio holdings")
    with c4:
        kpi_card("Monthly Cash Flow", format_money(monthly_cash_flow), subtext=flow_sub)


@st.fragment
def _render_accounts_grid(
    accounts: list[Any],
    nw_data: dict[str, Any],
    sync_logs: list[dict[str, Any]] | None = None,
    conn: sqlite3.Connection | None = None,
) -> None:
    """Render tokenized accounts grid with namespaced keys and popover adjustment forms."""
    if not accounts:
        return

    if sync_logs is None:
        sync_logs = []

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

    acc_balances = nw_data.get("acc_balances", {})
    today = date.today()

    latest_snapshots: dict[int, Any] = {}
    should_close = False
    db_conn = conn
    if db_conn is None:
        try:
            db_conn = database.connect(DB_PATH)
            should_close = True
        except Exception:
            db_conn = None

    if db_conn is not None:
        try:
            latest_snapshots = AccountRepository.get_all_latest_snapshots(db_conn)
        finally:
            if should_close:
                db_conn.close()

    acc_subtexts = _calculate_accrued_subtexts(accounts, latest_snapshots, today)
    currency_symbols = {"EUR": "€", "USD": "$", "TRY": "₺", "GBP": "£"}

    with section_header(
        "Accounts & Balances",
        "Real-time balances and connection statuses across connected institutions",
    ):
        COLS_PER_ROW = 4
        for i in range(0, len(accounts), COLS_PER_ROW):
            row_accounts = accounts[i : i + COLS_PER_ROW]
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
                    {
                        "institution": acc.institution,
                        "name": acc.name,
                        "currency": acc.currency,
                        "asset_class": acc.asset_class,
                    },
                    accounts_dicts,
                )
                logo_svg = get_institution_logo_svg(acc.institution or "", size=20)

                with col:
                    with st.container(border=True, key=f"account_card_{acc.id}"):
                        # Top Row: Vector Logo + Account Name (top-left) and Settings Popover (top-right)
                        c_header_info, c_header_cog = st.columns(
                            [0.85, 0.15], gap=0, vertical_alignment="center", wrap=False
                        )
                        with c_header_info:
                            header_html = (
                                f"<div class='account-card-marker'>"
                                f"{logo_svg}"
                                f"<span class='account-card-name' title='{disp_name}'>{disp_name}</span>"
                                f"</div>"
                            )
                            st.markdown(header_html, unsafe_allow_html=True)
                        with c_header_cog:
                            with st.popover(
                                "",
                                icon=":material/settings:",
                                help="Account Settings",
                                key=f"dashboard_acc_{acc.id}_popover",
                            ):
                                st.markdown(f"**{acc.name}**")
                                st.write(f"**Institution:** {acc.institution}")
                                st.write(f"**Asset Class:** {(acc.asset_class or 'cash').title()}")
                                st.write(f"**Currency:** {curr}")
                                st.caption(f"Status: {badge_txt}")

                                if acc.asset_class == "cash":
                                    st.divider()
                                    with st.form(f"dashboard_acc_{acc.id}_adjust_form"):
                                        st.caption(f"Adjust balance ({sym})")
                                        new_adj_bal = st.number_input(
                                            f"New Balance ({sym})",
                                            value=float(bal),
                                            min_value=0.0,
                                            step=50.0,
                                            format="%.2f",
                                            key=f"dashboard_acc_{acc.id}_bal_in",
                                        )
                                        if st.form_submit_button(
                                            "Update Balance",
                                            type="primary",
                                            use_container_width=True,
                                            key=f"dashboard_acc_{acc.id}_submit_btn",
                                        ):
                                            val_min = int(round(new_adj_bal * 100))
                                            save_conn = database.connect(DB_PATH)
                                            try:
                                                database.upsert_snapshots(
                                                    save_conn,
                                                    [
                                                        {
                                                            "account_id": acc.id,
                                                            "snapshot_date": today.isoformat(),
                                                            "balance_minor": val_min,
                                                            "balance_eur_minor": val_min,
                                                        }
                                                    ],
                                                )
                                            finally:
                                                save_conn.close()
                                            st.rerun(scope="app")

                        # Bottom Row: Currency Symbol + Balance + APY/Details (bottom-left) and Status Dot (bottom-right)
                        val_display = "****" if is_hidden() else f"{bal:,.2f}"
                        details_html = ""
                        if sub:
                            masked_sub = mask_if_hidden(sub) if is_hidden() else sub
                            details_html = f"<span class='account-card-details details-accrued' title='{masked_sub}'>✨ {masked_sub}</span>"
                        elif acc.apy:
                            details_html = f"<span class='account-card-details details-apy' title='{acc.apy}% APY'>📈 {acc.apy}% APY</span>"

                        card_bottom_html = (
                            f"<div class='account-card-bottom'>"
                            f"<div class='account-card-amount-group'>"
                            f"<span class='account-currency-symbol'>{sym}</span>"
                            f"<span class='account-balance-number'>{val_display}</span>"
                            f"{details_html}"
                            f"</div>"
                            f"<div class='account-card-status-slot'>"
                            f"{status_badge(badge_txt, badge_kind)}"
                            f"</div>"
                            f"</div>"
                        )
                        st.markdown(card_bottom_html, unsafe_allow_html=True)


@st.fragment
def _render_analytics_section(conn: sqlite3.Connection | None = None) -> None:
    """Render cash flow Sankey diagram with interactive drill-down inside an isolated fragment."""
    should_close = False
    db_conn = conn
    if db_conn is None:
        try:
            db_conn = database.connect(DB_PATH)
            should_close = True
        except Exception:
            return

    try:
        today = date.today()
        start_date = today.replace(day=1).isoformat()
        end_date = today.isoformat()
        month_label = today.strftime("%B %Y")

        with section_header(
            "Cash Flow Topology",
            f"Month-to-date cash flows ({month_label}) • Click any node or link in the diagram to filter",
        ):
            spend_df = TransactionRepository.get_recent_spending_df(
                db_conn, start_date=start_date, end_date=end_date
            )
            if not spend_df.empty:
                render_cash_flow_sankey(
                    db_conn,
                    key_prefix="dashboard_sankey",
                    start_date=start_date,
                    end_date=end_date,
                )
            else:
                empty_state(
                    "No Recent Spending",
                    f"No expense transactions recorded month-to-date ({month_label}). Import your statements in the 'Import' page to view spending breakdowns.",
                )
    finally:
        if should_close:
            db_conn.close()


@st.fragment
def _render_market_news_fragment() -> None:
    """Render cached market news inside an isolated fragment."""
    with section_header("Market News", "Latest updates from eToro feed"):
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
                        text = item["text"]
                        if len(text) > 200:
                            text = text[:200] + "..."
                        st.markdown(
                            f"**@{item['username']}** <span style='color: gray; font-size: 0.8em;'>• {item['created'][:10]}</span><br/>"
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
    """Primary dashboard entrypoint."""
    conn = database.connect(DB_PATH)
    try:
        # 1. Accounts check (AC-6)
        accounts = AccountRepository.get_active_accounts(conn)
        if not accounts:
            empty_state(
                "No Accounts Found",
                "Get started by importing your bank or brokerage statements in the 'Import' page, or connect an API in 'Settings'.",
            )
            return

        # 0. Scrolling Ticker Tape Widget (AC-3)
        _render_ticker_fragment(conn)

        # 1. Compute current net worth balances
        nw_data = calculate_current_net_worth(conn)
        liabilities = LiabilityRepository.get_all_liabilities(conn)
        sync_logs = AccountRepository.get_recent_sync_logs(conn, limit=50)

        # 2. Standardized 4-KPI Ribbon (AC-1)
        _render_kpi_ribbon(conn, nw_data, liabilities)

        # 3. Accounts & Balances Grid (AC-4, AC-5)
        _render_accounts_grid(accounts, nw_data, sync_logs, conn)

        # 4. Lower Grid: Spending Donut + Recurring Bills (AC-2, AC-6)
        _render_analytics_section(conn)

        # 5. Market News (AC-3)
        _render_market_news_fragment()

    finally:
        conn.close()
