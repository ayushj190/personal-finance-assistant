from datetime import date, datetime
import sqlite3
from typing import Any
import yfinance as yf

from config import DB_PATH
from db import database


def update_quotes(tickers: list[str], db_conn: sqlite3.Connection | None = None) -> None:
    valid_tickers = [t for t in tickers if t and not t.startswith("COPY:") and not t.startswith("ID_")]
    all_tickers = list(set(valid_tickers + ["EURUSD=X"]))
    if not all_tickers:
        return

    conn = db_conn or database.connect(DB_PATH)
    close_conn = db_conn is None

    try:
        data = yf.download(all_tickers, period="5d", interval="1d", group_by="ticker", progress=False)
        quotes: list[dict[str, Any]] = []

        for t in all_tickers:
            try:
                sub = data[t] if len(all_tickers) > 1 else data
                sub = sub.dropna(subset=["Close"])
                if len(sub) == 0:
                    continue
                latest_close = float(sub["Close"].iloc[-1])
                prev_close = float(sub["Close"].iloc[-2]) if len(sub) >= 2 else latest_close
                quote_date = str(sub.index[-1].date())
                quotes.append(
                    {
                        "ticker": t,
                        "quote_date": quote_date,
                        "close": latest_close,
                        "prev_close": prev_close,
                        "currency": "USD" if t != "EURUSD=X" and not t.endswith(".DE") else "EUR",
                    }
                )
            except Exception:
                continue

        if quotes:
            database.upsert_market_quotes(conn, quotes)
    except Exception:
        pass
    finally:
        if close_conn:
            conn.close()


def get_latest_fx_to_eur(currency: str, conn: sqlite3.Connection) -> float:
    if currency == "EUR":
        return 1.0
    if currency == "USD":
        row = conn.execute(
            "SELECT close FROM market_quotes WHERE ticker = 'EURUSD=X' ORDER BY quote_date DESC LIMIT 1"
        ).fetchone()
        if row and row["close"] and row["close"] > 0:
            return 1.0 / float(row["close"])
        return 1.0 / 1.08  # reasonable fallback
    return 1.0
