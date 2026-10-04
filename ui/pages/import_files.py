import pandas as pd
import streamlit as st

from config import DB_PATH
from connectors.file_import.detect import detect_format, parse_statement
from db import database
from services.sync_service import import_statement_content
from ui.components import section_header


def render():
    st.title("Import Statements")
    st.markdown("Drop your bank, card, or broker export files (CSV, TSV, MT940, CAMT.053 XML).")

    conn = database.connect(DB_PATH)
    accounts = conn.execute("SELECT id, name, institution, currency FROM accounts").fetchall()

    if not accounts:
        st.warning("Please configure at least one account in Settings before importing, or create one below.")
        with st.expander("Quick Create Account"):
            inst = st.selectbox("Institution", ["ABN AMRO", "Revolut", "eToro", "eToro Money", "Trade Republic"])
            name = st.text_input("Account Name", value=f"{inst} Main")
            curr = st.selectbox("Currency", ["EUR", "USD"])
            cls = st.selectbox("Asset Class", ["cash", "investment", "liability"])
            if st.button("Create Account"):
                acc_id = database.upsert_account(
                    conn,
                    {
                        "provider": "manual",
                        "institution": inst,
                        "name": name,
                        "currency": curr,
                        "asset_class": cls,
                        "external_id": f"manual_{inst.lower().replace(' ', '_')}_{name.lower().replace(' ', '_')}",
                    },
                )
                st.success("Account created!")
                st.rerun()
        conn.close()
        return

    acc_options = {a["id"]: f"{a['institution']} - {a['name']} ({a['currency']})" for a in accounts}
    selected_acc_id = st.selectbox(
        "Target Account",
        options=list(acc_options.keys()),
        format_func=lambda x: acc_options[x],
    )

    uploaded_files = st.file_uploader(
        "Upload statement files",
        type=["csv", "tsv", "tab", "xml", "txt", "sta", "940"],
        accept_multiple_files=True,
    )

    if uploaded_files:
        for file in uploaded_files:
            content = file.read().decode("utf-8", errors="replace")
            fmt, raw_txs = parse_statement(content)

            st.markdown(f"**File:** `{file.name}` | **Detected Format:** `{fmt.value}`")

            if not raw_txs:
                st.error("No valid transactions found in this file.")
                continue

            preview_data = [
                {
                    "Date": tx.booking_date.isoformat(),
                    "Amount": f"€{tx.amount_minor / 100.0:,.2f}",
                    "Description": tx.description,
                    "Counterparty": tx.counterparty_name or "-",
                }
                for tx in raw_txs[:5]
            ]
            st.dataframe(pd.DataFrame(preview_data), use_container_width=True, hide_index=True)

            if st.button(f"Import {len(raw_txs)} transactions from {file.name}", key=file.name):
                inserted, skipped, _ = import_statement_content(
                    conn,
                    content=content,
                    target_account_id=selected_acc_id,
                    enable_llm=False,
                )
                st.success(f"Import complete! {inserted} new transactions inserted, {skipped} duplicates skipped.")
                st.rerun()

    conn.close()
