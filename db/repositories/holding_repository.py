import sqlite3
from datetime import datetime
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
            status=row.get("status", "active") if isinstance(row, dict) else (row["status"] if "status" in row.keys() else "active"),
            closed_at=row.get("closed_at") if isinstance(row, dict) else (row["closed_at"] if "closed_at" in row.keys() else None),
            realized_pnl_minor=row.get("realized_pnl_minor", 0) if isinstance(row, dict) else (row["realized_pnl_minor"] if "realized_pnl_minor" in row.keys() else 0),
            realized_proceeds_minor=row.get("realized_proceeds_minor", 0) if isinstance(row, dict) else (row["realized_proceeds_minor"] if "realized_proceeds_minor" in row.keys() else 0),
        )

    @classmethod
    def get_all_holdings(cls, conn: sqlite3.Connection) -> list[Holding]:
        cur = conn.execute("SELECT * FROM holdings ORDER BY ticker ASC")
        return [cls.row_to_holding(r) for r in cur.fetchall()]

    @staticmethod
    def get_v_holdings_df(conn: sqlite3.Connection, include_closed: bool = False) -> pd.DataFrame:
        if not include_closed:
            return pd.read_sql_query("SELECT * FROM v_holdings", conn)

        query = """
        SELECT h.id, a.institution, a.name AS account, h.ticker, h.isin, h.name,
               h.asset_type, h.region, h.sector, h.quantity,
               ((COALESCE(h.cost_basis_minor, 0) / 100.0) * (CASE WHEN h.currency = 'USD' THEN (1.0 / COALESCE(fx.close, 1.0)) ELSE 1.0 END)) AS cost_basis,
               h.cost_basis_minor / 100.0 AS cost_basis_native,
               h.currency,
               COALESCE(mq.close, 0) AS latest_close,
               COALESCE(mq.prev_close, mq.close, 0) AS prev_close,
               (CASE 
                  WHEN COALESCE(mq.close, 0) > 0 THEN 
                    (h.quantity * mq.close * (CASE WHEN COALESCE(mq.currency, h.currency) = 'USD' THEN (1.0 / COALESCE(fx.close, 1.0)) ELSE 1.0 END))
                  ELSE 
                    ((COALESCE(h.cost_basis_minor, 0) / 100.0) * (CASE WHEN h.currency = 'USD' THEN (1.0 / COALESCE(fx.close, 1.0)) ELSE 1.0 END))
                END) AS value_eur,
               (CASE 
                  WHEN COALESCE(mq.close, 0) > 0 THEN 
                    ((h.quantity * mq.close * (CASE WHEN COALESCE(mq.currency, h.currency) = 'USD' THEN (1.0 / COALESCE(fx.close, 1.0)) ELSE 1.0 END))
                     - ((COALESCE(h.cost_basis_minor, 0) / 100.0) * (CASE WHEN h.currency = 'USD' THEN (1.0 / COALESCE(fx.close, 1.0)) ELSE 1.0 END)))
                  ELSE 0.0
                END) AS unrealized_pnl_eur,
               h.status,
               h.closed_at,
               h.updated_at
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
        """
        return pd.read_sql_query(query, conn)

    @classmethod
    def get_portfolio_kpis(cls, conn: sqlite3.Connection) -> dict[str, Any]:
        df = cls.get_v_holdings_df(conn)
        if df.empty:
            return {
                "total_value": 0.0,
                "total_cost": 0.0,
                "unrealized_pnl": 0.0,
                "return_pct": 0.0,
                "unquoted_count": 0,
            }
        total_val = float(df["value_eur"].sum())
        total_cost = float(df["cost_basis"].sum())
        unrealized_pnl = float(df["unrealized_pnl_eur"].sum())
        ret_pct = (unrealized_pnl / total_cost * 100.0) if total_cost > 0 else 0.0
        unquoted = int((df["latest_close"] <= 0).sum()) if "latest_close" in df.columns else 0
        return {
            "total_value": total_val,
            "total_cost": total_cost,
            "unrealized_pnl": unrealized_pnl,
            "return_pct": ret_pct,
            "unquoted_count": unquoted,
        }

    @staticmethod
    def upsert_holdings(
        conn: sqlite3.Connection, holdings: Iterable[Holding | dict[str, Any]]
    ) -> None:
        query = """
        INSERT INTO holdings (
            account_id, ticker, isin, name, asset_type, region, sector,
            quantity, cost_basis_minor, currency, status, closed_at,
            realized_pnl_minor, realized_proceeds_minor, updated_at
        ) VALUES (
            :account_id, :ticker, :isin, :name, :asset_type, :region, :sector,
            :quantity, :cost_basis_minor, :currency, :status, :closed_at,
            :realized_pnl_minor, :realized_proceeds_minor, :updated_at
        ) ON CONFLICT(account_id, ticker) DO UPDATE SET
            quantity = excluded.quantity,
            cost_basis_minor = excluded.cost_basis_minor,
            updated_at = excluded.updated_at,
            status = excluded.status,
            closed_at = excluded.closed_at,
            realized_pnl_minor = excluded.realized_pnl_minor,
            realized_proceeds_minor = excluded.realized_proceeds_minor,
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
                    "status": h.status or "active",
                    "closed_at": h.closed_at,
                    "realized_pnl_minor": h.realized_pnl_minor or 0,
                    "realized_proceeds_minor": h.realized_proceeds_minor or 0,
                    "updated_at": h.updated_at,
                })
            else:
                rec = {
                    "account_id": h["account_id"],
                    "ticker": h["ticker"],
                    "isin": h.get("isin"),
                    "name": h.get("name"),
                    "asset_type": h.get("asset_type", "stock"),
                    "region": h.get("region"),
                    "sector": h.get("sector"),
                    "quantity": float(h.get("quantity", 0.0)),
                    "cost_basis_minor": h.get("cost_basis_minor"),
                    "currency": h.get("currency", "EUR"),
                    "status": h.get("status", "active"),
                    "closed_at": h.get("closed_at"),
                    "realized_pnl_minor": int(h.get("realized_pnl_minor", 0) or 0),
                    "realized_proceeds_minor": int(h.get("realized_proceeds_minor", 0) or 0),
                    "updated_at": h.get("updated_at") or datetime.now().isoformat(),
                }
                records.append(rec)
        with conn:
            conn.executemany(query, records)

    @classmethod
    def reconcile_account_holdings(
        cls,
        conn: sqlite3.Connection,
        account_id: int,
        statement_holdings: list[dict[str, Any]],
    ) -> dict[str, int]:
        """
        Atomic statement reconciliation inside a single database transaction.
        Upserts incoming statement holdings with active status.
        Marks existing positions for that account absent from statement as closed.
        """
        statement_tickers = {h["ticker"] for h in statement_holdings if h.get("ticker")}
        now_iso = datetime.now().isoformat()

        with conn:
            cur = conn.execute(
                "SELECT ticker FROM holdings WHERE account_id = ? AND status = 'active'",
                (account_id,),
            )
            existing_active_tickers = {r["ticker"] for r in cur.fetchall()}
            missing_tickers = existing_active_tickers - statement_tickers

            closed_count = 0
            if missing_tickers:
                placeholders = ",".join("?" for _ in missing_tickers)
                params = [now_iso, now_iso, account_id, *list(missing_tickers)]
                conn.execute(
                    f"""
                    UPDATE holdings
                    SET quantity = 0.0,
                        status = 'closed',
                        closed_at = ?,
                        updated_at = ?
                    WHERE account_id = ? AND ticker IN ({placeholders})
                    """,
                    params,
                )
                closed_count = len(missing_tickers)

            for h in statement_holdings:
                h["status"] = "active"
                h["closed_at"] = None
                if not h.get("updated_at"):
                    h["updated_at"] = now_iso

            cls.upsert_holdings(conn, statement_holdings)

            active_cur = conn.execute(
                "SELECT COUNT(*) FROM holdings WHERE account_id = ? AND status = 'active' AND quantity > 0",
                (account_id,),
            )
            active_total = active_cur.fetchone()[0]

            return {
                "upserted": len(statement_holdings),
                "closed": closed_count,
                "active_total": active_total,
            }

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
        if row:
            val = row["close"] if hasattr(row, "keys") else row[0]
            if val is not None:
                return float(val)
        return None

    @staticmethod
    def get_latest_quotes(conn: sqlite3.Connection) -> list[sqlite3.Row]:
        """Latest stored close per active holding ticker, with the prior close for a delta.

        The freshest row often carries `prev_close` equal to its own `close`, so the
        previous trading day's stored close wins when one exists.
        """
        return conn.execute(
            """
            SELECT q.ticker, q.currency, q.close,
                   COALESCE(
                       (SELECT p.close FROM market_quotes p
                        WHERE p.ticker = q.ticker AND p.quote_date < q.quote_date
                        ORDER BY p.quote_date DESC LIMIT 1),
                       q.prev_close, q.close
                   ) AS prior_close
            FROM market_quotes q
            WHERE q.quote_date = (SELECT MAX(m.quote_date) FROM market_quotes m WHERE m.ticker = q.ticker)
              AND q.ticker IN (SELECT ticker FROM v_holdings)
            ORDER BY q.ticker
            """
        ).fetchall()

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

    @staticmethod
    def get_realized_pnl_summary(conn: sqlite3.Connection) -> dict[str, Any]:
        """
        Aggregate realized profit/loss and total proceeds for closed holdings,
        converting USD to EUR via latest FX quote.
        Returns dict with realized_pnl_eur, total_proceeds_eur, closed_count.
        """
        query = """
        SELECT 
            h.realized_pnl_minor,
            h.realized_proceeds_minor,
            h.currency,
            (CASE WHEN h.currency = 'USD' THEN (1.0 / COALESCE(fx.close, 1.0)) ELSE 1.0 END) AS fx_rate
        FROM holdings h
        LEFT JOIN (
            SELECT close
            FROM market_quotes
            WHERE ticker = 'EURUSD=X' AND quote_date = (SELECT MAX(quote_date) FROM market_quotes WHERE ticker = 'EURUSD=X')
        ) fx ON 1=1
        WHERE h.status = 'closed';
        """
        rows = conn.execute(query).fetchall()
        if not rows:
            return {
                "realized_pnl_eur": 0.0,
                "total_proceeds_eur": 0.0,
                "closed_count": 0,
            }

        total_pnl_eur = 0.0
        total_proceeds_eur = 0.0
        for r in rows:
            rate = float(r["fx_rate"] or 1.0)
            pnl_native = (r["realized_pnl_minor"] or 0) / 100.0
            proceeds_native = (r["realized_proceeds_minor"] or 0) / 100.0
            total_pnl_eur += pnl_native * rate
            total_proceeds_eur += proceeds_native * rate

        return {
            "realized_pnl_eur": total_pnl_eur,
            "total_proceeds_eur": total_proceeds_eur,
            "closed_count": len(rows),
        }

    @staticmethod
    def get_closed_holdings_df(conn: sqlite3.Connection) -> pd.DataFrame:
        """
        Return DataFrame of closed positions with ticker, name, cost_basis,
        proceeds, realized_pnl, closed_date, currency, closed_at, and return_pct.
        """
        query = """
        SELECT 
            h.id,
            h.ticker,
            h.name,
            h.currency,
            h.closed_at,
            ((COALESCE(h.cost_basis_minor, 0) / 100.0) * (CASE WHEN h.currency = 'USD' THEN (1.0 / COALESCE(fx.close, 1.0)) ELSE 1.0 END)) AS cost_basis,
            ((COALESCE(h.realized_proceeds_minor, 0) / 100.0) * (CASE WHEN h.currency = 'USD' THEN (1.0 / COALESCE(fx.close, 1.0)) ELSE 1.0 END)) AS proceeds,
            ((COALESCE(h.realized_pnl_minor, 0) / 100.0) * (CASE WHEN h.currency = 'USD' THEN (1.0 / COALESCE(fx.close, 1.0)) ELSE 1.0 END)) AS realized_pnl
        FROM holdings h
        LEFT JOIN (
            SELECT close
            FROM market_quotes
            WHERE ticker = 'EURUSD=X' AND quote_date = (SELECT MAX(quote_date) FROM market_quotes WHERE ticker = 'EURUSD=X')
        ) fx ON 1=1
        WHERE h.status = 'closed'
        ORDER BY h.closed_at DESC, h.ticker ASC;
        """
        df = pd.read_sql_query(query, conn)
        if df.empty:
            return pd.DataFrame(columns=[
                "id", "ticker", "name", "currency", "closed_at", "closed_date",
                "cost_basis", "proceeds", "realized_pnl", "return_pct"
            ])
        df["closed_date"] = df["closed_at"].fillna("").astype(str).str.slice(0, 10)
        df["return_pct"] = df.apply(
            lambda r: (r["realized_pnl"] / r["cost_basis"] * 100.0) if r["cost_basis"] > 0 else 0.0,
            axis=1,
        )
        return df

    @staticmethod
    def upsert_portfolio_snapshot(
        conn: sqlite3.Connection,
        snapshot_date: str,
        market_value_eur_minor: int,
        cost_basis_eur_minor: int,
        day_pnl_eur_minor: int | None = None,
    ) -> None:
        """Upsert a single portfolio valuation snapshot per day (minor units)."""
        conn.execute(
            """
            INSERT INTO portfolio_snapshots (
                snapshot_date, market_value_eur_minor, cost_basis_eur_minor, day_pnl_eur_minor, fetched_at
            ) VALUES (?, ?, ?, ?, datetime('now'))
            ON CONFLICT(snapshot_date) DO UPDATE SET
                market_value_eur_minor = excluded.market_value_eur_minor,
                cost_basis_eur_minor = excluded.cost_basis_eur_minor,
                day_pnl_eur_minor = excluded.day_pnl_eur_minor,
                fetched_at = excluded.fetched_at;
            """,
            (
                str(snapshot_date),
                int(market_value_eur_minor),
                int(cost_basis_eur_minor),
                int(day_pnl_eur_minor) if day_pnl_eur_minor is not None else None,
            ),
        )

    @staticmethod
    def get_portfolio_snapshots(
        conn: sqlite3.Connection,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[dict[str, Any]]:
        """Retrieve daily portfolio snapshots ordered by snapshot_date ASC."""
        clauses = []
        params: list[Any] = []
        if start_date:
            clauses.append("snapshot_date >= ?")
            params.append(str(start_date))
        if end_date:
            clauses.append("snapshot_date <= ?")
            params.append(str(end_date))
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        query = f"""
        SELECT snapshot_date, market_value_eur_minor, cost_basis_eur_minor, day_pnl_eur_minor, fetched_at
        FROM portfolio_snapshots
        {where}
        ORDER BY snapshot_date ASC
        """
        rows = conn.execute(query, tuple(params)).fetchall()
        return [
            {
                "snapshot_date": r["snapshot_date"],
                "market_value_eur_minor": r["market_value_eur_minor"],
                "cost_basis_eur_minor": r["cost_basis_eur_minor"],
                "day_pnl_eur_minor": r["day_pnl_eur_minor"],
                "market_value_eur": (r["market_value_eur_minor"] or 0) / 100.0,
                "cost_basis_eur": (r["cost_basis_eur_minor"] or 0) / 100.0,
                "day_pnl_eur": (r["day_pnl_eur_minor"] / 100.0) if r["day_pnl_eur_minor"] is not None else None,
                "fetched_at": r["fetched_at"],
            }
            for r in rows
        ]

    @staticmethod
    def get_ticker_close_series(
        conn: sqlite3.Connection,
        tickers: list[str],
        days: int = 30,
    ) -> dict[str, list[float]]:
        """Retrieve historical ordered close series per ticker for sparkline rendering."""
        clean_tickers = [str(t).strip() for t in tickers if str(t).strip()]
        if not clean_tickers:
            return {}
        placeholders = ",".join("?" for _ in clean_tickers)
        query = f"""
        SELECT ticker, close, quote_date
        FROM market_quotes
        WHERE ticker IN ({placeholders})
          AND close IS NOT NULL AND close > 0
        ORDER BY quote_date ASC
        """
        rows = conn.execute(query, tuple(clean_tickers)).fetchall()
        series: dict[str, list[float]] = {t: [] for t in clean_tickers}
        for r in rows:
            t = r[0] if isinstance(r, (tuple, list)) else r["ticker"]
            val = float(r[1] if isinstance(r, (tuple, list)) else r["close"])
            if t in series:
                series[t].append(val)
        return {t: pts[-days:] if len(pts) > days else pts for t, pts in series.items()}

