import sqlite3
from typing import Any, Iterable, Optional
import pandas as pd

from db.models import Holding


class HoldingRepository:
    @staticmethod
    def row_to_holding(row: sqlite3.Row | dict[str, Any]) -> Holding:
        return Holding(
            id=row["id"],
            account_id=row["account_id"],
            ticker=row["ticker"],
            asset_type=row["asset_type"],
            quantity=row["quantity"],
            currency=row.get("currency", "EUR") if isinstance(row, dict) else row["currency"],
            updated_at=row["updated_at"],
            isin=row.get("isin") if isinstance(row, dict) else row["isin"],
            name=row.get("name") if isinstance(row, dict) else row["name"],
            region=row.get("region") if isinstance(row, dict) else row["region"],
            sector=row.get("sector") if isinstance(row, dict) else row["sector"],
            cost_basis_minor=row.get("cost_basis_minor") if isinstance(row, dict) else row["cost_basis_minor"],
        )

    @classmethod
    def get_all_holdings(cls, conn: sqlite3.Connection) -> list[Holding]:
        cur = conn.execute("SELECT * FROM holdings ORDER BY ticker ASC")
        return [cls.row_to_holding(r) for r in cur.fetchall()]

    @staticmethod
    def get_distinct_tickers(conn: sqlite3.Connection) -> list[str]:
        cur = conn.execute("SELECT DISTINCT ticker FROM v_holdings")
        return [r["ticker"] for r in cur.fetchall() if r["ticker"]]

    @staticmethod
    def get_v_holdings_df(conn: sqlite3.Connection) -> pd.DataFrame:
        return pd.read_sql_query("SELECT * FROM v_holdings", conn)

    @staticmethod
    def upsert_holdings(
        conn: sqlite3.Connection, holdings: Iterable[Holding | dict[str, Any]]
    ) -> None:
        query = """
        INSERT INTO holdings (
            account_id, ticker, isin, name, asset_type, region, sector,
            quantity, cost_basis_minor, currency, updated_at
        ) VALUES (
            :account_id, :ticker, :isin, :name, :asset_type, :region, :sector,
            :quantity, :cost_basis_minor, :currency, :updated_at
        ) ON CONFLICT(account_id, ticker) DO UPDATE SET
            quantity = excluded.quantity,
            cost_basis_minor = excluded.cost_basis_minor,
            updated_at = excluded.updated_at,
            name = COALESCE(excluded.name, holdings.name),
            isin = COALESCE(excluded.isin, holdings.isin),
            asset_type = COALESCE(excluded.asset_type, holdings.asset_type),
            region = COALESCE(excluded.region, holdings.region),
            sector = COALESCE(excluded.sector, holdings.sector);
        """
        records = []
        for h in holdings:
            if isinstance(h, Holding):
                records.append({
                    "account_id": h.account_id,
                    "ticker": h.ticker,
                    "isin": h.isin,
                    "name": h.name,
                    "asset_type": h.asset_type,
                    "region": h.region,
                    "sector": h.sector,
                    "quantity": h.quantity,
                    "cost_basis_minor": h.cost_basis_minor,
                    "currency": h.currency,
                    "updated_at": h.updated_at,
                })
            else:
                records.append(h)
        with conn:
            conn.executemany(query, records)

    @staticmethod
    def upsert_market_quotes(
        conn: sqlite3.Connection, quotes: Iterable[dict[str, Any]]
    ) -> None:
        query = """
        INSERT INTO market_quotes (ticker, quote_date, close, prev_close, currency, fetched_at)
        VALUES (:ticker, :quote_date, :close, :prev_close, :currency, datetime('now'))
        ON CONFLICT(ticker, quote_date) DO UPDATE SET
            close = excluded.close,
            prev_close = COALESCE(excluded.prev_close, market_quotes.prev_close),
            currency = excluded.currency,
            fetched_at = datetime('now');
        """
        with conn:
            conn.executemany(query, quotes)

    @staticmethod
    def get_latest_fx_quote(
        conn: sqlite3.Connection, pair: str = "EURUSD=X"
    ) -> Optional[float]:
        row = conn.execute(
            "SELECT close FROM market_quotes WHERE ticker = ? ORDER BY quote_date DESC LIMIT 1",
            (pair,),
        ).fetchone()
        if row and row["close"]:
            return float(row["close"])
        return None

    @staticmethod
    def get_allocation_profiles(conn: sqlite3.Connection) -> list[dict[str, Any]]:
        cur = conn.execute("SELECT * FROM allocation_profiles ORDER BY is_active DESC, name ASC")
        return [dict(r) for r in cur.fetchall()]

    @staticmethod
    def get_allocation_targets(conn: sqlite3.Connection, profile_id: int) -> dict[str, float]:
        cur = conn.execute(
            "SELECT bucket, target_pct FROM allocation_targets WHERE profile_id = ?",
            (profile_id,),
        )
        return {r["bucket"]: float(r["target_pct"]) for r in cur.fetchall()}

