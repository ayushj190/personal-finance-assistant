import pandas as pd
import streamlit as st

from config import DB_PATH
from connectors.file_import.detect import FileFormat, detect_format, parse_statement, parse_statement_holdings, parse_statement_balance
from connectors.market_data_service import update_quotes
from db import database
from services.sync_service import import_statement_content, process_and_save_transactions
from ui.components import section_header


def render():
    st.title("Import Statements")
    st.markdown("Drop your bank, card, or broker export files (Trade Republic, ABN AMRO, Revolut, eToro, MT940, CAMT.053 XML). The system will automatically detect the format and target account.")

    conn = database.connect(DB_PATH)
    
    def auto_resolve_accounts(conn, fmt: FileFormat) -> tuple[int, int]:
        # Maps format to (Institution, Cash_Ext_ID, Inv_Ext_ID)
        mapping = {
            FileFormat.TRADE_REPUBLIC_PDF: ("Trade Republic", "tr_cash_eur", "tr_portfolio_eur"),
            FileFormat.TRADE_REPUBLIC_CSV: ("Trade Republic", "tr_cash_eur", "tr_portfolio_eur"),
            FileFormat.ETORO_STATEMENT_CSV: ("eToro", "etoro_cash_eur", "etoro_trading_usd"),
            FileFormat.ETORO_MONEY_TSV: ("eToro Bank", "etoro_cash_eur", "etoro_cash_eur"),
            FileFormat.REVOLUT_CSV: ("Revolut", "revolut_eur", "revolut_eur"),
            FileFormat.ABN_AMRO_TAB: ("ABN AMRO", "abn_checking", "abn_checking"),
        }
        
        inst, cash_ext, inv_ext = mapping.get(fmt, ("Imported Bank", "imported_cash", "imported_inv"))
        
        # Resolve Cash Account
        cash_row = conn.execute("SELECT id FROM accounts WHERE external_id = ?", (cash_ext,)).fetchone()
        if cash_row:
            cash_id = cash_row["id"]
        else:
            cash_id = database.upsert_account(conn, {
                "provider": "manual", "institution": inst, "external_id": cash_ext,
                "name": f"{inst} Cash", "currency": "EUR", "asset_class": "cash"
            })
            
        # Resolve Investment Account
        inv_row = conn.execute("SELECT id FROM accounts WHERE external_id = ?", (inv_ext,)).fetchone()
        if inv_row:
            inv_id = inv_row["id"]
        else:
            inv_id = database.upsert_account(conn, {
                "provider": "manual", "institution": inst, "external_id": inv_ext,
                "name": f"{inst} Investment", "currency": "EUR", "asset_class": "investment"
            })
            
        return cash_id, inv_id

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

            st.markdown(f"**File:** `{file.name}` | **Detected Format:** `{fmt.value}`")

            if not raw_txs and not raw_holdings:
                st.error("No valid transactions or holdings found in this file.")
                continue

            if raw_txs:
                st.caption(f"Found {len(raw_txs)} transactions:")
                preview_data = [
                    {
                        "Date": tx.booking_date.isoformat(),
                        "Amount": f"{tx.currency} {tx.amount_minor / 100.0:,.2f}",
                        "Description": tx.description,
                        "Counterparty": tx.counterparty_name or "-",
                    }
                    for tx in raw_txs[:5]
                ]
                st.dataframe(pd.DataFrame(preview_data), use_container_width=True, hide_index=True)

            if raw_holdings:
                st.caption(f"Found {len(raw_holdings)} investment positions:")
                h_preview = [
                    {
                        "Ticker / Name": h.ticker,
                        "Units": h.quantity,
                        "Cost Basis": f"{h.currency} {h.cost_basis_minor / 100.0:,.2f}",
                        "ISIN": h.isin or "-",
                    }
                    for h in raw_holdings[:5]
                ]
                st.dataframe(pd.DataFrame(h_preview), use_container_width=True, hide_index=True)

            btn_label = f"Import {len(raw_txs)} transactions"
            if raw_holdings:
                btn_label += f" & {len(raw_holdings)} holdings"
            btn_label += f" from {file.name}"

            if st.button(btn_label, key=file.name):
                cash_acc_id, inv_acc_id = auto_resolve_accounts(conn, fmt)
                msg_parts = []
                if raw_txs:
                    if fmt == FileFormat.TRADE_REPUBLIC_PDF:
                        inserted, skipped = process_and_save_transactions(
                            conn, account_id=cash_acc_id, raw_txs=raw_txs, source="pdf", enable_llm_categorization=False
                        )
                    else:
                        content_str = raw_bytes.decode("utf-8", errors="replace")
                        inserted, skipped, _ = import_statement_content(
                            conn,
                            content=content_str,
                            target_account_id=cash_acc_id,
                            enable_llm=False,
                        )
                    msg_parts.append(f"{inserted} new transactions inserted ({skipped} duplicates skipped)")

                if raw_balance is not None:
                    database.upsert_snapshots(conn, [{
                        "account_id": cash_acc_id,
                        "snapshot_date": __import__('pandas').Timestamp.now().date().isoformat(),
                        "balance_minor": raw_balance,
                        "balance_eur_minor": raw_balance
                    }])
                    msg_parts.append(f"Account balance updated to {raw_balance / 100.0:,.2f}")

                if raw_holdings:

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
                    database.upsert_holdings(conn, prepared_h)
                    msg_parts.append(f"{len(raw_holdings)} holdings saved")
                    try:
                        tickers = [h.ticker for h in raw_holdings if h.ticker]
                        update_quotes(tickers, db_conn=conn)
                    except Exception:
                        pass

                st.success(f"Import complete! {', '.join(msg_parts)}.")
                st.rerun()

    conn.close()
