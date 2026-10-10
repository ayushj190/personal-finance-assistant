import unittest
import os
import tempfile
import sqlite3

from db.database import migrate, connect
from services.dividend_service import calculate_dividend_projections, get_estimated_yield
from services.budget_service import (
    init_budget_table,
    set_category_budget,
    calculate_budget_variance,
    calculate_12_month_runway_forecast,
)
from services.tax_report_service import generate_dutch_tax_statement
from connectors.market_data_service import get_latest_fx_to_eur


class TestNewFeatures(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_features.db")
        migrate(self.db_path)
        self.conn = connect(self.db_path)

    def tearDown(self):
        self.conn.close()
        self.temp_dir.cleanup()

    def test_dividend_projections(self):
        # Insert a sample account first to satisfy foreign key
        self.conn.execute(
            """
            INSERT INTO accounts (id, provider, institution, external_id, name, currency, asset_class, is_active)
            VALUES (101, 'manual', 'Test Broker', 'test_inv_101', 'Test Broker Inv', 'EUR', 'investment', 1)
            """
        )
        # Insert a sample holding into holdings
        self.conn.execute(
            """
            INSERT OR REPLACE INTO holdings (id, account_id, ticker, name, asset_type, quantity, cost_basis_minor, currency, updated_at)
            VALUES (999, 101, 'VWCE.DE', 'Vanguard FTSE All-World', 'etf', 10.0, 100000, 'EUR', datetime('now'))
            """
        )
        self.conn.commit()


        # Check yield resolution
        vwce_yield = get_estimated_yield("VWCE.DE", "etf", "Broad Market ETF")
        self.assertEqual(vwce_yield, 1.5)

        div_res = calculate_dividend_projections(self.conn)
        self.assertIn("projected_annual_dividends_eur", div_res)
        self.assertIn("monthly_distribution", div_res)
        self.assertEqual(len(div_res["monthly_distribution"]), 12)

    def test_budget_service(self):
        init_budget_table(self.conn)
        # Find a category ID
        cat = self.conn.execute("SELECT id FROM categories WHERE kind = 'fixed' LIMIT 1").fetchone()
        self.assertIsNotNone(cat)
        cat_id = cat["id"]

        set_category_budget(self.conn, cat_id, 450.0)
        variance = calculate_budget_variance(self.conn)
        self.assertGreaterEqual(variance["total_budget_eur"], 450.0)
        self.assertIn("categories_df", variance)

        # Test runway forecast
        forecast = calculate_12_month_runway_forecast(
            liquid_cash=10000.0,
            projected_monthly_income=3000.0,
            current_burn_rate=2500.0,
            budgeted_burn_rate=2000.0,
            horizon_months=12,
        )
        self.assertEqual(len(forecast), 12)
        # Budgeted trajectory should save more than current burn
        self.assertGreater(forecast[-1]["budgeted_spend_balance_eur"], forecast[-1]["current_spend_balance_eur"])

    def test_tax_report_service(self):
        report = generate_dutch_tax_statement(year=2024, conn=self.conn)
        self.assertIn("report_df", report)
        self.assertIn("csv_content", report)
        self.assertIn("Box 1 - Gross Annual Income", report["csv_content"])
        self.assertIn("Box 3 - Tax Due", report["csv_content"])
        self.assertGreater(len(report["report_df"]), 5)

    def test_multi_currency_fx(self):
        eur_rate = get_latest_fx_to_eur("EUR", self.conn)
        self.assertEqual(eur_rate, 1.0)

        usd_rate = get_latest_fx_to_eur("USD", self.conn)
        self.assertGreater(usd_rate, 0.5)

        gbp_rate = get_latest_fx_to_eur("GBP", self.conn)
        self.assertGreater(gbp_rate, 0.5)

        chf_rate = get_latest_fx_to_eur("CHF", self.conn)
        self.assertGreater(chf_rate, 0.5)


if __name__ == "__main__":
    unittest.main()
