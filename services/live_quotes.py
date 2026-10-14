"""Live market quotes service with Europe/Amsterdam market hours gate.

Provides batched intraday quote polling via yfinance with timeout protection,
session state caching, and thread-safe fallback to stored SQLite market quotes.
"""

from __future__ import annotations

import logging
import sqlite3
import time
from datetime import datetime, time as dtime
from typing import Any
from zoneinfo import ZoneInfo
import pandas as pd
import yfinance as yf

from core.config import DB_PATH
from db import database
from db.repositories import HoldingRepository

logger = logging.getLogger(__name__)

AMSTERDAM_TZ = ZoneInfo("Europe/Amsterdam")
MARKET_OPEN_TIME = dtime(9, 0)
MARKET_CLOSE_TIME = dtime(22, 0)
DEFAULT_POLL_TIMEOUT_SECS = 8.0


def market_session_state(now: datetime | None = None) -> str:
    """Return 'open' or 'closed' for Europe/Amsterdam market window.

    Open on weekdays (Monday=0 to Friday=4) between 09:00 and 22:00 Amsterdam time.
    Uses zoneinfo so daylight saving shifts are handled accurately without drift.
    """
    dt = (now or datetime.now(AMSTERDAM_TZ)).astimezone(AMSTERDAM_TZ)
    # Weekday check: Monday (0) to Friday (4)
    if dt.weekday() > 4:
        return "closed"
    current_time = dt.time()
    if MARKET_OPEN_TIME <= current_time < MARKET_CLOSE_TIME:
        return "open"
    return "closed"


def market_clock(now: datetime | None = None, conn: sqlite3.Connection | None = None) -> dict[str, Any]:
    """Return session state, window bounds, and latest available price date."""
    dt = (now or datetime.now(AMSTERDAM_TZ)).astimezone(AMSTERDAM_TZ)
    state = market_session_state(dt)

    last_price_date = dt.strftime("%Y-%m-%d")
    close_db = False
    db_conn = conn
    if db_conn is None:
        try:
            db_conn = database.connect_readonly(DB_PATH)
            close_db = True
        except Exception:
            db_conn = None

    if db_conn is not None:
        try:
            row = db_conn.execute("SELECT MAX(quote_date) AS max_date FROM market_quotes").fetchone()
            if row and row["max_date"]:
                last_price_date = str(row["max_date"])
        except Exception:
            pass
        finally:
            if close_db:
                db_conn.close()

    return {
        "session_state": state,
        "is_open": state == "open",
        "current_time_amsterdam": dt.strftime("%H:%M:%S"),
        "open_time": "09:00",
        "close_time": "22:00",
        "last_price_date": last_price_date,
    }


