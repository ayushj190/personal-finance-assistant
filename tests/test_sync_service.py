import sqlite3
import unittest
from services.sync_service import sync_all


class TestSyncService(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        with open("db/schema.sql", "r", encoding="utf-8") as f:
            self.conn.executescript(f.read())
        with open("db/seed.sql", "r", encoding="utf-8") as f:
            self.conn.executescript(f.read())

    def tearDown(self):
        self.conn.close()

    @unittest.mock.patch("services.secrets_vault.get", return_value=None)
    def test_sync_all_smoke(self, _mock_vault_get):
        # With no connectors configured, sync_all should complete gracefully
        res = sync_all(self.conn)
        self.assertIn("connectors", res)
        self.assertIn("total_inserted", res)
        self.assertEqual(res["total_inserted"], 0)


if __name__ == "__main__":
    unittest.main()
