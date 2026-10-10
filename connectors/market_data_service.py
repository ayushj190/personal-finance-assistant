import re
import sqlite3
import threading
import json
from pathlib import Path
import urllib.parse
from typing import Any
import yfinance as yf

from config import DB_PATH
from db import database


def update_quotes(tickers: list[str], db_conn: sqlite3.Connection | None = None) -> None:
    valid_tickers = [t for t in tickers if t and not t.startswith(
        "COPY:") and not t.startswith("ID_")]
    all_tickers = list(set(valid_tickers + ["EURUSD=X"]))
    if not all_tickers:
        return

    conn = db_conn or database.connect(DB_PATH)
    close_conn = db_conn is None

    try:
        data = yf.download(all_tickers, period="5d",
                           interval="1d", group_by="ticker", progress=False)
        quotes: list[dict[str, Any]] = []

        for t in all_tickers:
            try:
                sub = data[t] if len(all_tickers) > 1 else data
                sub = sub.dropna(subset=["Close"])
                if len(sub) == 0:
                    continue
                latest_close = float(sub["Close"].iloc[-1])
                prev_close = float(sub["Close"].iloc[-2]
                                   ) if len(sub) >= 2 else latest_close
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


_fx_cache: dict[str, tuple[float, float]] = {}  # currency -> (rate, timestamp)


def get_latest_fx_to_eur(currency: str, conn: sqlite3.Connection) -> float:
    """Returns multiplier to convert an amount in native `currency` into EUR."""
    curr = (currency or "EUR").upper().strip()
    if curr == "EUR":
        return 1.0

    import time
    now = time.time()
    if curr in _fx_cache:
        cached_rate, ts = _fx_cache[curr]
        if now - ts < 300:  # 5 min cache
            return cached_rate

    rate = 1.0
    fallback_rates = {
        "USD": 1.0 / 1.08,
        "GBP": 1.0 / 0.86,
        "CHF": 1.0 / 0.95,
        "JPY": 1.0 / 160.0,
        "TRY": 1.0 / 37.0,
    }

    ticker_map = {
        "USD": "EURUSD=X",
        "GBP": "EURGBP=X",
        "CHF": "EURCHF=X",
        "JPY": "EURJPY=X",
    }

    ticker = ticker_map.get(curr)
    if ticker:
        row = conn.execute(
            "SELECT close FROM market_quotes WHERE ticker = ? ORDER BY quote_date DESC LIMIT 1",
            (ticker,)
        ).fetchone()
        if row and row["close"] and row["close"] > 0:
            rate = 1.0 / float(row["close"])
        else:
            rate = fallback_rates.get(curr, 1.0)
    else:
        rate = fallback_rates.get(curr, 1.0)

    _fx_cache[curr] = (rate, now)
    return rate



def fetch_yfinance_quote(ticker: str) -> dict[str, Any] | None:
    try:
        t = yf.Ticker(ticker)
        info = t.info
        if not info or "regularMarketPrice" not in info:
            hist = t.history(period="1d")
            if hist.empty:
                return None
            return {"price": float(hist["Close"].iloc[-1])}

        return {
            "price": info.get("regularMarketPrice") or info.get("currentPrice"),
            "name": info.get("shortName", ticker),
            "currency": info.get("currency", "USD"),
            "52WeekHigh": info.get("fiftyTwoWeekHigh"),
            "52WeekLow": info.get("fiftyTwoWeekLow"),
            "sector": info.get("sector"),
            "industry": info.get("industry")
        }
    except Exception:
        return None

def _fetch_and_cache_domain(ticker: str, cache_path: Path):
    try:
        t = yf.Ticker(ticker)
        website = t.info.get("website")
        
        with open(cache_path, "r", encoding="utf-8") as f:
            domains = json.load(f)
            
        if website:
            domain = urllib.parse.urlparse(website).netloc
            if domain.startswith("www."):
                domain = domain[4:]
            domains[ticker] = domain
        else:
            domains[ticker] = ""
            
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(domains, f)
    except Exception:
        pass

