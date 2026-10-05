import sqlite3
from pathlib import Path

from config import DB_PATH
from db import database
from services.categorization import categorize_transactions
from services.normalization import clean_merchant, detect_internal_transfer


def run_migration():
    conn = database.connect(DB_PATH)

    # 1. Recreate v_holdings view
    conn.execute("DROP VIEW IF EXISTS v_holdings")
    conn.execute("""
    CREATE VIEW IF NOT EXISTS v_holdings AS
    SELECT h.id, a.institution, a.name AS account, h.ticker, h.isin, h.name,
           h.asset_type, h.region, h.sector, h.quantity,
           ((COALESCE(h.cost_basis_minor, 0) / 100.0) * (CASE WHEN h.currency = 'USD' THEN (1.0 / COALESCE(fx.close, 1.0)) ELSE 1.0 END)) AS cost_basis,
           h.cost_basis_minor / 100.0 AS cost_basis_native,
           h.currency,
           COALESCE(mq.close, 0) AS latest_close,
           COALESCE(mq.prev_close, mq.close, 0) AS prev_close,
           (h.quantity * COALESCE(mq.close, 0) * (CASE WHEN COALESCE(mq.currency, h.currency) = 'USD' THEN (1.0 / COALESCE(fx.close, 1.0)) ELSE 1.0 END)) AS value_eur,
           ((h.quantity * COALESCE(mq.close, 0) * (CASE WHEN COALESCE(mq.currency, h.currency) = 'USD' THEN (1.0 / COALESCE(fx.close, 1.0)) ELSE 1.0 END))
            - ((COALESCE(h.cost_basis_minor, 0) / 100.0) * (CASE WHEN h.currency = 'USD' THEN (1.0 / COALESCE(fx.close, 1.0)) ELSE 1.0 END))) AS unrealized_pnl_eur
    FROM holdings h
    JOIN accounts a ON a.id = h.account_id
    LEFT JOIN (
      SELECT ticker, close, prev_close, currency
      FROM market_quotes
      WHERE (ticker, quote_date) IN (SELECT ticker, MAX(quote_date) FROM market_quotes GROUP BY ticker)
    ) mq ON mq.ticker = h.ticker
    LEFT JOIN (
      SELECT close
      FROM market_quotes
      WHERE ticker = 'EURUSD=X' AND quote_date = (SELECT MAX(quote_date) FROM market_quotes WHERE ticker = 'EURUSD=X')
    ) fx ON 1=1;
    """)

    # 2. Update existing transactions: re-detect internal transfers and re-normalize merchants
    own_ibans = database.get_own_ibans(conn)
    cat_map = database.get_category_map(conn)
    internal_transfer_cat_id = cat_map.get("Internal Transfer")
    brokerage_deposit_cat_id = cat_map.get("Brokerage Deposits")

    tx_rows = conn.execute("SELECT * FROM transactions").fetchall()
    
    updated_transfers = 0
    updated_categories = 0

    tx_dicts = []
    for r in tx_rows:
        t = dict(r)
        desc = t.get("description_raw") or ""
        cp = t.get("counterparty_name") or ""
        iban = t.get("counterparty_iban") or ""

        # Re-clean merchant
        norm_merchant = clean_merchant(cp or desc)
        t["merchant_normalized"] = norm_merchant

        # Re-detect internal transfer
        is_transfer = detect_internal_transfer(
            description=desc,
            counterparty_name=cp,
            counterparty_iban=iban,
            own_ibans=own_ibans,
        )
        
        # Check specific brokerage / savings keywords
        combined = f"{desc} {cp}".lower()
        if "trbk" in combined or "trade republic" in combined or "etoro" in combined:
            is_transfer = True
            if not t.get("category_id"):
                t["category_id"] = brokerage_deposit_cat_id

        if "savings account" in combined or "spaarrekening" in combined:
            is_transfer = True
            if not t.get("category_id"):
                t["category_id"] = internal_transfer_cat_id

        if is_transfer:
            t["is_internal_transfer"] = 1
            if not t.get("category_id"):
                t["category_id"] = internal_transfer_cat_id
            updated_transfers += 1
        
        tx_dicts.append(t)

    # Re-run categorization on transactions that are not internal transfers
    categorized = categorize_transactions(conn, tx_dicts, enable_llm=False)

    with conn:
        for t in categorized:
            conn.execute(
                """
                UPDATE transactions
                SET merchant_normalized = ?,
                    is_internal_transfer = ?,
                    category_id = ?,
                    category_source = COALESCE(?, category_source)
                WHERE id = ?
                """,
                (
                    t["merchant_normalized"],
                    t["is_internal_transfer"],
                    t["category_id"],
                    t.get("category_source"),
                    t["id"],
                ),
            )

    conn.close()
    print(f"Migration complete! Processed {len(categorized)} transactions.")


if __name__ == "__main__":
    run_migration()
