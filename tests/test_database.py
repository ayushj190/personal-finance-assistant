import os
import tempfile
import unittest

from db.database import connect, migrate, upsert_account, upsert_transactions
from services.normalization import dedup_hash


class TestDatabase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_finance.db")
        migrate(self.db_path)
        self.conn = connect(self.db_path)

    def tearDown(self):
        self.conn.close()
        self.temp_dir.cleanup()

    def test_migrate_idempotent(self):
        # Running migrate again should not raise errors
        migrate(self.db_path)
        row = self.conn.execute(
            "SELECT version FROM schema_version").fetchone()
        self.assertEqual(row["version"], 1)

    def test_dedup_and_occurrence_idx(self):
        acc_id = upsert_account(
            self.conn,
            {
                "provider": "manual",
                "institution": "ABN AMRO",
                "name": "Checking",
                "currency": "EUR",
                "asset_class": "cash",
                "external_id": "abn_test",
            },
        )

        h1 = dedup_hash("2026-03-01", -350, "EUR",
                        "Coffee Shop", occurrence_idx=0)
        h2 = dedup_hash("2026-03-01", -350, "EUR",
                        "Coffee Shop", occurrence_idx=1)

        txs = [
            {
                "account_id": acc_id,
                "dedup_hash": h1,
                "booking_date": "2026-03-01",
                "amount_minor": -350,
                "currency": "EUR",
                "amount_eur_minor": -350,
                "description_raw": "Coffee Shop",
                "merchant_normalized": "Coffee Shop",
                "source": "csv",
            },
            {
                "account_id": acc_id,
                "dedup_hash": h2,
                "booking_date": "2026-03-01",
                "amount_minor": -350,
                "currency": "EUR",
                "amount_eur_minor": -350,
                "description_raw": "Coffee Shop",
                "merchant_normalized": "Coffee Shop",
                "source": "csv",
            },
        ]

        # Insert two identical same-day coffees with different occurrence_idx
        inserted = upsert_transactions(self.conn, txs)
        self.assertEqual(inserted, 2)

        # Re-inserting the same transactions should insert 0 (idempotent dedup)
        reinserted = upsert_transactions(self.conn, txs)
        self.assertEqual(reinserted, 0)

    def test_v_holdings_currency_conversion(self):
        # Setup account, holding in USD and FX rate
        acc_id = upsert_account(
            self.conn,
            {
                "provider": "etoro",
                "institution": "eToro",
                "name": "eToro USD",
                "currency": "USD",
                "asset_class": "investment",
                "external_id": "etoro_test",
            },
        )
        # Cost basis: $1,000 USD (100,000 minor)
        self.conn.execute(
            """
            INSERT INTO holdings (account_id, ticker, name, asset_type, quantity, cost_basis_minor, currency, updated_at)
            VALUES (?, 'TEST', 'Test Asset', 'stock', 10.0, 100000, 'USD', '2026-10-05')
            """,
            (acc_id,),
        )
        # FX: 1 EUR = 1.25 USD -> 1 USD = 0.80 EUR. Quote: $120/share -> value = $1,200 USD -> €960 EUR
        self.conn.execute(
            "INSERT INTO market_quotes (ticker, quote_date, close, currency) VALUES ('EURUSD=X', '2026-10-05', 1.25, 'EUR')"
        )
        self.conn.execute(
            "INSERT INTO market_quotes (ticker, quote_date, close, currency) VALUES ('TEST', '2026-10-05', 120.0, 'USD')"
        )

        row = self.conn.execute(
            "SELECT * FROM v_holdings WHERE ticker = 'TEST'").fetchone()
        self.assertIsNotNone(row)
        # Cost: $1,000 / 1.25 = €800
        self.assertAlmostEqual(row["cost_basis"], 800.0, places=2)
        # Value: 10 * 120 / 1.25 = €960
        self.assertAlmostEqual(row["value_eur"], 960.0, places=2)
        # Unrealized PnL: €960 - €800 = +€160 (NOT €960 - $1,000 = -€40!)
        self.assertAlmostEqual(row["unrealized_pnl_eur"], 160.0, places=2)


if __name__ == "__main__":
    unittest.main()
