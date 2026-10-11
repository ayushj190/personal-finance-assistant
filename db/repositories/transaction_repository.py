import sqlite3
from typing import Any, Iterable, Optional

from db.models import Transaction


class TransactionRepository:
    @staticmethod
    def row_to_transaction(row: sqlite3.Row | dict[str, Any]) -> Transaction:
        return Transaction(
            id=row["id"],
            account_id=row["account_id"],
            dedup_hash=row["dedup_hash"],
            booking_date=row["booking_date"],
            amount_minor=row["amount_minor"],
            amount_eur_minor=row["amount_eur_minor"],
            description_raw=row["description_raw"],
            currency=row.get("currency", "EUR") if isinstance(row, dict) else row["currency"],
            external_ref=row.get("external_ref") if isinstance(row, dict) else row["external_ref"],
            value_date=row.get("value_date") if isinstance(row, dict) else row["value_date"],
            counterparty_name=row.get("counterparty_name") if isinstance(row, dict) else row["counterparty_name"],
            counterparty_iban=row.get("counterparty_iban") if isinstance(row, dict) else row["counterparty_iban"],
            merchant_normalized=row.get("merchant_normalized") if isinstance(row, dict) else row["merchant_normalized"],
            mcc=row.get("mcc") if isinstance(row, dict) else row["mcc"],
            category_id=row.get("category_id") if isinstance(row, dict) else row["category_id"],
            category_source=row.get("category_source") if isinstance(row, dict) else row["category_source"],
            is_internal_transfer=row.get("is_internal_transfer", 0) if isinstance(row, dict) else row["is_internal_transfer"],
            source=row.get("source", "csv") if isinstance(row, dict) else row["source"],
            imported_at=row.get("imported_at") if isinstance(row, dict) else row["imported_at"],
        )

    @classmethod
    def get_recent(
        cls,
        conn: sqlite3.Connection,
        limit: int = 50,
        account_id: Optional[int] = None,
    ) -> list[Transaction]:
        if account_id is not None:
            cur = conn.execute(
                "SELECT * FROM transactions WHERE account_id = ? ORDER BY booking_date DESC, id DESC LIMIT ?",
                (account_id, limit),
            )
        else:
            cur = conn.execute(
                "SELECT * FROM transactions ORDER BY booking_date DESC, id DESC LIMIT ?",
                (limit,),
            )
        return [cls.row_to_transaction(r) for r in cur.fetchall()]

    @staticmethod
    def upsert_transactions(
        conn: sqlite3.Connection, txs: Iterable[Transaction | dict[str, Any]]
    ) -> int:
        query = """
        INSERT INTO transactions (
            account_id, dedup_hash, external_ref, booking_date, value_date,
            amount_minor, currency, amount_eur_minor, description_raw,
            counterparty_name, counterparty_iban, merchant_normalized,
            mcc, category_id, category_source, is_internal_transfer, source
        ) VALUES (
            :account_id, :dedup_hash, :external_ref, :booking_date, :value_date,
            :amount_minor, :currency, :amount_eur_minor, :description_raw,
            :counterparty_name, :counterparty_iban, :merchant_normalized,
            :mcc, :category_id, :category_source, :is_internal_transfer, :source
        ) ON CONFLICT(account_id, dedup_hash) DO NOTHING;
        """
        inserted = 0
        with conn:
            for tx in txs:
                if isinstance(tx, Transaction):
                    row_dict = {
                        "account_id": tx.account_id,
                        "dedup_hash": tx.dedup_hash,
                        "external_ref": tx.external_ref,
                        "booking_date": tx.booking_date,
                        "value_date": tx.value_date,
                        "amount_minor": tx.amount_minor,
                        "currency": tx.currency,
                        "amount_eur_minor": tx.amount_eur_minor,
                        "description_raw": tx.description_raw,
                        "counterparty_name": tx.counterparty_name,
                        "counterparty_iban": tx.counterparty_iban,
                        "merchant_normalized": tx.merchant_normalized,
                        "mcc": tx.mcc,
                        "category_id": tx.category_id,
                        "category_source": tx.category_source,
                        "is_internal_transfer": tx.is_internal_transfer,
                        "source": tx.source,
                    }
                else:
                    row_dict = {
                        "account_id": tx["account_id"],
                        "dedup_hash": tx["dedup_hash"],
                        "external_ref": tx.get("external_ref"),
                        "booking_date": tx["booking_date"],
                        "value_date": tx.get("value_date"),
                        "amount_minor": tx["amount_minor"],
                        "currency": tx.get("currency", "EUR"),
                        "amount_eur_minor": tx["amount_eur_minor"],
                        "description_raw": tx["description_raw"],
                        "counterparty_name": tx.get("counterparty_name"),
                        "counterparty_iban": tx.get("counterparty_iban"),
                        "merchant_normalized": tx.get("merchant_normalized"),
                        "mcc": tx.get("mcc"),
                        "category_id": tx.get("category_id"),
                        "category_source": tx.get("category_source"),
                        "is_internal_transfer": tx.get("is_internal_transfer", 0),
                        "source": tx.get("source", "csv"),
                    }
                cur = conn.execute(query, row_dict)
                if cur.rowcount > 0:
                    inserted += cur.rowcount
        return inserted

    @staticmethod
    def get_monthly_cashflow(conn: sqlite3.Connection) -> list[dict[str, Any]]:
        cur = conn.execute("SELECT * FROM v_monthly_cashflow ORDER BY month ASC")
        return [dict(r) for r in cur.fetchall()]

    @staticmethod
    def get_monthly_expenses(conn: sqlite3.Connection) -> list[float]:
        query = """
        SELECT strftime('%Y-%m', t.booking_date) AS month,
               SUM(CASE WHEN c.kind IN ('fixed','discretionary') THEN -t.amount_eur_minor ELSE 0 END) / 100.0 AS expenses
        FROM transactions t
        LEFT JOIN categories c ON c.id = t.category_id
        WHERE t.is_internal_transfer = 0
        GROUP BY strftime('%Y-%m', t.booking_date)
        ORDER BY month ASC
        """
        rows = conn.execute(query).fetchall()
        return [r["expenses"] for r in rows if r["expenses"] > 0]

    @staticmethod
    def get_recent_spending_df(conn: sqlite3.Connection, days: int = 30):
        import pandas as pd
        spend_query = f"""
        SELECT c.name AS category, t.merchant_normalized AS merchant, -t.amount_eur_minor / 100.0 AS amount_eur
        FROM transactions t
        JOIN categories c ON c.id = t.category_id
        WHERE t.amount_eur_minor < 0
          AND c.kind IN ('fixed', 'discretionary')
          AND t.is_internal_transfer = 0
          AND t.booking_date >= date('now', '-{days} days')
        """
        return pd.read_sql_query(spend_query, conn)

    @staticmethod
    def get_v_transactions(conn: sqlite3.Connection, limit: int = 500) -> list[dict[str, Any]]:
        cur = conn.execute(
            "SELECT * FROM v_transactions ORDER BY booking_date DESC LIMIT ?",
            (limit,),
        )
        return [dict(r) for r in cur.fetchall()]

    @staticmethod
    def get_average_monthly_expenses(conn: sqlite3.Connection) -> float:
        query = """
        SELECT AVG(monthly_exp) as m_exp
        FROM (
            SELECT SUM(amount_eur) as monthly_exp
            FROM v_transactions
            WHERE amount_eur < 0 AND category_kind IN ('fixed', 'discretionary')
            GROUP BY strftime('%Y-%m', booking_date)
        )
        """
        row = conn.execute(query).fetchone()
        return float(row["m_exp"] or 0) if row else 0.0

    @staticmethod
    def get_average_monthly_savings(conn: sqlite3.Connection) -> float:
        row = conn.execute("SELECT AVG(savings_eur) as m_sav FROM v_monthly_cashflow").fetchone()
        return float(row["m_sav"] or 0) if row else 0.0

    @staticmethod
    def get_goals(conn: sqlite3.Connection) -> list[dict[str, Any]]:
        query = """
        SELECT g.*, a.name as account_name,
               (SELECT balance_eur_minor/100.0
                FROM account_snapshots s
                WHERE s.account_id = g.account_id
                ORDER BY snapshot_date DESC LIMIT 1) as current_balance
        FROM goals g
        LEFT JOIN accounts a ON a.id = g.account_id
        ORDER BY g.id ASC
        """
        cur = conn.execute(query)
        return [dict(r) for r in cur.fetchall()]

    @staticmethod
    def add_goal(
        conn: sqlite3.Connection, name: str, target_amount: float, account_id: Optional[int] = None
    ) -> int:
        with conn:
            cur = conn.execute(
                "INSERT INTO goals (name, target_amount, account_id) VALUES (?, ?, ?)",
                (name, target_amount, account_id),
            )
            return cur.lastrowid