def get_ticker_logo_url(ticker: str) -> str:
    cache_path = Path(__file__).resolve().parent.parent / "data" / "ticker_domains.json"
    if not cache_path.exists():
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump({}, f)
            
    try:
        with open(cache_path, "r", encoding="utf-8") as f:
            domains = json.load(f)
    except Exception:
        domains = {}
        
    fallback = f"https://ui-avatars.com/api/?name={ticker}&background=random&color=fff&rounded=true#.png"
    
    if ticker in domains:
        domain = domains[ticker]
        if domain:
            return f"https://logo.clearbit.com/{domain}?size=64#.png"
            
    # Launch background fetch
    if ticker not in domains:
        domains[ticker] = "" # mark as pending
        try:
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(domains, f)
        except Exception:
            pass
            
        threading.Thread(target=_fetch_and_cache_domain, args=(ticker, cache_path), daemon=True).start()
        
    return f"https://logo.clearbit.com/{ticker}.com?size=64#.png"

def classify_asset(ticker: str, name: str = "", yf_info: dict[str, Any] | None = None) -> tuple[str, str]:
    t_u = (ticker or "").upper()
    n_u = (name or "").upper()
    yf = yf_info or {}
    q_type = (yf.get("quoteType") or "").upper()
    yf_sec = yf.get("sector") or ""
    yf_ind = (yf.get("industry") or "").upper()

    # 1. Crypto
    crypto_symbols = {"BTC", "ETH", "SOL", "BNB", "LINK", "XLM", "XRP", "ADA", "DOGE", "DOT", "AVAX", "NEAR", "SUI", "TON"}
    if t_u in crypto_symbols or q_type == "CRYPTOCURRENCY" or any(c in n_u for c in ["BITCOIN", "ETHEREUM", "SOLANA", "CHAINLINK", "STELLAR", "RIPPLE"]):
        return "crypto", "Cryptocurrency"

    # 2. Gold & Precious Metals
    if any(g in n_u for g in ["PHYSICAL GOLD", "PHYSICAL METALS", "GOLD ETC", "GOLD ETF", "PRECIOUS METALS"]) or t_u in ["PPFB.DE", "GLD", "IAU", "BAR", "SGOL"]:
        return "etf", "Gold & Metals"

    # 3. ETF detection
    is_etf = (
        q_type in ("ETF", "MUTUALFUND")
        or bool(re.search(r"\b(ETF|UCITS|ETC|ISHARES|VANGUARD|SPDR|INVESCO)\b", n_u))
        or "INDEX FUND" in n_u
        or "URANIUM" in n_u
        or any(k in t_u for k in ["UCITS", "ETF"])
    )

    # 4. Aerospace & Defense
    if "AEROSPACE & DEFENSE" in yf_ind or t_u in ["RHM.DE", "RKLB", "LMT", "RTX", "NOC", "GD", "BA"] or any(d in n_u for d in ["RHEINMETALL", "ROCKET LAB"]):
        return "stock", "Defense & Aerospace"

    # 5. Energy (including Clean Energy & Uranium)
    if "ENERGY" in n_u or "URANIUM" in n_u or yf_sec == "Energy" or t_u in ["SPYN.DE", "URA", "VK.PA", "RRC", "TE.PA", "XLE", "XOM", "CVX", "SHEL", "TTE", "BP"]:
        return ("etf" if is_etf else "stock"), "Energy"

    # 6. Bonds & Fixed Income
    if any(b in n_u for b in ["TREASURY", "BOND", "FIXED INCOME", "T-BILL"]) or t_u == "IB01.L":
        return "etf", "Bonds & Fixed Income"

    # 7. Technology
    if (
        any(tech in n_u for tech in ["INFORMATION TECHNOLOGY", "AI INFRASTRUCTURE", "SEMICONDUCTOR", "TECHNOLOGY", "SOFTWARE", "CYBERSECURITY"])
        or yf_sec == "Technology"
        or any(ind in yf_ind for ind in ["SEMICONDUCTOR", "SOFTWARE", "INTERNET", "INFORMATION TECH"])
        or t_u in ["IUIT.L", "AINF.NV", "ASTS", "SYM", "TSM", "WDC", "ASML", "AMZN", "NFLX", "0700.HK", "BABA"]
    ):
        return ("etf" if is_etf else "stock"), "Technology"

    # 8. Broad Market & Global ETFs
    if is_etf:
        return "etf", "Broad Market ETF"

    # 9. Financial Services
    if yf_sec in ["Financial Services", "Financials"] or any(f in yf_ind for f in ["BANK", "INSURANCE", "CREDIT"]) or t_u in ["BCS", "NWG", "KBC.BR", "RF.PA", "NU", "KLAR", "ETOR", "BRK.B", "PRU.L", "1299.HK", "PYPL"]:
        return "stock", "Financial Services"

    # 10. Healthcare
    if yf_sec == "Healthcare" or any(h in yf_ind for h in ["DRUG", "BIOTECH", "HEALTHCARE"]) or t_u in ["SAN.PA", "AZN"]:
        return "stock", "Healthcare"

    # 11. Real Estate
    if yf_sec == "Real Estate" or "REIT" in yf_ind or t_u in ["VNA.DE", "GFC.PA", "IWG.L"]:
        return "stock", "Real Estate"

    # 12. Industrials & Materials
    if yf_sec in ["Industrials", "Basic Materials"] or t_u in ["KGX.DE", "DG.PA", "VALE"]:
        return "stock", "Industrials & Materials"

    # 13. Consumer & Entertainment
    if yf_sec in ["Consumer Cyclical", "Consumer Defensive", "Communication Services"] or t_u in ["PDD", "JMT.LSB", "RKT.L", "UMG.NV"]:
        return "stock", "Consumer & Entertainment"

    sec = yf_sec if yf_sec and yf_sec != "Other" else "Other / Diversified"
    return ("etf" if is_etf else "stock"), sec


