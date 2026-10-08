import sqlite3
from typing import Any


def get_active_accounts(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    return [dict(r) for r in conn.execute("SELECT * FROM accounts WHERE is_active = 1").fetchall()]


def get_recent_sync_logs(conn: sqlite3.Connection, limit: int = 5) -> list[dict[str, Any]]:
    return [dict(r) for r in conn.execute("SELECT connector, started_at, status, message FROM sync_log ORDER BY started_at DESC LIMIT ?", (limit,)).fetchall()]


def get_liabilities(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    return [dict(r) for r in conn.execute("SELECT * FROM liabilities").fetchall()]


def get_allocation_profiles(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    return [dict(r) for r in conn.execute("SELECT * FROM allocation_profiles ORDER BY is_active DESC, name ASC").fetchall()]


def get_categories(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    return [dict(r) for r in conn.execute("SELECT id, name FROM categories ORDER BY name ASC").fetchall()]


def update_account_apy(conn: sqlite3.Connection, account_id: int, apy: float) -> None:
    with conn:
        conn.execute("UPDATE accounts SET apy = ? WHERE id = ?",
                     (apy, account_id))


def get_cash_accounts(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    return [dict(r) for r in conn.execute("SELECT id, institution, name, currency, apy FROM accounts WHERE asset_class = 'cash' AND is_active = 1").fetchall()]
