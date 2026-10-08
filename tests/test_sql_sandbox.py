import os
import tempfile
import unittest

from agent.sql_sandbox import execute_safe_query
from db.database import migrate


class TestSqlSandbox(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_finance.db")
        migrate(self.db_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_allowed_view_select(self):
        # v_transactions query should succeed
        df = execute_safe_query(
            "SELECT * FROM v_transactions LIMIT 5", db_path=self.db_path)
        self.assertIsNotNone(df)

    def test_multi_statement_rejection(self):
        with self.assertRaises(ValueError):
            execute_safe_query("SELECT 1; SELECT 2", db_path=self.db_path)

    def test_denial_of_destructive_queries(self):
        # DELETE should be blocked by authorizer
        with self.assertRaises(Exception):
            execute_safe_query("DELETE FROM accounts", db_path=self.db_path)

        # DROP TABLE should be blocked
        with self.assertRaises(Exception):
            execute_safe_query("DROP TABLE accounts", db_path=self.db_path)

        # PRAGMA should be blocked
        with self.assertRaises(Exception):
            execute_safe_query("PRAGMA journal_mode", db_path=self.db_path)


if __name__ == "__main__":
    unittest.main()
