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
        row = self.conn.execute("SELECT version FROM schema_version").fetchone()
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

        h1 = dedup_hash("2026-03-01", -350, "EUR", "Coffee Shop", occurrence_idx=0)
        h2 = dedup_hash("2026-03-01", -350, "EUR", "Coffee Shop", occurrence_idx=1)

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


if __name__ == "__main__":
    unittest.main()
