import pandas as pd
import streamlit as st

from config import DB_PATH
from connectors.file_import.detect import (
    FileFormat,
    detect_statement_account_hint,
    parse_statement,
    parse_statement_balance,
    parse_statement_holdings,
)
from connectors.market_data_service import update_quotes
from db import database
from db.repositories import HoldingRepository
from money import Money
from services.sync_service import import_statement_content
from ui.dialogs import manual_account_dialog


def render():
    col_desc, col_btn = st.columns([0.78, 0.22], vertical_alignment="center")
    with col_desc:
        st.markdown(
            "Drop your bank, card, or broker export files (Trade Republic, ABN AMRO, Revolut, eToro, Türkiye İş Bankası, MT940, CAMT.053, PDF). The system automatically detects formats and matches target accounts."
        )
    with col_btn:
        if st.button("➕ Add Manual Account", key="import_add_manual_acc_btn", width="stretch"):
            manual_account_dialog()

    conn = database.connect(DB_PATH)

    def auto_resolve_accounts(conn, fmt: FileFormat) -> tuple[int, int]:
        # Maps format to (Institution, Cash_Ext_ID, Inv_Ext_ID)
        mapping = {
            FileFormat.ETORO_STATEMENT_CSV: ("eToro", "etoro_cash_eur", "etoro_trading_usd"),
            FileFormat.ETORO_MONEY_TSV: ("eToro Bank", "etoro_cash_eur", "etoro_cash_eur"),
            FileFormat.REVOLUT_CSV: ("Revolut", "revolut_eur", "revolut_eur"),
            FileFormat.ABN_AMRO_TAB: ("ABN AMRO", "abn_checking", "abn_checking"),
        }

        inst, cash_ext, inv_ext = mapping.get(
            fmt, ("Imported Bank", "imported_cash", "imported_inv"))

        # Resolve Cash Account
        cash_row = conn.execute(
            "SELECT id FROM accounts WHERE external_id = ?", (cash_ext,)).fetchone()
        if cash_row:
            cash_id = cash_row["id"]
        else:
            cash_id = database.upsert_account(conn, {
                "provider": "manual", "institution": inst, "external_id": cash_ext,
                "name": f"{inst} Cash", "currency": "EUR", "asset_class": "cash",
                "apy": 3.0 if inst == "Trade Republic" else None,
            })

        # Resolve Investment Account
        inv_row = conn.execute(
            "SELECT id FROM accounts WHERE external_id = ?", (inv_ext,)).fetchone()
        if inv_row:
            inv_id = inv_row["id"]
        else:
            inv_id = database.upsert_account(conn, {
                "provider": "manual", "institution": inst, "external_id": inv_ext,
                "name": f"{inst} Investment", "currency": "EUR", "asset_class": "investment"
            })

        return cash_id, inv_id

    all_accounts = conn.execute(
        "SELECT id, name, institution, iban, currency, asset_class FROM accounts WHERE is_active = 1 ORDER BY name ASC"
    ).fetchall()
    acc_dict = {a["id"]: dict(a) for a in all_accounts}
    acc_labels = {
        a["id"]: f"{a['name']} ({a['institution']}) • {a['currency']}"
        for a in all_accounts
    }

    uploaded_files = st.file_uploader(
        "Upload statement files",
        type=["csv", "tsv", "tab", "xml", "txt", "sta", "940", "pdf"],
        accept_multiple_files=True,
    )

    if uploaded_files:
        for file in uploaded_files:
            raw_bytes = file.read()
            fmt, raw_txs = parse_statement(raw_bytes)
            raw_holdings = parse_statement_holdings(raw_bytes)
            raw_balance = parse_statement_balance(raw_bytes)

            st.markdown(
                f"**File:** `{file.name}` | **Detected Format:** `{fmt.value}`")

            if not raw_txs and not raw_holdings and raw_balance is None:
                st.error(
                    "No valid transactions, holdings, or account balance found in this file.")
                continue

            inst_hint, iban_hint = detect_statement_account_hint(raw_bytes)
            default_acc_id = None
            if iban_hint:
                clean_hint = iban_hint.replace(" ", "").upper()
                for aid, a in acc_dict.items():
                    if a.get("iban") and a["iban"].replace(" ", "").upper() == clean_hint:
                        default_acc_id = aid
                        break
            if not default_acc_id and inst_hint:
                inst_lower = inst_hint.lower()
                for aid, a in acc_dict.items():
                    if inst_lower in (a.get("institution") or "").lower():
                        default_acc_id = aid
                        break
            if not default_acc_id:
                cash_fallback, _ = auto_resolve_accounts(conn, fmt)
                default_acc_id = cash_fallback

            if default_acc_id not in acc_dict:
                row = conn.execute(
                    "SELECT id, name, institution, iban, currency, asset_class FROM accounts WHERE id = ?",
                    (default_acc_id,),
                ).fetchone()
                if row:
                    acc_dict[default_acc_id] = dict(row)
                    acc_labels[default_acc_id] = f"{row['name']} ({row['institution']}) • {row['currency']}"

            acc_ids_list = list(acc_dict.keys())
            def_idx = acc_ids_list.index(default_acc_id) if default_acc_id in acc_ids_list else 0

            col_sel, _ = st.columns([1, 1])
            with col_sel:
                target_account_id = st.selectbox(
                    "Target Account",
                    options=acc_ids_list,
                    index=def_idx,
                    format_func=lambda aid: acc_labels.get(aid, str(aid)),
                    key=f"target_acc_sel_{file.name}",
                    help="Confirm or reassign the target account before importing.",
                )

            target_acc = acc_dict.get(target_account_id, {})
            target_curr = target_acc.get("currency", "EUR")

            final_balance_to_save = raw_balance
            if raw_balance is not None:
                maj_bal = Money.from_cents(raw_balance).to_major()
                st.info(
                    f"💰 **Detected Account Balance (Eindsaldo / Bakiye):** {target_curr} {maj_bal:,.2f}")
                adj_bal = st.number_input(
                    f"Confirm or adjust account balance ({target_curr})",
                    value=float(maj_bal),
                    step=50.0,
                    format="%.2f",
                    key=f"bal_input_{file.name}",
                )
                final_balance_to_save = Money.from_major(adj_bal).cents

            if raw_txs:
                st.caption(f"Found {len(raw_txs)} transactions:")
                preview_data = [
                    {
                        "Date": tx.booking_date.isoformat(),
                        "Amount": f"{tx.currency} {Money.from_cents(tx.amount_minor).to_major():,.2f}",
                        "Description": tx.description,
                        "Counterparty": tx.counterparty_name or "-",
                    }
                    for tx in raw_txs[:5]
                ]
                st.dataframe(pd.DataFrame(preview_data),
                             width="stretch", hide_index=True)

            if raw_holdings:
                st.caption(f"Found {len(raw_holdings)} investment positions:")
                h_preview = [
                    {
                        "Ticker / Name": h.ticker,
                        "Units": h.quantity,
                        "Cost Basis": f"{h.currency} {Money.from_cents(h.cost_basis_minor).to_major():,.2f}",
                        "ISIN": h.isin or "-",
                    }
                    for h in raw_holdings[:5]
                ]
                st.dataframe(pd.DataFrame(h_preview),
                             width="stretch", hide_index=True)

            if not raw_txs and not raw_holdings and final_balance_to_save is not None:
                save_maj = Money.from_cents(final_balance_to_save).to_major()
                btn_label = f"Update balance to {target_curr} {save_maj:,.2f} from {file.name}"
            else:
                btn_label = f"Import {len(raw_txs)} transactions"
                if raw_holdings:
                    btn_label += f" & {len(raw_holdings)} holdings"
                if final_balance_to_save is not None:
                    save_maj = Money.from_cents(final_balance_to_save).to_major()
                    btn_label += f" & set balance to {target_curr} {save_maj:,.2f}"
                btn_label += f" from {file.name}"

            if st.button(btn_label, key=file.name):
                msg_parts = []
                if raw_txs:
                    inserted, skipped, _ = import_statement_content(
                        conn,
                        content=raw_bytes,
                        target_account_id=target_account_id,
                        enable_llm=False,
                    )
                    msg_parts.append(
                        f"{inserted} new transactions inserted ({skipped} duplicates skipped)")

                if final_balance_to_save is not None:
                    database.upsert_snapshots(conn, [{
                        "account_id": target_account_id,
                        "snapshot_date": pd.Timestamp.now().date().isoformat(),
                        "balance_minor": final_balance_to_save,
                        "balance_eur_minor": final_balance_to_save
                    }])
                    save_maj = Money.from_cents(final_balance_to_save).to_major()
                    msg_parts.append(
                        f"Account balance updated to {target_curr} {save_maj:,.2f}")

                if raw_holdings:
                    _, inv_acc_id = auto_resolve_accounts(conn, fmt)
                    prepared_h = [
                        {
                            "account_id": inv_acc_id,
                            "ticker": h.ticker,
                            "isin": h.isin,
                            "name": h.name,
                            "asset_type": h.asset_type,
                            "region": h.region,
                            "sector": h.sector,
                            "quantity": h.quantity,
                            "cost_basis_minor": h.cost_basis_minor,
                            "currency": h.currency,
                            "updated_at": pd.Timestamp.now().isoformat(),
                        }
                        for h in raw_holdings
                    ]
                    rec_stats = HoldingRepository.reconcile_account_holdings(conn, inv_acc_id, prepared_h)
                    msg = f"{rec_stats['upserted']} holdings reconciled"
                    if rec_stats['closed'] > 0:
                        msg += f" ({rec_stats['closed']} closed)"
                    msg_parts.append(msg)
                    try:
                        tickers = [h.ticker for h in raw_holdings if h.ticker]
                        update_quotes(tickers, db_conn=conn)
                    except Exception:
                        pass

                st.success(f"Import complete! {', '.join(msg_parts)}.")
                st.rerun()

    conn.close()
