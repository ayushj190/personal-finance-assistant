from datetime import date, datetime, timedelta
import html
import logging
import sqlite3
from typing import Any
import streamlit as st

from config import DB_PATH
from db import database
from db.repositories import AccountRepository, HoldingRepository, LiabilityRepository, TransactionRepository
from money import Money
from services.analytics import calculate_burn_and_runway, calculate_current_net_worth
from services.portfolio import get_consolidated_holdings_df
from ui import state
from ui.charts import (
    build_investments_market_carpet,
    open_sankey_fullscreen_dialog,
    render_cash_flow_sankey,
)
from ui.components import (
    empty_state,
    format_money,
    is_hidden,
    kpi_card,
    mask_if_hidden,
    render_section_header,
    section_header,
    status_badge,
)
from ui.logos import get_institution_logo_svg
from ui.page_panel import render_page_panel
from ui.theme import render_chart

logger = logging.getLogger(__name__)


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
    """Net cash flow (income minus expenses) over the trailing window.

    Savings and transfer activity is excluded, matching the spending page and
    `v_monthly_cashflow`, so a savings transfer does not drag the figure down. The
    window uses the local date, not SQLite's UTC `date('now')`.
    """
    window_start = (date.today() - timedelta(days=days)).isoformat()
    try:
        query = """
        SELECT COALESCE(SUM(t.amount_eur_minor), 0) AS net_flow_minor
        FROM transactions t
        LEFT JOIN categories c ON c.id = t.category_id
        WHERE t.is_internal_transfer = 0
          AND t.booking_date >= ?
          AND (c.kind IS NULL OR c.kind NOT IN ('savings', 'transfer'))
        """
        row = conn.execute(query, (window_start,)).fetchone()
        cents = int(row["net_flow_minor"] if row else 0)
        return Money.from_cents(cents).to_major()
    except Exception as e:
        logger.error("Error calculating monthly cash flow: %s", e, exc_info=True)
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
            base_bal_eur = Money.from_cents(row["balance_eur_minor"]).to_major()
            apy = acc.apy
            if apy and apy > 0:
                snap_date_str = str(row["snapshot_date"])[:10]
                try:
                    snap_date = datetime.strptime(snap_date_str, "%Y-%m-%d").date()
                    days = (today - snap_date).days
                    if days > 0:
                        daily_rate = (apy / 100.0) / 365.0  # pct
                        accrued = base_bal_eur * (daily_rate * days)
                        subtext = f"+€{accrued:,.2f} accrued ({apy}% APY)"
                except (ValueError, TypeError, OverflowError) as e:
                    logger.debug("Accrued calculation fallback for account %s: %s", acc.id, e)
        acc_subtexts[acc.id] = subtext
    return acc_subtexts


def _is_conn_open(conn: sqlite3.Connection | None) -> bool:
    if conn is None:
        return False
    try:
        conn.execute("SELECT 1")
        return True
    except sqlite3.Error:
        return False