def _fetch_and_cache_metadata_thread(tickers: list[str], cache_path: Path, names_map: dict[str, str] | None = None):
    names = names_map or {}
    try:
        with open(cache_path, "r", encoding="utf-8") as f:
            meta = json.load(f)
    except Exception:
        meta = {}

    updated = False
    for t in tickers:
        name = names.get(t, "")
        try:
            info = yf.Ticker(t).info or {}
            short_name = info.get("shortName") or name
            atype, sec = classify_asset(t, short_name, info)
            meta[t] = {
                "quoteType": info.get("quoteType", "ETF" if atype == "etf" else "EQUITY"),
                "asset_type": atype,
                "sector": sec,
                "country": info.get("country", "Unknown"),
                "currency": info.get("currency", "USD"),
                "exchange": info.get("exchange", "Unknown")
            }
            updated = True
        except Exception:
            atype, sec = classify_asset(t, name)
            meta[t] = {
                "asset_type": atype,
                "sector": sec,
                "country": "Unknown",
                "currency": "USD",
                "exchange": "Unknown",
                "quoteType": "ETF" if atype == "etf" else "EQUITY"
            }
            updated = True

    if updated:
        try:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(meta, f, indent=2)
        except Exception:
            pass


def enrich_ticker_metadata(tickers: list[str], names_map: dict[str, str] | None = None) -> None:
    cache_path = Path(__file__).resolve().parent.parent / "data" / "ticker_metadata.json"
    try:
        if cache_path.exists():
            with open(cache_path, "r", encoding="utf-8") as f:
                meta = json.load(f)
        else:
            meta = {}
    except Exception:
        meta = {}

    # Identify missing or stale/unclassified entries
    missing = [
        t for t in tickers 
        if t and not t.startswith("ID_") and not t.startswith("COPY:")
        and (t not in meta or meta[t].get("status") == "pending" or meta[t].get("sector") in ("Unknown", "Other", None))
    ]
    if missing:
        for m in missing:
            if m not in meta:
                meta[m] = {"status": "pending"}
        try:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(meta, f, indent=2)
        except Exception:
            pass

        threading.Thread(target=_fetch_and_cache_metadata_thread, args=(missing, cache_path, names_map), daemon=True).start()
