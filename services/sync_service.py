from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
import sqlite3
from typing import Any

from config import DB_PATH
from connectors.base import RawAccount, RawHolding, RawTransaction
from connectors.file_import.detect import FileFormat, parse_statement
from connectors.market_data_service import get_latest_fx_to_eur
from db import database
from services.categorization import categorize_transactions
from services.normalization import clean_merchant, dedup_hash, detect_internal_transfer


def process_and_save_transactions(
    conn: sqlite3.Connection,
    account_id: int,
    raw_txs: list[RawTransaction],
    source: str = "csv",
    enable_llm_categorization: bool = False,
) -> tuple[int, int]:
    if not raw_txs:
        return 0, 0

    own_ibans = database.get_own_ibans(conn)
    acc_row = conn.execute("SELECT currency FROM accounts WHERE id = ?", (account_id,)).fetchone()
    acc_curr = acc_row["currency"] if acc_row else "EUR"
    fx_rate = get_latest_fx_to_eur(acc_curr, conn)

    # Dedup occurrence index tracking within batch
    batch_counts: dict[str, int] = {}
    prepared: list[dict[str, Any]] = []

    for tx in raw_txs:
        date_str = tx.booking_date.isoformat()
        norm_merchant = clean_merchant(tx.description)
        is_transfer = detect_internal_transfer(
            description=tx.description,
            counterparty_name=tx.counterparty_name,
            counterparty_iban=tx.counterparty_iban,
            own_ibans=own_ibans,
        )

        tuple_key = f"{date_str}|{tx.amount_minor}|{tx.currency}|{norm_merchant}"
        idx = batch_counts.get(tuple_key, 0)
        batch_counts[tuple_key] = idx + 1

        tx_hash = dedup_hash(
            booking_date=date_str,
            amount_minor=tx.amount_minor,
            currency=tx.currency,
            description=tx.description,
            occurrence_idx=idx,
            external_ref=tx.external_ref,
        )

        amt_eur_minor = int(round(tx.amount_minor * fx_rate))

        prepared.append(
            {
                "account_id": account_id,
                "dedup_hash": tx_hash,
                "external_ref": tx.external_ref,
                "booking_date": date_str,
                "value_date": tx.value_date.isoformat() if tx.value_date else None,
                "amount_minor": tx.amount_minor,
                "currency": tx.currency,
                "amount_eur_minor": amt_eur_minor,
                "description_raw": tx.description,
                "counterparty_name": tx.counterparty_name,
                "counterparty_iban": tx.counterparty_iban,
                "merchant_normalized": norm_merchant,
                "mcc": tx.mcc,
                "is_internal_transfer": 1 if is_transfer else 0,
                "source": source,
                "category_id": None,
                "category_source": None,
            }
        )

    # Categorize
    categorized = categorize_transactions(conn, prepared, enable_llm=enable_llm_categorization)
    inserted = database.upsert_transactions(conn, categorized)
    skipped = len(categorized) - inserted
    return inserted, skipped


def import_statement_content(
    conn: sqlite3.Connection,
    content: str,
    target_account_id: int,
    source_name: str = "csv",
    enable_llm: bool = False,
) -> tuple[int, int, str]:
    fmt, raw_txs = parse_statement(content)
    if not raw_txs:
        return 0, 0, str(fmt.value)

    source_type = "csv"
    if fmt == FileFormat.MT940:
        source_type = "mt940"
    elif fmt == FileFormat.CAMT053:
        source_type = "camt053"

    inserted, skipped = process_and_save_transactions(
        conn,
        account_id=target_account_id,
        raw_txs=raw_txs,
        source=source_type,
        enable_llm_categorization=enable_llm,
    )

    # Record sync log
    with conn:
        conn.execute(
            """
            INSERT INTO sync_log (connector, started_at, finished_at, status, inserted, message)
            VALUES (?, datetime('now'), datetime('now'), 'ok', ?, ?)
            """,
            (f"import_{fmt.value}", inserted, f"Imported {inserted} rows, skipped {skipped}"),
        )

    return inserted, skipped, str(fmt.value)


