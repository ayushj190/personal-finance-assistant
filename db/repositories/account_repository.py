import sqlite3
from datetime import date, datetime
from typing import Any, Optional

from db.models import Account


class AccountRepository:
    @staticmethod
    def row_to_account(row: sqlite3.Row | dict[str, Any]) -> Account:
        return Account(
            id=row["id"],
            provider=row["provider"],
            institution=row["institution"],
            name=row["name"],
            currency=row.get("currency", "EUR") if isinstance(row, dict) else row["currency"],
            asset_class=row["asset_class"],
            external_id=row.get("external_id") if isinstance(row, dict) else row["external_id"],
            iban=row.get("iban") if isinstance(row, dict) else row["iban"],
            apy=row.get("apy") if isinstance(row, dict) else row["apy"],
            is_active=row.get("is_active", 1) if isinstance(row, dict) else row["is_active"],
            created_at=row.get("created_at") if isinstance(row, dict) else row["created_at"],
        )

    @classmethod
    def get_active_accounts(cls, conn: sqlite3.Connection) -> list[Account]:
        cur = conn.execute("SELECT * FROM accounts WHERE is_active = 1")
        return [cls.row_to_account(r) for r in cur.fetchall()]

    @classmethod
    def get_all_accounts(cls, conn: sqlite3.Connection) -> list[Account]:
        cur = conn.execute("SELECT * FROM accounts ORDER BY institution ASC, name ASC")
        return [cls.row_to_account(r) for r in cur.fetchall()]

    @classmethod
    def get_by_id(cls, conn: sqlite3.Connection, account_id: int) -> Optional[Account]:
        cur = conn.execute("SELECT * FROM accounts WHERE id = ?", (account_id,))
        row = cur.fetchone()
        return cls.row_to_account(row) if row else None

    @classmethod
    def get_by_provider_ext_id(
        cls, conn: sqlite3.Connection, provider: str, ext_id: str
    ) -> Optional[Account]:
        cur = conn.execute(
            "SELECT * FROM accounts WHERE provider = ? AND external_id = ?",
            (provider, ext_id),
        )
        row = cur.fetchone()
        return cls.row_to_account(row) if row else None

    @staticmethod
    def upsert(conn: sqlite3.Connection, acc: Account | dict[str, Any]) -> int:
        if isinstance(acc, Account):
            provider = acc.provider
            institution = acc.institution
            external_id = acc.external_id
            iban = acc.iban
            name = acc.name
            currency = acc.currency
            asset_class = acc.asset_class
            apy = acc.apy
            is_active = acc.is_active
        else:
            provider = acc["provider"]
            institution = acc["institution"]
            external_id = acc.get("external_id")
            iban = acc.get("iban")
            name = acc["name"]
            currency = acc.get("currency", "EUR")
            asset_class = acc.get("asset_class", "cash")
            apy = acc.get("apy")
            is_active = acc.get("is_active", 1)

        query = """
        INSERT INTO accounts (provider, institution, external_id, iban, name, currency, asset_class, apy, is_active)
        VALUES (:provider, :institution, :external_id, :iban, :name, :currency, :asset_class, :apy, :is_active)
        ON CONFLICT(provider, external_id) DO UPDATE SET
            name = excluded.name,
            iban = COALESCE(excluded.iban, accounts.iban),
            currency = excluded.currency,
            asset_class = excluded.asset_class,
            apy = COALESCE(excluded.apy, accounts.apy),
            is_active = excluded.is_active;
        """
        params = {
            "provider": provider,
            "institution": institution,
            "external_id": external_id,
            "iban": iban,
            "name": name,
            "currency": currency,
            "asset_class": asset_class,
            "apy": apy,
            "is_active": is_active,
        }
        with conn:
            conn.execute(query, params)
            row = conn.execute(
                "SELECT id FROM accounts WHERE provider = ? AND external_id = ?",
                (provider, external_id),
            ).fetchone()
            return row[0] if row else 0

    @staticmethod
    def update_apy(conn: sqlite3.Connection, account_id: int, apy: float) -> None:
        with conn:
            conn.execute("UPDATE accounts SET apy = ? WHERE id = ?", (apy, account_id))

    @staticmethod
    def get_latest_snapshot(
        conn: sqlite3.Connection, account_id: int
    ) -> Optional[dict[str, Any]]:
        cur = conn.execute(
            """
            SELECT balance_minor, balance_eur_minor, snapshot_date
            FROM account_snapshots
            WHERE account_id = ?
            ORDER BY snapshot_date DESC
            LIMIT 1
            """,
            (account_id,),
        )
        row = cur.fetchone()
        return dict(row) if row else None

    @staticmethod
    def get_all_latest_snapshots(
        conn: sqlite3.Connection,
    ) -> dict[int, dict[str, Any]]:
        cur = conn.execute(
            """
            SELECT s.account_id, s.balance_minor, s.balance_eur_minor, s.snapshot_date
            FROM account_snapshots s
            INNER JOIN (
                SELECT account_id, MAX(snapshot_date) as max_date
                FROM account_snapshots
                GROUP BY account_id
            ) latest ON s.account_id = latest.account_id AND s.snapshot_date = latest.max_date
            """
        )
        return {r["account_id"]: dict(r) for r in cur.fetchall()}

    @staticmethod
    def get_manual_stale_accounts(
        conn: sqlite3.Connection, days_threshold: int = 30
    ) -> list[str]:
        cur = conn.execute(
            """
            SELECT a.name, MAX(s.snapshot_date) as last_snap
            FROM accounts a
            LEFT JOIN account_snapshots s ON s.account_id = a.id
            WHERE a.provider = 'manual' AND a.is_active = 1
            GROUP BY a.id
            """
        )
        stale = []
        today = date.today()
        for r in cur.fetchall():
            if not r["last_snap"]:
                stale.append(r["name"])
            else:
                try:
                    last_snap = datetime.strptime(r["last_snap"][:10], "%Y-%m-%d").date()
                    if (today - last_snap).days >= days_threshold:
                        stale.append(r["name"])
                except Exception:
                    stale.append(r["name"])
        return stale

    @staticmethod
    def get_recent_sync_logs(
        conn: sqlite3.Connection, limit: int = 50
    ) -> list[dict[str, Any]]:
        cur = conn.execute(
            "SELECT connector, started_at, status, message FROM sync_log ORDER BY started_at DESC LIMIT ?",
            (limit,),
        )
        return [dict(r) for r in cur.fetchall()]

    @classmethod
    def get_cash_accounts(cls, conn: sqlite3.Connection) -> list[Account]:
        cur = conn.execute("SELECT * FROM accounts WHERE asset_class = 'cash' AND is_active = 1")
        return [cls.row_to_account(r) for r in cur.fetchall()]

    @staticmethod
    def get_total_cash_balance(conn: sqlite3.Connection) -> float:
        row = conn.execute(
            "SELECT SUM(balance_eur_minor)/100.0 AS val FROM account_snapshots WHERE account_id IN (SELECT id FROM accounts WHERE asset_class = 'cash')"
        ).fetchone()
        return float(row["val"] or 0.0) if row else 0.0

    @staticmethod
    def get_latest_net_worth_snapshot(conn: sqlite3.Connection) -> float:
        row = conn.execute(
            "SELECT SUM(balance_eur_minor)/100.0 as nw FROM account_snapshots WHERE snapshot_date = (SELECT MAX(snapshot_date) FROM account_snapshots)"
        ).fetchone()
        return float(row["nw"] or 0.0) if row else 0.0

