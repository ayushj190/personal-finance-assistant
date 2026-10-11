import sqlite3
import unittest
from pathlib import Path

from db.database import add_custom_category


class TestCategoryDedup(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript("""
            CREATE TABLE categories (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                parent_id INTEGER,
                kind TEXT NOT NULL
            );

            CREATE TABLE category_budgets (
                category_id INTEGER PRIMARY KEY,
                monthly_limit_eur REAL NOT NULL
            );

            CREATE TABLE merchant_category_rules (
                merchant_normalized TEXT PRIMARY KEY,
                category_id INTEGER NOT NULL
            );

            CREATE TABLE transactions (
                id INTEGER PRIMARY KEY,
                category_id INTEGER,
                amount_eur_minor INTEGER NOT NULL
            );

            -- Simulate duplicate seed rows as seen in production
            INSERT INTO categories VALUES
                (103, 'Utility Bills', NULL, 'fixed'),
                (105, 'Utility Bills', NULL, 'fixed'),
                (107, 'Utility Bills', NULL, 'fixed'),
                (104, 'Sports & Leisure', NULL, 'discretionary'),
                (106, 'Sports & Leisure', NULL, 'discretionary'),
                (13, 'Electricity & Gas', 105, 'fixed'),  -- points to duplicate parent 105
                (14, 'Water', 107, 'fixed');              -- points to duplicate parent 107

            INSERT INTO transactions VALUES
                (1, 105, -5000),  -- points to duplicate category 105
                (2, 107, -3000);  -- points to duplicate category 107

            INSERT INTO category_budgets VALUES
                (103, 300.0),
                (105, 300.0);

            INSERT INTO merchant_category_rules VALUES
                ('Eneco', 105);
        """)

    def tearDown(self):
        self.conn.close()

    def test_migration_deduplicates_and_repoints(self):
        """Verify migration script consolidates duplicate categories and reassigns FK references."""
        migration_path = Path(__file__).resolve().parent.parent / "db" / "migrations" / "0003_dedup_categories_and_unique_indexes.sql"
        with open(migration_path, "r", encoding="utf-8") as f:
            sql = f.read()

        self.conn.executescript(sql)

        # 1. Categories deduped
        cats = self.conn.execute("SELECT id, name FROM categories WHERE name = 'Utility Bills'").fetchall()
        self.assertEqual(len(cats), 1)
        self.assertEqual(cats[0]["id"], 103)

        sports = self.conn.execute("SELECT id, name FROM categories WHERE name = 'Sports & Leisure'").fetchall()
        self.assertEqual(len(sports), 1)
        self.assertEqual(sports[0]["id"], 104)

        # 2. Child categories repointed to canonical parent 103
        children = self.conn.execute("SELECT id, name, parent_id FROM categories WHERE parent_id IS NOT NULL").fetchall()
        for child in children:
            self.assertEqual(child["parent_id"], 103)

        # 3. Transactions repointed to canonical 103
        txs = self.conn.execute("SELECT id, category_id FROM transactions").fetchall()
        for tx in txs:
            self.assertEqual(tx["category_id"], 103)

        # 4. Merchant rules repointed to 103
        rule = self.conn.execute("SELECT category_id FROM merchant_category_rules WHERE merchant_normalized = 'Eneco'").fetchone()
        self.assertEqual(rule["category_id"], 103)

        # 5. Unique index prevents new duplicate insertion
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute("INSERT INTO categories (id, name, parent_id, kind) VALUES (999, 'Utility Bills', NULL, 'fixed')")

    def test_add_custom_category_prevents_duplicate(self):
        """Verify add_custom_category returns existing ID when category already exists."""
        # 103 'Utility Bills' already exists
        existing_id = add_custom_category(self.conn, "Utility Bills", "fixed", parent_id=None)
        self.assertIn(existing_id, [103, 105, 107])

        # Subcategory check
        elec_id = add_custom_category(self.conn, "Electricity & Gas", "fixed", parent_id=105)
        self.assertEqual(elec_id, 13)


if __name__ == "__main__":
    unittest.main()
