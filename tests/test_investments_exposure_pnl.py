import sqlite3
import unittest
from unittest.mock import MagicMock, patch
import pandas as pd

from db.migrations.runner import run_migrations
from db.repositories.holding_repository import HoldingRepository
from services.portfolio import get_dimension_exposure_df
from ui.components import is_hidden


class TestInvestmentsExposurePnL(unittest.TestCase):
    def setUp(self):
        from streamlit.delta_generator import DeltaGenerator, context_dg_stack
        context_dg_stack.set((DeltaGenerator(),))
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        run_migrations(self.conn)

    def tearDown(self):
        from streamlit.delta_generator import DeltaGenerator, context_dg_stack
        context_dg_stack.set((DeltaGenerator(),))
        self.conn.close()

    def test_schema_migration_0006_columns_present(self):
        """AC-4: Holdings table has realized_pnl_minor and realized_proceeds_minor."""
        cur = self.conn.execute("PRAGMA table_info(holdings)")
        cols = {r["name"]: r["type"] for r in cur.fetchall()}
        self.assertIn("realized_pnl_minor", cols)
        self.assertIn("realized_proceeds_minor", cols)

    def test_realized_pnl_summary_and_closed_df(self):
        """AC-5, AC-6: HoldingRepository calculates realized P&L and returns closed positions."""
        # Insert a dummy account
        self.conn.execute(
            "INSERT INTO accounts (id, name, provider, institution, currency, asset_class) "
            "VALUES (1, 'Main Broker', 'etoro', 'eToro', 'EUR', 'investment')"
        )
        # Insert closed holdings: one EUR, one USD
        self.conn.execute(
            """
            INSERT INTO holdings (
                id, account_id, ticker, name, asset_type, quantity, currency,
                cost_basis_minor, realized_proceeds_minor, realized_pnl_minor,
                status, closed_at, updated_at
            ) VALUES
            (1, 1, 'ASML.AS', 'ASML Holding', 'stock', 0, 'EUR', 100000, 150000, 50000, 'closed', '2026-05-10T12:00:00', '2026-05-10'),
            (2, 1, 'NVDA', 'Nvidia', 'stock', 0, 'USD', 200000, 260000, 60000, 'closed', '2026-06-15T12:00:00', '2026-06-15')
            """
        )
        # Mock FX rate EURUSD=X = 1.25 (meaning 1 USD = 0.80 EUR)
        self.conn.execute(
            "INSERT INTO market_quotes (ticker, quote_date, close, currency, fetched_at) "
            "VALUES ('EURUSD=X', '2026-06-15', 1.25, 'USD', '2026-06-15T12:00:00')"
        )

        summary = HoldingRepository.get_realized_pnl_summary(self.conn)
        self.assertEqual(summary["closed_count"], 2)
        # ASML: pnl 500 EUR, proceeds 1500 EUR
        # NVDA: pnl 600 USD * (1/1.25) = 480 EUR, proceeds 2600 USD * (1/1.25) = 2080 EUR
        # Total pnl = 500 + 480 = 980 EUR
        # Total proceeds = 1500 + 2080 = 3580 EUR
        self.assertAlmostEqual(summary["realized_pnl_eur"], 980.0, places=2)
        self.assertAlmostEqual(summary["total_proceeds_eur"], 3580.0, places=2)

        closed_df = HoldingRepository.get_closed_holdings_df(self.conn)
        self.assertEqual(len(closed_df), 2)
        self.assertIn("ticker", closed_df.columns)
        self.assertIn("proceeds", closed_df.columns)
        self.assertIn("realized_pnl", closed_df.columns)
        self.assertIn("closed_date", closed_df.columns)
        self.assertEqual(closed_df.iloc[0]["closed_date"], "2026-06-15")

    def test_dimension_exposure_aggregation(self):
        """AC-1, AC-2: Aggregates exposure across sector, region, currency, asset class."""
        data = [
            {"ticker": "AAPL", "value_eur": 1000.0, "asset_type_display": "STOCK", "sector": "Technology", "region": "US", "currency": "USD"},
            {"ticker": "MSFT", "value_eur": 1000.0, "asset_type_display": "STOCK", "sector": "Technology", "region": "US", "currency": "USD"},
            {"ticker": "VWCE", "value_eur": 2000.0, "asset_type_display": "ETF", "sector": "Broad Market ETF", "region": "Global", "currency": "EUR"},
            {"ticker": "UNKNOWN", "value_eur": 1000.0, "asset_type_display": "OTHER", "sector": None, "region": "Unknown", "currency": None},
        ]
        df = pd.DataFrame(data)

        # 1. Sector
        sec_df = get_dimension_exposure_df(df, "Sector")
        self.assertEqual(len(sec_df), 3)  # Technology (2000), Broad Market ETF (2000), Other (1000)
        top_sec = sec_df.iloc[0]
        self.assertEqual(top_sec["weight_pct"], 40.0)

        # 2. Region
        reg_df = get_dimension_exposure_df(df, "Region")
        # US: 2000 (40%), Global: 2000 (40%), Other: 1000 (20%)
        other_row = reg_df[reg_df["bucket"] == "Other"]
        self.assertFalse(other_row.empty)
        self.assertEqual(other_row.iloc[0]["weight_pct"], 20.0)

        # 3. Currency
        cur_df = get_dimension_exposure_df(df, "Currency")
        self.assertIn("USD", cur_df["bucket"].values)
        self.assertIn("EUR", cur_df["bucket"].values)

        # 4. Asset Class
        asset_df = get_dimension_exposure_df(df, "Asset Class")
        self.assertIn("STOCK", asset_df["bucket"].values)
        self.assertIn("ETF", asset_df["bucket"].values)


if __name__ == "__main__":
    unittest.main()
