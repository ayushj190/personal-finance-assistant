from datetime import date, datetime
from typing import Any

from core.config import DB_PATH
from connectors.file_import.detect import (
    FileFormat,
    parse_statement,
    parse_statement_balance,
    parse_statement_holdings,
)
from connectors.market_data_service import update_quotes
from db import database
from core.money import Money
from services.sync_service import import_statement_content


def tool_parse_and_import_file(
    file_name: str,
    file_bytes: bytes,
    confirm_balance: float | None = None,
) -> dict[str, Any]:
    """Parse uploaded bank/broker statement (PDF, CSV, TAB, XML, MT940) and insert transactions and holdings into DB."""
    conn = database.connect(DB_PATH)
    try:
        fmt, raw_txs = parse_statement(file_bytes)
        raw_holdings = parse_statement_holdings(file_bytes)
        detected_balance = parse_statement_balance(file_bytes)

        if not raw_txs and not raw_holdings and detected_balance is None:
            return {
                "success": False,
                "message": f"Could not detect valid financial transactions, holdings, or balance in '{file_name}'. (Detected format: {fmt.value})",
            }

        mapping = {
            FileFormat.ETORO_STATEMENT_CSV: ("eToro", "etoro_cash_eur", "etoro_trading_usd"),
            FileFormat.ETORO_MONEY_TSV: ("eToro Bank", "etoro_cash_eur", "etoro_cash_eur"),
            FileFormat.REVOLUT_CSV: ("Revolut", "revolut_eur", "revolut_eur"),
            FileFormat.ABN_AMRO_TAB: ("ABN AMRO", "abn_checking", "abn_checking"),
        }
        inst, cash_ext, inv_ext = mapping.get(fmt, ("Imported Bank", "imported_cash", "imported_inv"))

        cash_row = conn.execute("SELECT id FROM accounts WHERE external_id = ?", (cash_ext,)).fetchone()
        if cash_row:
            cash_id = cash_row["id"]
        else:
            cash_id = database.upsert_account(
                conn,
                {
                    "provider": "manual",
                    "institution": inst,
                    "external_id": cash_ext,
                    "name": f"{inst} Cash",
                    "currency": "EUR",
                    "asset_class": "cash",
                    "apy": 3.0 if inst == "Trade Republic" else None,
                },
            )

        inv_row = conn.execute("SELECT id FROM accounts WHERE external_id = ?", (inv_ext,)).fetchone()
        if inv_row:
            inv_id = inv_row["id"]
        else:
            inv_id = database.upsert_account(
                conn,
                {
                    "provider": "manual",
                    "institution": inst,
                    "external_id": inv_ext,
                    "name": f"{inst} Investment",
                    "currency": "EUR",
                    "asset_class": "investment",
                },
            )

        details = []
        inserted, skipped = 0, 0
        if raw_txs:
            content_str = file_bytes.decode("utf-8", errors="replace")
            inserted, skipped, _ = import_statement_content(
                conn, content=content_str, target_account_id=cash_id, enable_llm=False
            )
            details.append(f"{inserted} transactions imported ({skipped} duplicates skipped)")

        final_bal = confirm_balance if confirm_balance is not None else (
            Money.from_cents(detected_balance).to_major() if detected_balance else None
        )
        if final_bal is not None:
            b_minor = Money.from_major(final_bal).cents
            database.upsert_snapshots(
                conn,
                [{
                    "account_id": cash_id,
                    "snapshot_date": date.today().isoformat(),
                    "balance_minor": b_minor,
                    "balance_eur_minor": b_minor,
                }],
            )
            details.append(f"Balance recorded: €{final_bal:,.2f}")

        if raw_holdings:
            prepared_h = [
                {
                    "account_id": inv_id,
                    "ticker": h.ticker,
                    "isin": h.isin,
                    "name": h.name,
                    "asset_type": h.asset_type,
                    "region": h.region,
                    "sector": h.sector,
                    "quantity": h.quantity,
                    "cost_basis_minor": h.cost_basis_minor,
                    "currency": h.currency,
                    "updated_at": datetime.now().isoformat(),
                }
                for h in raw_holdings
            ]
            database.upsert_holdings(conn, prepared_h)
            details.append(f"{len(raw_holdings)} investment positions saved")
            try:
                tickers = [h.ticker for h in raw_holdings if h.ticker]
                update_quotes(tickers, db_conn=conn)
            except Exception:
                pass

        return {
            "success": True,
            "format": fmt.value,
            "message": f"Successfully imported '{file_name}' ({fmt.value}): {', '.join(details)}.",
            "inserted_transactions": inserted,
            "skipped_transactions": skipped,
            "holdings_count": len(raw_holdings),
        }
    finally:
        conn.close()