def sync_all(conn: sqlite3.Connection, enable_llm: bool = False) -> dict[str, Any]:
    """Orchestrates sync across all configured connectors, quotes, and records sync_log."""
    from datetime import timedelta
    from connectors.base import NeedsReauth
    from connectors.enable_banking_service import EnableBankingService
    from connectors.etoro_service import EtoroService
    from connectors.trade_republic_service import TradeRepublicService
    from connectors.market_data_service import update_quotes
    from services import secrets_vault

    results: dict[str, Any] = {"connectors": {}, "total_inserted": 0, "quotes_updated": False}

    # 1. Open Banking (Enable Banking) per configured institution/session
    eb = EnableBankingService()
    if eb.is_configured():
        # Check all sessions stored in vault or default session
        stored_sessions = []
        for key in ["eb_session_id", "eb_session_abn_amro", "eb_session_revolut", "eb_session_ing", "eb_session_rabobank"]:
            if secrets_vault.get(key):
                stored_sessions.append((key, EnableBankingService(session_vault_key=key)))

        if not stored_sessions and secrets_vault.get("eb_session_id"):
            stored_sessions.append(("eb_session_id", eb))

        for session_key, eb_inst in stored_sessions:
            inst_label = session_key.replace("eb_session_", "").replace("_id", "")
            started = datetime.now().isoformat()
            try:
                accs = eb_inst.fetch_accounts()
                tot_inserted = 0
                for acc in accs:
                    acc_id = database.upsert_account(
                        conn,
                        {
                            "provider": "enable_banking",
                            "institution": acc.institution,
                            "external_id": acc.external_id,
                            "name": acc.name,
                            "currency": acc.currency,
                            "asset_class": acc.asset_class,
                            "iban": acc.iban,
                        },
                    )
                    # Snapshot balance
                    if acc.balance_minor is not None:
                        fx = get_latest_fx_to_eur(acc.currency, conn)
                        database.upsert_snapshots(
                            conn,
                            [
                                {
                                    "account_id": acc_id,
                                    "snapshot_date": date.today().isoformat(),
                                    "balance_minor": acc.balance_minor,
                                    "balance_eur_minor": int(round(acc.balance_minor * fx)),
                                }
                            ],
                        )

                    # Incremental transactions: max date - 7 days
                    max_dt_row = conn.execute(
                        "SELECT MAX(booking_date) AS m FROM transactions WHERE account_id = ?", (acc_id,)
                    ).fetchone()
                    if max_dt_row and max_dt_row["m"]:
                        since_dt = datetime.strptime(max_dt_row["m"][:10], "%Y-%m-%d").date() - timedelta(days=7)
                    else:
                        since_dt = date.today() - timedelta(days=90)

                    txs = eb_inst.fetch_transactions(since=since_dt)
                    ins, _ = process_and_save_transactions(
                        conn, account_id=acc_id, raw_txs=txs, source="api", enable_llm_categorization=enable_llm
                    )
                    tot_inserted += ins

                with conn:
                    conn.execute(
                        "INSERT INTO sync_log (connector, started_at, finished_at, status, inserted, message) VALUES (?, ?, datetime('now'), 'ok', ?, ?)",
                        (f"enable_banking_{inst_label}", started, tot_inserted, f"Synced {len(accs)} accounts, {tot_inserted} txs"),
                    )
                results["connectors"][f"open_banking_{inst_label}"] = {"status": "ok", "inserted": tot_inserted}
                results["total_inserted"] += tot_inserted
            except NeedsReauth as e:
                with conn:
                    conn.execute(
                        "INSERT INTO sync_log (connector, started_at, finished_at, status, inserted, message) VALUES (?, ?, datetime('now'), 'needs_reauth', 0, ?)",
                        (f"enable_banking_{inst_label}", started, str(e)),
                    )
                results["connectors"][f"open_banking_{inst_label}"] = {"status": "needs_reauth", "error": str(e)}
            except Exception as e:
                with conn:
                    conn.execute(
                        "INSERT INTO sync_log (connector, started_at, finished_at, status, inserted, message) VALUES (?, ?, datetime('now'), 'error', 0, ?)",
                        (f"enable_banking_{inst_label}", started, str(e)),
                    )
                results["connectors"][f"open_banking_{inst_label}"] = {"status": "error", "error": str(e)}

    # 2. eToro
    etoro = EtoroService()
    if etoro.is_configured():
        started = datetime.now().isoformat()
        try:
            accs = etoro.fetch_accounts()
            holdings = etoro.fetch_holdings()
            for acc in accs:
                acc_id = database.upsert_account(
                    conn,
                    {
                        "provider": "etoro",
                        "institution": acc.institution,
                        "external_id": acc.external_id,
                        "name": acc.name,
                        "currency": acc.currency,
                        "asset_class": acc.asset_class,
                    },
                )
                if acc.balance_minor is not None:
                    fx = get_latest_fx_to_eur(acc.currency, conn)
                    database.upsert_snapshots(
                        conn,
                        [
                            {
                                "account_id": acc_id,
                                "snapshot_date": date.today().isoformat(),
                                "balance_minor": acc.balance_minor,
                                "balance_eur_minor": int(round(acc.balance_minor * fx)),
                            }
                        ],
                    )

            if holdings:
                db_holdings = []
                acc_row = database.get_account_by_provider_ext_id(conn, "etoro", "etoro_trading_usd")
                if acc_row:
                    acc_id = acc_row["id"]
                    for h in holdings:
                        db_holdings.append(
                            {
                                "account_id": acc_id,
                                "ticker": h.ticker,
                                "isin": h.isin,
                                "name": h.name,
                                "asset_type": h.asset_type,
                                "region": "US" if not h.ticker.endswith(".DE") else "Europe",
                                "sector": "Diversified",
                                "quantity": h.quantity,
                                "cost_basis_minor": h.cost_basis_minor,
                                "currency": h.currency,
                                "updated_at": date.today().isoformat(),
                            }
                        )
                    database.upsert_holdings(conn, db_holdings)

            with conn:
                conn.execute(
                    "INSERT INTO sync_log (connector, started_at, finished_at, status, inserted, message) VALUES ('etoro', ?, datetime('now'), 'ok', 0, ?)",
                    (started, f"Synced {len(holdings)} holdings"),
                )
            results["connectors"]["etoro"] = {"status": "ok", "holdings": len(holdings)}
        except NeedsReauth as e:
            with conn:
                conn.execute(
                    "INSERT INTO sync_log (connector, started_at, finished_at, status, inserted, message) VALUES ('etoro', ?, datetime('now'), 'needs_reauth', 0, ?)",
                    (started, str(e)),
                )
            results["connectors"]["etoro"] = {"status": "needs_reauth", "error": str(e)}
        except Exception as e:
            with conn:
                conn.execute(
                    "INSERT INTO sync_log (connector, started_at, finished_at, status, inserted, message) VALUES ('etoro', ?, datetime('now'), 'error', 0, ?)",
                    (started, str(e)),
                )
            results["connectors"]["etoro"] = {"status": "error", "error": str(e)}

    # 3. Trade Republic
    tr = TradeRepublicService()
    if tr.is_configured():
        started = datetime.now().isoformat()
        try:
            accs = tr.fetch_accounts()
            for acc in accs:
                database.upsert_account(
                    conn,
                    {
                        "provider": "trade_republic",
                        "institution": acc.institution,
                        "external_id": acc.external_id,
                        "name": acc.name,
                        "currency": acc.currency,
                        "asset_class": acc.asset_class,
                    },
                )
            holdings = tr.fetch_holdings()
            if holdings:
                acc_row = database.get_account_by_provider_ext_id(conn, "trade_republic", "tr_portfolio_eur")
                if acc_row:
                    acc_id = acc_row["id"]
                    db_holdings = [
                        {
                            "account_id": acc_id,
                            "ticker": h.ticker,
                            "isin": h.isin,
                            "name": h.name,
                            "asset_type": h.asset_type,
                            "region": "Europe",
                            "sector": "Diversified",
                            "quantity": h.quantity,
                            "cost_basis_minor": h.cost_basis_minor,
                            "currency": h.currency,
                            "updated_at": date.today().isoformat(),
                        }
                        for h in holdings
                    ]
                    database.upsert_holdings(conn, db_holdings)

            with conn:
                conn.execute(
                    "INSERT INTO sync_log (connector, started_at, finished_at, status, inserted, message) VALUES ('trade_republic', ?, datetime('now'), 'ok', 0, ?)",
                    (started, f"Synced {len(holdings)} holdings"),
                )
            results["connectors"]["trade_republic"] = {"status": "ok", "holdings": len(holdings)}
        except NeedsReauth as e:
            with conn:
                conn.execute(
                    "INSERT INTO sync_log (connector, started_at, finished_at, status, inserted, message) VALUES ('trade_republic', ?, datetime('now'), 'needs_reauth', 0, ?)",
                    (started, str(e)),
                )
            results["connectors"]["trade_republic"] = {"status": "needs_reauth", "error": str(e)}
        except Exception as e:
            with conn:
                conn.execute(
                    "INSERT INTO sync_log (connector, started_at, finished_at, status, inserted, message) VALUES ('trade_republic', ?, datetime('now'), 'error', 0, ?)",
                    (started, str(e)),
                )
            results["connectors"]["trade_republic"] = {"status": "error", "error": str(e)}

    # 4. Market Quotes
    holdings_tickers = [
        r["ticker"] for r in conn.execute("SELECT DISTINCT ticker FROM holdings WHERE ticker IS NOT NULL").fetchall()
    ]
    if holdings_tickers:
        try:
            update_quotes(holdings_tickers, db_conn=conn)
            results["quotes_updated"] = True
        except Exception:
            pass

    return results
