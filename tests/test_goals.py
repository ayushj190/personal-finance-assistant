import sqlite3
import unittest
import os
import tempfile

class TestGoals(unittest.TestCase):
    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp()
        self.conn = sqlite3.connect(self.db_path)
        # Setup minimal schema
        self.conn.executescript("""
            CREATE TABLE accounts (
                id INTEGER PRIMARY KEY,
                provider TEXT NOT NULL,
                institution TEXT NOT NULL,
                name TEXT NOT NULL,
                currency TEXT NOT NULL,
                asset_class TEXT NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 1
            );
            CREATE TABLE goals (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                target_amount REAL NOT NULL,
                target_date TEXT,
                account_id INTEGER REFERENCES accounts(id) ON DELETE SET NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            CREATE TABLE account_snapshots (
                account_id INTEGER NOT NULL REFERENCES accounts(id),
                snapshot_date TEXT NOT NULL,
                balance_minor INTEGER NOT NULL,
                balance_eur_minor INTEGER NOT NULL,
                PRIMARY KEY (account_id, snapshot_date)
            );
        """)
        
        # Insert test data
        self.conn.execute("INSERT INTO accounts (id, provider, institution, name, currency, asset_class) VALUES (1, 'manual', 'Bank', 'Savings', 'EUR', 'cash')")
        self.conn.execute("INSERT INTO account_snapshots (account_id, snapshot_date, balance_minor, balance_eur_minor) VALUES (1, '2023-01-01', 500000, 500000)")
        self.conn.execute("INSERT INTO goals (name, target_amount, account_id) VALUES ('New Car', 10000.0, 1)")
        self.conn.commit()

    def tearDown(self):
        self.conn.close()
        os.close(self.db_fd)
        os.remove(self.db_path)

    def test_goals_inserted_correctly(self):
        goals = self.conn.execute("SELECT * FROM goals").fetchall()
        self.assertEqual(len(goals), 1)
        self.assertEqual(goals[0][1], 'New Car')
        self.assertEqual(goals[0][2], 10000.0)

    def test_goals_join_with_accounts(self):
        res = self.conn.execute('''
            SELECT g.name, a.name as account_name, 
                   (SELECT balance_eur_minor/100.0 FROM account_snapshots s WHERE s.account_id = g.account_id ORDER BY snapshot_date DESC LIMIT 1) as current_balance
            FROM goals g LEFT JOIN accounts a ON a.id = g.account_id
        ''').fetchone()
        
        self.assertIsNotNone(res)
        self.assertEqual(res[0], 'New Car')
        self.assertEqual(res[1], 'Savings')
        self.assertEqual(res[2], 5000.0) # 500000 minor = 5000.0

if __name__ == '__main__':
    unittest.main()