@st.fragment
def _render_ticker_fragment(conn: sqlite3.Connection | None = None) -> None:
    """Render the native scrolling market tape for quoted active holdings."""
    should_close = False
    db_conn = conn
    if not _is_conn_open(db_conn):
        try:
            db_conn = database.connect(DB_PATH)
            should_close = True
        except Exception as e:
            logger.error("Error opening DB for ticker tape: %s", e, exc_info=True)
            return

    try:
        rows = HoldingRepository.get_latest_quotes(db_conn)
    except Exception as e:
        logger.error("Error loading ticker tape quotes: %s", e, exc_info=True)
        rows = []
    finally:
        if should_close and db_conn is not None:
            db_conn.close()

    items: list[str] = []
    seen: set[str] = set()
    for row in rows:
        ticker = (row["ticker"] or "").strip()
        price = float(row["close"] or 0.0)
        # eToro COPY: rows quote a mirror's NAV, not a traded price, and a name with
        # a space came from a statement import rather than a listed symbol.
        if not ticker or ticker in seen or price <= 0 or ":" in ticker or " " in ticker:
            continue
        seen.add(ticker)

        prior_close = float(row["prior_close"] or 0.0) or price
        change = price - prior_close
        change_pct = (change / prior_close) * 100.0
        direction = "up" if change >= 0 else "down"
        sign = "+" if change >= 0 else ""
        items.append(
            "<span class='ticker-tape__item'>"
            f"<span class='ticker-tape__symbol'>{html.escape(ticker)}</span>"
            f"<span class='ticker-tape__price'>{price:,.2f}</span>"
            f"<span class='ticker-tape__change ticker-tape__change--{direction}'>"
            f"{sign}{change:,.2f} ({sign}{change_pct:.2f}%)</span>"
            "</span>"
        )

    if not items:
        return

    # Even copy count: a half-width shift loops seamlessly and the track
    # always outruns the viewport, even with only a couple of holdings.
    copies = 2 * -(-6 // len(items))
    st.html(
        "<div class='ticker-tape'>"
        f"<div class='ticker-tape__track'>{''.join(items * copies)}</div>"
        "</div>"
    )


def _render_kpi_ribbon(
    conn: sqlite3.Connection,
    nw_data: dict[str, Any],
    liabilities: list[Any] | None = None,
) -> None:
    """Render the top KPI ribbon: Net Worth, Liquid Cash, Investments, Monthly Cash Flow, and Runway."""
    liquid_cash = Money.from_major(nw_data.get("liquid_cash", 0.0))
    invested = Money.from_major(nw_data.get("invested", 0.0))
    home_equity = Money.from_major(nw_data.get("home_equity", 0.0))
    net_worth = Money.from_major(nw_data.get("net_worth", 0.0))

    lib_row = liabilities[0] if liabilities else None
    nw_sub = (
        f"Assets minus liabilities (Home equity: {format_money(home_equity)})"
        if lib_row
        else "Assets minus liabilities"
    )

    monthly_cash_flow_val = _calculate_monthly_cash_flow(conn, days=30)
    monthly_cash_flow = Money.from_major(monthly_cash_flow_val)
    flow_sub = "Net cash flow (last 30 days)"

    monthly_expenses = TransactionRepository.get_monthly_expenses(conn)
    _burn, runway_months, runway_days = calculate_burn_and_runway(
        monthly_expenses, nw_data.get("liquid_cash", 0.0)
    )
    if runway_months >= 999:
        runway_txt, runway_sub = "Sustainable", "Net positive cash flow"
    elif runway_months >= 60:
        runway_txt, runway_sub = "5+ yrs", f"{int(runway_days):,} days buffer"
    else:
        runway_txt, runway_sub = f"{runway_months:.1f} mo", f"{int(runway_days):,} days buffer"

    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        kpi_card("Net Worth", format_money(net_worth), subtext=nw_sub)
    with c2:
        kpi_card("Liquid Cash", format_money(liquid_cash), subtext="Checking & cash reserves")
    with c3:
        kpi_card("Investments", format_money(invested), subtext="Securities & portfolio holdings")
    with c4:
        kpi_card("Monthly Cash Flow", format_money(monthly_cash_flow), subtext=flow_sub)
    with c5:
        kpi_card("Runway", runway_txt, subtext=runway_sub)


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
    if not _is_conn_open(db_conn):
        try:
            db_conn = database.connect(DB_PATH)
            should_close = True
        except Exception as e:
            logger.error("Error opening DB for accounts grid snapshots: %s", e, exc_info=True)
            db_conn = None

    if db_conn is not None:
        try:
            latest_snapshots = AccountRepository.get_all_latest_snapshots(db_conn)
        finally:
            if should_close:
                db_conn.close()

    acc_subtexts = _calculate_accrued_subtexts(accounts, latest_snapshots, today)
    currency_symbols = {"EUR": "€", "USD": "$", "TRY": "₺", "GBP": "£"}

    cash_count = len([a for a in accounts if getattr(a, "asset_class", "cash") == "cash"])
    invest_count = len([a for a in accounts if getattr(a, "asset_class", "cash") != "cash"])
    if cash_count and invest_count:
        badge_txt = f"{cash_count} cash • {invest_count} invest"
    elif invest_count:
        badge_txt = f"{invest_count} invest"
    else:
        badge_txt = f"{cash_count} cash"

    with section_header(
        "Accounts & Balances",
        "Real-time balances and connection statuses across connected institutions",
        badge=badge_txt,
    ):
        def _render_account_card(acc: Any, group_type: str) -> None:
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
            accent_cls = "account-accent-cash" if group_type == "cash" else "account-accent-investment"

            with st.container(border=True, key=f"account_card_{acc.id}"):
                c_header_info, c_header_cog = st.columns(
                    [0.85, 0.15], gap=0, vertical_alignment="center", wrap=False
                )
                with c_header_info:
                    header_html = (
                        f"<div class='account-card-marker {accent_cls}'>"
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
                                    width="stretch",
                                    key=f"dashboard_acc_{acc.id}_submit_btn",
                                ):
                                    val_min = Money.from_major(new_adj_bal).cents
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

        cash_accounts = [a for a in accounts if getattr(a, "asset_class", "cash") == "cash"]
        investment_accounts = [a for a in accounts if getattr(a, "asset_class", "cash") != "cash"]

        sorted_cash = sorted(
            cash_accounts,
            key=lambda a: (
                (getattr(a, "institution", "") or "").lower(),
                (getattr(a, "name", "") or "").lower(),
            ),
        )
        sorted_invest = sorted(
            investment_accounts,
            key=lambda a: (
                (getattr(a, "institution", "") or "").lower(),
                (getattr(a, "name", "") or "").lower(),
            ),
        )
        sorted_accounts = sorted_cash + sorted_invest

        cols_per_row = 4
        for i in range(0, len(sorted_accounts), cols_per_row):
            chunk = sorted_accounts[i : i + cols_per_row]
            cols = st.columns(cols_per_row, gap="small")
            for col, acc in zip(cols, chunk):
                group_type = "cash" if getattr(acc, "asset_class", "cash") == "cash" else "investment"
                with col:
                    _render_account_card(acc, group_type)


@st.dialog("Investments Exposure — Fullscreen Market Carpet", width="large")
def _investments_fullscreen_dialog() -> None:
    dlg_conn = database.connect(DB_PATH)
    try:
        df = get_consolidated_holdings_df(dlg_conn)
        if not df.empty:
            fig = build_investments_market_carpet(df, height=560)
            render_chart(fig, width="stretch", key="modal_market_carpet")
        else:
            st.info("No investment holdings tracked.")
    finally:
        dlg_conn.close()


@st.fragment
def _render_analytics_section(conn: sqlite3.Connection | None = None) -> None:
    """Render Expenses Sankey diagram and Investments Sector/Themes Market Carpet heatmap side-by-side."""
    should_close = False
    db_conn = conn
    if not _is_conn_open(db_conn):
        try:
            db_conn = database.connect(DB_PATH)
            should_close = True
        except Exception as e:
            logger.error("Error opening DB in dashboard analytics section: %s", e, exc_info=True)
            return

    try:
        today = date.today()
        today_iso = today.isoformat()
        prev_salary_date = TransactionRepository.get_latest_salary_date(db_conn, today_iso)
        if prev_salary_date:
            start_date = prev_salary_date
            try:
                dt = datetime.strptime(start_date, "%Y-%m-%d").date()
                period_sub = f"Since last salary ({dt.strftime('%d %b %Y')} – {today.strftime('%d %b %Y')})"
            except (ValueError, TypeError):
                period_sub = f"Since last salary ({start_date} – {today_iso})"
        else:
            start_date = today.replace(day=1).isoformat()
            period_sub = f"Month-to-date ({today.strftime('%B %Y')})"

        end_date = today_iso

        col_expenses, col_investments = st.columns(2, gap="medium")

        with col_expenses:
            with st.container(border=True, key="expenses_diagram_panel"):
                c_exp_head, c_exp_act = st.columns([0.88, 0.12], vertical_alignment="center")
                with c_exp_head:
                    render_section_header("Expenses", f"{period_sub} • Interactive flow")
                with c_exp_act:
                    if st.button("⛶", key="expand_expenses_flow_btn", help="Expand Expenses to Fullscreen"):
                        open_sankey_fullscreen_dialog(
                            start_date,
                            end_date,
                            drilldown_flow=state.get(state.K.DASHBOARD_SANKEY_DRILLDOWN, "Full Flow"),
                        )

                spend_df = TransactionRepository.get_recent_spending_df(
                    db_conn, start_date=start_date, end_date=end_date
                )
                if not spend_df.empty:
                    render_cash_flow_sankey(
                        db_conn,
                        key_prefix="dashboard_sankey",
                        start_date=start_date,
                        end_date=end_date,
                        height=360,
                    )
                else:
                    empty_state(
                        "No Recent Spending",
                        f"No expense transactions recorded since last salary ({period_sub}). Import your statements in the 'Import' page to view spending breakdowns.",
                        icon="💸",
                    )

        with col_investments:
            with st.container(border=True, key="portfolio_exposure_panel"):
                c_inv_head, c_inv_act = st.columns([0.88, 0.12], vertical_alignment="center")
                with c_inv_head:
                    render_section_header("Portfolio exposure", "Sector & themes breakdown • Market carpet heatmap")
                with c_inv_act:
                    if st.button("⛶", key="expand_invest_carpet_btn", help="Expand Portfolio Exposure to Fullscreen"):
                        _investments_fullscreen_dialog()

                consolidated_df = get_consolidated_holdings_df(db_conn)
                if not consolidated_df.empty:
                    carpet_fig = build_investments_market_carpet(consolidated_df, height=360)
                    render_chart(carpet_fig, width="stretch", key="dashboard_market_carpet")
                else:
                    empty_state(
                        "No Investment Holdings",
                        "No investment portfolio holdings found. Connect eToro or add broker holdings to view exposure.",
                        icon="📈",
                    )
    finally:
        if should_close:
            db_conn.close()


def render() -> None:
    """Primary dashboard entrypoint."""
    render_page_panel("dashboard")
    conn = database.connect(DB_PATH)
    try:
        # 1. Accounts check (AC-6)
        accounts = AccountRepository.get_active_accounts(conn)
        if not accounts:
            empty_state(
                "No Accounts Found",
                "Get started by importing your bank or brokerage statements in the 'Import' page, or connect an API in 'Settings'.",
                icon="🏦",
            )
            return

        # 0. Native scrolling market ticker tape (AC-3)
        _render_ticker_fragment()

        # 1. Compute current net worth balances
        nw_data = calculate_current_net_worth(conn)
        liabilities = LiabilityRepository.get_all_liabilities(conn)
        sync_logs = AccountRepository.get_recent_sync_logs(conn, limit=50)

        # 2. Standardized 4-KPI Ribbon (AC-1)
        _render_kpi_ribbon(conn, nw_data, liabilities)

        # 3. Expenses and Portfolio exposure panels (AC-2)
        _render_analytics_section()

        # 4. Accounts & Balances Grid (AC-4, AC-5)
        _render_accounts_grid(accounts, nw_data, sync_logs)

    finally:
        conn.close()
