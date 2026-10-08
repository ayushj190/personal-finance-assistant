import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "finance.db"


def cleanup():
    if not DB_PATH.exists():
        print(f"DB not found at {DB_PATH}")
        return

    # 1. Backup DB
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = DB_PATH.parent / f"finance_backup_{ts}.db"
    shutil.copy2(DB_PATH, backup_path)
    print(f"Created backup: {backup_path}")

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = OFF;")

    with conn:
        # 2. Add 'apy' column to accounts if missing
        cols = [r["name"]
                for r in conn.execute("PRAGMA table_info(accounts)").fetchall()]
        if "apy" not in cols:
            conn.execute(
                "ALTER TABLE accounts ADD COLUMN apy REAL DEFAULT NULL;")
            print("Added column 'apy' to accounts.")

        # 3. Add 'Interest' category if missing
        interest_cat = conn.execute(
            "SELECT id FROM categories WHERE name = 'Interest' AND parent_id = 1").fetchone()
        if not interest_cat:
            conn.execute(
                "INSERT OR IGNORE INTO categories (id, name, parent_id, kind) VALUES (6, 'Interest', 1, 'income')")
            print("Added 'Interest' category under Income.")

        # 4. Merge account #9 into account #7 (Trade Republic)
        acc7 = conn.execute("SELECT id FROM accounts WHERE id = 7").fetchone()
        acc9 = conn.execute("SELECT id FROM accounts WHERE id = 9").fetchone()
        if acc7:
            # Set default 3.0% APY for Trade Republic
            conn.execute(
                "UPDATE accounts SET apy = 3.0, provider = 'manual', institution = 'Trade Republic' WHERE id = 7")
            print("Updated Trade Republic account #7 with APY = 3.0%")

        if acc9:
            # Reassign any tx or snapshots from 9 to 7
            conn.execute(
                "UPDATE OR IGNORE transactions SET account_id = 7 WHERE account_id = 9")
            conn.execute("DELETE FROM transactions WHERE account_id = 9")
            conn.execute(
                "UPDATE OR IGNORE account_snapshots SET account_id = 7 WHERE account_id = 9")
            conn.execute("DELETE FROM account_snapshots WHERE account_id = 9")
            conn.execute("DELETE FROM accounts WHERE id = 9")
            print("Merged and deleted duplicate Trade Republic account #9 into #7.")

        # 5. Delete empty TR securities account #8
        acc8 = conn.execute("SELECT id FROM accounts WHERE id = 8").fetchone()
        if acc8:
            conn.execute("DELETE FROM holdings WHERE account_id = 8")
            conn.execute("DELETE FROM account_snapshots WHERE account_id = 8")
            conn.execute("DELETE FROM transactions WHERE account_id = 8")
            conn.execute("DELETE FROM accounts WHERE id = 8")
            print("Deleted empty Trade Republic securities account #8.")

        # 6. Delete orphan snapshots
        deleted_snapshots = conn.execute(
            "DELETE FROM account_snapshots WHERE account_id NOT IN (SELECT id FROM accounts)").rowcount
        print(f"Deleted {deleted_snapshots} orphaned snapshots.")

        # 7. Check transactions constraint for 'pdf' source
        # In SQLite, recreating table or checking if 'pdf' works:
        try:
            conn.execute("INSERT INTO transactions (account_id, dedup_hash, booking_date, amount_minor, currency, amount_eur_minor, description_raw, source) VALUES (7, '__test_check__', '2026-01-01', 0, 'EUR', 0, 'test', 'pdf')")
            conn.execute(
                "DELETE FROM transactions WHERE dedup_hash = '__test_check__'")
            print("Transactions table allows 'pdf' source.")
        except sqlite3.IntegrityError:
            print("Recreating transactions table to allow 'pdf' source...")
            conn.execute("DROP VIEW IF EXISTS v_transactions;")
            conn.execute("DROP VIEW IF EXISTS v_monthly_cashflow;")
            conn.execute("""
            CREATE TABLE transactions_new (
              id                  INTEGER PRIMARY KEY,
              account_id          INTEGER NOT NULL REFERENCES accounts(id),
              dedup_hash          TEXT NOT NULL,
              external_ref        TEXT,
              booking_date        TEXT NOT NULL,
              value_date          TEXT,
              amount_minor        INTEGER NOT NULL,
              currency            TEXT NOT NULL,
              amount_eur_minor    INTEGER NOT NULL,
              description_raw     TEXT NOT NULL,
              counterparty_name   TEXT,
              counterparty_iban   TEXT,
              merchant_normalized TEXT,
              mcc                 TEXT,
              category_id         INTEGER REFERENCES categories(id),
              category_source     TEXT CHECK (category_source IN ('mcc','rule','llm','user')),
              is_internal_transfer INTEGER NOT NULL DEFAULT 0,
              source              TEXT NOT NULL CHECK (source IN ('api','csv','mt940','camt053','pdf')),
              imported_at         TEXT NOT NULL DEFAULT (datetime('now')),
              UNIQUE (account_id, dedup_hash)
            );
            """)
            conn.execute(
                "INSERT INTO transactions_new SELECT * FROM transactions;")
            conn.execute("DROP TABLE transactions;")
            conn.execute(
                "ALTER TABLE transactions_new RENAME TO transactions;")
            conn.execute("""
            CREATE VIEW IF NOT EXISTS v_transactions AS
            SELECT t.id, t.booking_date, a.institution, a.name AS account,
                   t.amount_eur_minor / 100.0 AS amount_eur, t.currency,
                   t.merchant_normalized AS merchant, c.name AS category,
                   p.name AS parent_category, c.kind AS category_kind,
                   t.is_internal_transfer
            FROM transactions t
            JOIN accounts a ON a.id = t.account_id
            LEFT JOIN categories c ON c.id = t.category_id
            LEFT JOIN categories p ON p.id = c.parent_id;
            """)
            conn.execute("""
            CREATE VIEW IF NOT EXISTS v_monthly_cashflow AS
            SELECT strftime('%Y-%m', t.booking_date) AS month,
                   SUM(CASE WHEN COALESCE(c.kind, CASE WHEN t.amount_eur_minor > 0 THEN 'income' ELSE 'discretionary' END) = 'income' THEN t.amount_eur_minor ELSE 0 END) / 100.0 AS income_eur,
                   SUM(CASE WHEN c.kind = 'fixed' THEN -t.amount_eur_minor ELSE 0 END) / 100.0 AS fixed_eur,
                   SUM(CASE WHEN COALESCE(c.kind, CASE WHEN t.amount_eur_minor < 0 THEN 'discretionary' ELSE '' END) = 'discretionary' THEN -t.amount_eur_minor ELSE 0 END) / 100.0 AS discretionary_eur,
                   SUM(CASE WHEN c.kind = 'savings' THEN -t.amount_eur_minor ELSE 0 END) / 100.0 AS savings_eur
            FROM transactions t
            LEFT JOIN categories c ON c.id = t.category_id
            WHERE t.is_internal_transfer = 0
            GROUP BY strftime('%Y-%m', t.booking_date);
            """)
            print("Successfully updated transactions table schema with 'pdf' source.")

    conn.execute("PRAGMA foreign_keys = ON;")
    conn.close()
    print("Database cleanup completed successfully.")


if __name__ == "__main__":
    cleanup()
