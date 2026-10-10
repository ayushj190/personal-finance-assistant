import sqlite3
from typing import Any
import pandas as pd

from config import DB_PATH
from db import database

# Estimated baseline dividend yields by sector/type for projection models
ESTIMATED_YIELDS = {
    "Broad Market ETF": 1.6,
    "Dividend & Value ETF": 3.8,
    "Technology": 0.8,
    "Financial Services": 3.2,
    "Consumer Defensive": 2.6,
    "Energy": 4.1,
    "Healthcare": 2.2,
    "Real Estate": 4.5,
    "Utilities": 3.9,
    "Defense & Aerospace": 1.4,
    "Gold & Metals": 0.0,
    "Cryptocurrency": 0.0,
    "bond": 3.2,
    "etf": 1.7,
    "stock": 2.1,
    "crypto": 0.0,
    "commodity": 0.0,
}

KNOWN_TICKER_YIELDS = {
    "VWCE.DE": 1.5,
    "IWDA.AS": 1.4,
    "VUSA.AS": 1.3,
    "AAPL": 0.5,
    "MSFT": 0.7,
    "O": 5.4,
    "MAIN": 6.8,
    "SCHD": 3.4,
    "JNJ": 3.1,
    "PG": 2.4,
    "KO": 3.0,
    "PEP": 2.9,
    "ASML.AS": 1.1,
    "INGA.AS": 6.5,
    "ABN.AS": 7.0,
    "UNA.AS": 3.6,
}


def get_estimated_yield(ticker: str, asset_type: str, sector: str | None = None) -> float:
    """Return estimated percentage dividend yield for an asset."""
    t_clean = (ticker or "").upper().strip()
    if t_clean in KNOWN_TICKER_YIELDS:
        return KNOWN_TICKER_YIELDS[t_clean]

    if asset_type in ("crypto", "commodity"):
        return 0.0

    if sector and sector in ESTIMATED_YIELDS:
        return ESTIMATED_YIELDS[sector]

    return ESTIMATED_YIELDS.get(asset_type, 1.8)


def calculate_dividend_projections(conn: sqlite3.Connection | None = None) -> dict[str, Any]:
    """Calculates dividend projections and income forecast across current holdings."""
    close_conn = False
    if conn is None:
        conn = database.connect(DB_PATH)
        close_conn = True

    try:
        holdings = conn.execute(
            """
            SELECT ticker, name, asset_type, sector, value_eur
            FROM v_holdings
            WHERE value_eur > 0
            """
        ).fetchall()

        rows = []
        total_value = 0.0
        total_annual_div = 0.0

        for h in holdings:
            val = float(h["value_eur"] or 0.0)
            if val <= 0:
                continue
            total_value += val
            y_pct = get_estimated_yield(h["ticker"], h["asset_type"], h["sector"])
            annual_div = val * (y_pct / 100.0)
            total_annual_div += annual_div

            rows.append({
                "ticker": h["ticker"],
                "name": h["name"] or h["ticker"],
                "asset_type": h["asset_type"].upper(),
                "sector": h["sector"] or "Other",
                "value_eur": val,
                "yield_pct": y_pct,
                "annual_dividend_eur": annual_div,
            })

        avg_yield = (total_annual_div / total_value * 100.0) if total_value > 0 else 0.0
        monthly_avg = total_annual_div / 12.0

        # Estimated monthly payout schedule (quarterly distributions peak in Mar/Jun/Sep/Dec)
        months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        quarterly_weights = [0.06, 0.05, 0.14, 0.07, 0.06, 0.15, 0.06, 0.06, 0.14, 0.06, 0.05, 0.10]
        monthly_distribution = [
            {"month": m, "payout_eur": round(total_annual_div * w, 2)}
            for m, w in zip(months, quarterly_weights)
        ]

        df = pd.DataFrame(rows)
        if not df.empty:
            df = df.sort_values(by="annual_dividend_eur", ascending=False)

        return {
            "total_portfolio_value_eur": total_value,
            "projected_annual_dividends_eur": total_annual_div,
            "average_dividend_yield_pct": avg_yield,
            "monthly_average_eur": monthly_avg,
            "monthly_distribution": monthly_distribution,
            "holdings_df": df,
        }
    finally:
        if close_conn:
            conn.close()
