import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import unittest
from unittest.mock import patch

from core.config import DATA_DIR


class TestDemoMode(unittest.TestCase):
    def test_demo_config_env(self):
        # Test that running with PFA_DEMO=1 resolves to demo.db
        cmd = [
            sys.executable,
            "-c",
            "import os; os.environ['PFA_DEMO'] = '1'; from core.config import DB_PATH, DEMO, VAULT_PATH; "
            "print(DEMO, DB_PATH.name, VAULT_PATH)",
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        self.assertIn("True demo.db None", res.stdout)

    def test_seed_demo_deterministic(self):
        demo_db = DATA_DIR / "demo.db"
        self.assertTrue(demo_db.exists())

        conn = sqlite3.connect(str(demo_db))
        try:
            accounts = conn.execute("SELECT COUNT(*) FROM accounts").fetchone()[0]
            txs = conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
            holdings = conn.execute("SELECT COUNT(*) FROM holdings").fetchone()[0]
            closed = conn.execute("SELECT COUNT(*) FROM holdings WHERE status = 'closed'").fetchone()[0]

            self.assertEqual(accounts, 3)
            self.assertGreaterEqual(txs, 500)
            self.assertEqual(holdings, 15)
            self.assertGreaterEqual(closed, 3)
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