def refresh_live_quotes(
    tickers: list[str],
    now: datetime | None = None,
    session_cache: dict[str, Any] | None = None,
    timeout: float = DEFAULT_POLL_TIMEOUT_SECS,
) -> dict[str, Any]:
    """Fetch 1-minute intraday quotes for valid tickers, updating the session cache.

    If market is closed, returns existing cache without making network calls.
    If poll fails or times out, keeps existing cache and marks last_poll_failed=True.
    """
    dt = (now or datetime.now(AMSTERDAM_TZ)).astimezone(AMSTERDAM_TZ)
    cache = dict(session_cache or {})
    quote_entries: dict[str, dict[str, Any]] = dict(cache.get("quotes", {}))

    # Guard: Outside market hours, freeze and do not poll
    state = market_session_state(dt)
    if state == "closed":
        return {
            "quotes": quote_entries,
            "last_refresh_ts": cache.get("last_refresh_ts"),
            "last_poll_failed": False,
            "session_state": "closed",
        }

    # Clean ticker list: ignore empty, COPY:, and ID_ pseudo-tickers
    valid_tickers = sorted(
        {
            str(t).strip()
            for t in tickers
            if str(t).strip() and not str(t).startswith(("COPY:", "ID_"))
        }
    )
    if not valid_tickers:
        return {
            "quotes": quote_entries,
            "last_refresh_ts": cache.get("last_refresh_ts") or time.time(),
            "last_poll_failed": False,
            "session_state": "open",
        }

    fetch_ts = dt.isoformat()
    now_epoch = time.time()

    # Guard: If session cache was refreshed within last 30s and has entries, reuse it
    last_refresh = float(cache.get("last_refresh_ts") or 0.0)
    if quote_entries and (now_epoch - last_refresh) < 30.0:
        return {
            "quotes": quote_entries,
            "last_refresh_ts": last_refresh,
            "last_poll_failed": False,
            "session_state": "open",
        }

    try:
        # Download 1-minute bars with explicit request timeout
        df = yf.download(
            valid_tickers,
            period="1d",
            interval="1m",
            group_by="ticker",
            progress=False,
            timeout=timeout,
        )

        if df is None or df.empty:
            logger.warning("Live quote poll returned empty frame.")
            return {
                "quotes": quote_entries,
                "last_refresh_ts": cache.get("last_refresh_ts"),
                "last_poll_failed": True,
                "session_state": "open",
            }

        # Parse per-ticker closes
        for ticker in valid_tickers:
            try:
                sub = df[ticker] if len(valid_tickers) > 1 else df
                if isinstance(sub, pd.DataFrame) and "Close" in sub.columns:
                    closes = sub["Close"].dropna()
                    if not closes.empty:
                        price = float(closes.iloc[-1])
                        if price > 0:
                            prev_entry = quote_entries.get(ticker, {})
                            curr = prev_entry.get("currency")
                            if not curr:
                                if ticker.endswith(".DE"):
                                    curr = "EUR"
                                elif ticker.endswith(".L"):
                                    curr = "GBP"
                                else:
                                    curr = "USD"
                            quote_entries[ticker] = {
                                "price": price,
                                "prev_close": prev_entry.get("prev_close"),
                                "currency": curr,
                                "fetched_at": fetch_ts,
                                "source": "yfinance_1m",
                            }
            except Exception as e:
                logger.debug("Failed parsing quote for ticker %s: %s", ticker, e)
                continue

        return {
            "quotes": quote_entries,
            "last_refresh_ts": now_epoch,
            "last_poll_failed": False,
            "session_state": "open",
        }
    except Exception as exc:
        logger.warning("Live quote poll failed: %s", exc)
        return {
            "quotes": quote_entries,
            "last_refresh_ts": cache.get("last_refresh_ts"),
            "last_poll_failed": True,
            "session_state": "open",
        }


def cached_quotes(conn: sqlite3.Connection | None = None) -> dict[str, Any]:
    """Guarded accessor for current quotes. Safe to call off the script thread.

    If run inside an active Streamlit session, returns session cache.
    Otherwise (or if cache is empty), falls back to stored closes in market_quotes.
    """
    quotes: dict[str, dict[str, Any]] = {}
    last_refresh_ts: float | None = None
    last_poll_failed: bool = False
    session_state: str = market_session_state()

    # Try Streamlit session state if available on current thread
    try:
        import streamlit as st
        from ui import state

        if hasattr(st, "session_state"):
            s_cache = state.get(state.K.LIVE_QUOTE_CACHE)
            if isinstance(s_cache, dict) and s_cache.get("quotes"):
                return {
                    "quotes": s_cache.get("quotes", {}),
                    "last_refresh_ts": s_cache.get("last_refresh_ts"),
                    "last_poll_failed": bool(s_cache.get("last_poll_failed", False)),
                    "session_state": s_cache.get("session_state", session_state),
                }
    except Exception:
        pass

    # Fallback to stored closes in market_quotes
    should_close = False
    db_conn = conn
    if db_conn is None:
        try:
            db_conn = database.connect_readonly(DB_PATH)
            should_close = True
        except Exception:
            db_conn = None

    if db_conn is not None:
        try:
            if db_conn.row_factory is None:
                db_conn.row_factory = sqlite3.Row
            query = """
            SELECT q.ticker, q.close, q.prev_close, q.currency, q.quote_date, q.fetched_at
            FROM market_quotes q
            WHERE q.quote_date = (SELECT MAX(m.quote_date) FROM market_quotes m WHERE m.ticker = q.ticker);
            """
            rows = db_conn.execute(query).fetchall()
            for r in rows:
                t = r["ticker"]
                price = float(r["close"] or 0.0)
                if price > 0:
                    quotes[t] = {
                        "price": price,
                        "prev_close": float(r["prev_close"] or price),
                        "currency": r["currency"] or "EUR",
                        "fetched_at": r["fetched_at"] or r["quote_date"],
                        "source": "stored_close",
                    }
        except Exception as e:
            logger.error("Error reading stored quotes fallback: %s", e)
        finally:
            if should_close:
                db_conn.close()

    return {
        "quotes": quotes,
        "last_refresh_ts": last_refresh_ts,
        "last_poll_failed": last_poll_failed,
        "session_state": session_state,
    }
