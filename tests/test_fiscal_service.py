import unittest
from datetime import date

from core.config import DB_PATH
from db import database
from services.fiscal_service import (
    get_default_salary_day,
    get_fiscal_salary_day,
    set_fiscal_salary_day,
    get_fiscal_month_range,
    get_fiscal_month_for_date,
    format_fiscal_month_label,
)
from services.budget_service import (
    init_budget_table,
    calculate_budget_variance,
)


class TestFiscalService(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        database.migrate()
        cls.conn = database.connect(DB_PATH)

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()

    def test_default_salary_day_detection(self):
        day = get_default_salary_day(self.conn)
        # Should be an integer between 1 and 31
        self.assertIsInstance(day, int)
        self.assertGreaterEqual(day, 1)
        self.assertLessEqual(day, 31)
        # In current test database, salary transaction on 2026-09-23 is largest
        self.assertEqual(day, 23)

    def test_get_and_set_fiscal_salary_day(self):
        # Save custom day
        set_fiscal_salary_day(self.conn, 15)
        self.assertEqual(get_fiscal_salary_day(self.conn), 15)

        # Restore detected day
        default_day = get_default_salary_day(self.conn)
        set_fiscal_salary_day(self.conn, default_day)
        self.assertEqual(get_fiscal_salary_day(self.conn), default_day)

    def test_fiscal_month_date_ranges(self):
        # Day 23 cycle
        s_date, e_date = get_fiscal_month_range(2026, 9, 23)
        self.assertEqual(s_date, date(2026, 9, 23))
        self.assertEqual(e_date, date(2026, 10, 22))

        # Year boundary December -> January
        s_dec, e_dec = get_fiscal_month_range(2026, 12, 23)
        self.assertEqual(s_dec, date(2026, 12, 23))
        self.assertEqual(e_dec, date(2027, 1, 22))

        # Standard calendar month when salary_day == 1
        s_1, e_1 = get_fiscal_month_range(2026, 9, 1)
        self.assertEqual(s_1, date(2026, 9, 1))
        self.assertEqual(e_1, date(2026, 9, 30))

        # Day 31 clamped in shorter month (Feb)
        s_jan, e_jan = get_fiscal_month_range(2026, 1, 31)
        self.assertEqual(s_jan, date(2026, 1, 31))
        self.assertEqual(e_jan, date(2026, 2, 27))

    def test_fiscal_month_for_date(self):
        # If salary day is 23:
        # 2026-09-23 is >= 23 -> 2026-09
        self.assertEqual(get_fiscal_month_for_date("2026-09-23", 23), "2026-09")
        # 2026-10-05 is < 23 -> belongs to 2026-09
        self.assertEqual(get_fiscal_month_for_date("2026-10-05", 23), "2026-09")
        # 2026-09-15 is < 23 -> belongs to 2026-08
        self.assertEqual(get_fiscal_month_for_date("2026-09-15", 23), "2026-08")

        # When salary day is 1:
        self.assertEqual(get_fiscal_month_for_date("2026-09-15", 1), "2026-09")

    def test_format_fiscal_month_label(self):
        lbl = format_fiscal_month_label("2026-09", 23)
        self.assertIn("23 Sep", lbl)
        self.assertIn("22 Oct", lbl)

    def test_custom_category_creation(self):
        test_cat = "Test Custom Pet"
        existing = self.conn.execute("SELECT id FROM categories WHERE name = ?", (test_cat,)).fetchone()
        if existing:
            self.conn.execute("DELETE FROM categories WHERE id = ?", (existing["id"],))

        new_id = database.add_custom_category(self.conn, test_cat, "discretionary")
        self.assertIsInstance(new_id, int)

        row = self.conn.execute("SELECT * FROM categories WHERE id = ?", (new_id,)).fetchone()
        self.assertEqual(row["name"], test_cat)
        self.assertEqual(row["kind"], "discretionary")
        self.assertIsNone(row["parent_id"])

        # Clean up
        with self.conn:
            self.conn.execute("DELETE FROM categories WHERE id = ?", (new_id,))

    def test_budget_variance_fiscal_range(self):
        init_budget_table(self.conn)
        s_date, e_date = get_fiscal_month_range(2026, 9, 23)
        res = calculate_budget_variance(
            self.conn,
            year_month="2026-09",
            start_date=s_date.isoformat(),
            end_date=e_date.isoformat(),
        )
        self.assertIn("categories_df", res)
        self.assertIn("total_budget_eur", res)
        self.assertIn("total_spent_eur", res)


if __name__ == "__main__":
    unittest.main()
