"""Shared ticker to TradingView symbol mapping.

Used by both the Dashboard ticker tape and the Investments watchlist so a
holding resolves to the same exchange-prefixed symbol everywhere (AC-9).
"""

TICKER_EXCHANGE_MAP = {
    ".AS": "EURONEXT:",
    ".PA": "EURONEXT:",
    ".BR": "EURONEXT:",
    ".LS": "EURONEXT:",
    ".L": "LSE:",
    ".DE": "XETR:",
    ".F": "FWB:",
    ".MI": "MIL:",
    ".MC": "BME:",
    ".SW": "SIX:",
}


def tradingview_symbol(ticker: str | None) -> str | None:
    """Map one holding ticker to a TradingView prefixed symbol, or None if unusable."""
    if not ticker or not isinstance(ticker, str):
        return None
    t_clean = ticker.strip()
    if not t_clean or t_clean.startswith("ID_") or "=" in t_clean or "^" in t_clean:
        return None

    # Crypto pairs: map to a price instrument, not the market cap series (AC-12).
    if t_clean.upper().endswith("-USD"):
        base = t_clean[: -len("-USD")].upper()
        if base:
            return f"BITSTAMP:{base}USD"

    if "." in t_clean:
        upper = t_clean.upper()
        for suffix, prefix in TICKER_EXCHANGE_MAP.items():
            if upper.endswith(suffix):
                return f"{prefix}{t_clean[:-len(suffix)]}"
        return None
    return t_clean
