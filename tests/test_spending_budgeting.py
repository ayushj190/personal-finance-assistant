import sqlite3
import unittest
from unittest.mock import patch


from db import database
from services.budget_service import (
    calculate_budget_variance,
    set_category_budget,
)
from ui.dialogs import assign_mortgage_dialog, set_category_budget_dialog
from ui.pages.spending import (
    _calculate_monthly_summary,
    _fetch_spending_df,
    _render_analytics_fragment,
    _render_budget_tracker_fragment,
    _render_kpi_ribbon,
)


class TestSpendingBudgetingStreamline(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row

        # Setup minimal schema matching SQLite database
        self.conn.executescript("""
            CREATE TABLE accounts (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                type TEXT NOT NULL DEFAULT 'checking'
            );

            CREATE TABLE categories (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                kind TEXT NOT NULL, -- fixed, discretionary, income, savings, transfer
                parent_id INTEGER REFERENCES categories(id)
            );

            CREATE TABLE category_budgets (
                category_id INTEGER PRIMARY KEY REFERENCES categories(id),
                monthly_limit_eur REAL NOT NULL
            );

            CREATE TABLE merchant_category_rules (
                merchant_normalized TEXT PRIMARY KEY,
                category_id INTEGER NOT NULL REFERENCES categories(id),
                source TEXT DEFAULT 'user',
                confidence REAL DEFAULT 1.0,
                hit_count INTEGER DEFAULT 1,
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE transactions (
                id INTEGER PRIMARY KEY,
                account_id INTEGER REFERENCES accounts(id),
                booking_date TEXT NOT NULL,
                amount_eur_minor INTEGER NOT NULL,
                description_raw TEXT,
                merchant_normalized TEXT,
                category_id INTEGER REFERENCES categories(id),
                category_source TEXT,
                is_internal_transfer INTEGER DEFAULT 0
            );

            CREATE TABLE liabilities (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                lender TEXT NOT NULL,
                loan_type TEXT DEFAULT 'annuity',
                original_principal_minor INTEGER DEFAULT 0,
                home_value_minor INTEGER,
                term_months INTEGER DEFAULT 360,
                start_date TEXT DEFAULT '2024-01-01',
                balance_override_minor INTEGER,
                balance_override_date TEXT,
                payment_match_pattern TEXT
            );

            CREATE TABLE liability_extra_payments (
                liability_id INTEGER REFERENCES liabilities(id),
                paid_date TEXT NOT NULL,
                amount_minor INTEGER NOT NULL,
                recalc TEXT DEFAULT 'lower_payment',
                PRIMARY KEY (liability_id, paid_date)
            );
        """)

        # Seed test account
        self.conn.execute("INSERT INTO accounts (id, name) VALUES (1, 'Main Checking')")

        # Seed categories hierarchy
        # Fixed tree: Housing -> Mortgage, Insurance
        self.conn.execute("INSERT INTO categories (id, name, kind, parent_id) VALUES (1, 'Housing', 'fixed', NULL)")
        self.conn.execute("INSERT INTO categories (id, name, kind, parent_id) VALUES (2, 'Mortgage', 'fixed', 1)")
        self.conn.execute("INSERT INTO categories (id, name, kind, parent_id) VALUES (3, 'Home Insurance', 'fixed', 1)")

        # Discretionary tree: Food & Dining -> Groceries, Restaurants
        self.conn.execute("INSERT INTO categories (id, name, kind, parent_id) VALUES (4, 'Food & Dining', 'discretionary', NULL)")
        self.conn.execute("INSERT INTO categories (id, name, kind, parent_id) VALUES (5, 'Groceries', 'discretionary', 4)")
        self.conn.execute("INSERT INTO categories (id, name, kind, parent_id) VALUES (6, 'Restaurants', 'discretionary', 4)")

        # Non-spending categories
        self.conn.execute("INSERT INTO categories (id, name, kind, parent_id) VALUES (7, 'Salary', 'income', NULL)")
        self.conn.execute("INSERT INTO categories (id, name, kind, parent_id) VALUES (8, 'Investment Savings', 'savings', NULL)")
        self.conn.execute("INSERT INTO categories (id, name, kind, parent_id) VALUES (9, 'Internal Transfer', 'transfer', NULL)")

        # Uncategorized category explicitly present
        self.conn.execute("INSERT INTO categories (id, name, kind, parent_id) VALUES (10, 'Uncategorized', 'discretionary', NULL)")
        calculate_budget_variance.clear()

    def tearDown(self):
        calculate_budget_variance.clear()
        self.conn.close()

    # -------------------------------------------------------------------------
    # AC-1, AC-2, AC-7: Summation Identity & Uncategorized Classification
    # -------------------------------------------------------------------------

    def test_strict_summation_identity_and_uncategorized_isolation(self):
        """AC-1, AC-2, AC-7: Verify Total = Fixed + Discretionary + Uncategorized exact identity."""
        # Insert various transactions in integer minor units (cents)
        txs = [
            # Fixed expenses: Total -€1,350.50
            (1, "2026-03-05", -120050, "Mortgage payment", "ABN AMRO", 2, 0),
            (1, "2026-03-10", -15000, "Home insurance", "Centraal Beheer", 3, 0),
            # Discretionary expenses: Total -€127.35
            (1, "2026-03-12", -8525, "Supermarket", "Albert Heijn", 5, 0),
            (1, "2026-03-15", -4210, "Dinner", "Pizzeria", 6, 0),
            # Uncategorized expenses (category_id NULL and category 'Uncategorized'): Total -€80.00
            (1, "2026-03-18", -5500, "Unknown merchant", "Unknown Store", None, 0),
            (1, "2026-03-20", -2500, "Misc cash", "ATM", 10, 0),  # Explicit 'Uncategorized' category
            # Inflows & transfers to exclude
            (1, "2026-03-25", 350000, "Monthly salary", "Employer B.V.", 7, 0),  # Income
            (1, "2026-03-26", -50000, "Save for future", "Degiro", 8, 0),        # Savings
            (1, "2026-03-27", -20000, "Transfer to savings", "Savings Acc", 9, 1), # Internal transfer
        ]

        self.conn.executemany(
            """
            INSERT INTO transactions (account_id, booking_date, amount_eur_minor, description_raw, merchant_normalized, category_id, is_internal_transfer)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            txs,
        )

        df = _fetch_spending_df(self.conn, filters={})

        # Ensure excluded transactions are not in df
        self.assertEqual(len(df), 6)
        self.assertTrue((df["amount_eur_minor"] < 0).all())

        # AC-2: Verify uncategorized items are never marked as discretionary
        uncat_rows = df[df["is_uncat"]]
        self.assertEqual(len(uncat_rows), 2)
        self.assertTrue((~uncat_rows["is_disc"]).all())
        self.assertTrue((~uncat_rows["is_fixed"]).all())

        # AC-1, AC-7: Monthly summary calculation with exact minor unit summation
        summary = _calculate_monthly_summary(df, salary_day=1)
        self.assertEqual(len(summary), 1)
        row = summary.iloc[0]

        # In minor units:
        # Fixed: 120050 + 15000 = 135050 cents (€1,350.50)
        # Discretionary: 8525 + 4210 = 12735 cents (€127.35)
        # Uncategorized: 5500 + 2500 = 8000 cents (€80.00)
        # Total: 135050 + 12735 + 8000 = 155785 cents (€1,557.85)
        self.assertEqual(row["fix_minor"], 135050)
        self.assertEqual(row["disc_minor"], 12735)
        self.assertEqual(row["unc_minor"], 8000)
        self.assertEqual(row["tot_minor"], 155785)

        # Presentation boundary euros
        self.assertEqual(row["fixed_spent"], 1350.50)
        self.assertEqual(row["disc_spent"], 127.35)
        self.assertEqual(row["uncat_spent"], 80.00)
        self.assertEqual(row["total_spent"], 1557.85)

        # Strict identity check
        self.assertAlmostEqual(
            row["total_spent"],
            row["fixed_spent"] + row["disc_spent"] + row["uncat_spent"],
            places=2,
        )

    @patch("ui.pages.spending.kpi_card")
    @patch("ui.pages.spending.is_hidden", return_value=True)
    def test_kpi_ribbon_privacy_mode(self, mock_is_hidden, mock_kpi_card):
        """AC-1: Verify KPI ribbon masks amounts when privacy mode is active."""
        _render_kpi_ribbon(1557.85, 1350.50, 127.35, 80.00, "March 2026")
        self.assertEqual(mock_kpi_card.call_count, 4)
        for call_args in mock_kpi_card.call_args_list:
            card_title, card_val = call_args[0][0], call_args[0][1]
            self.assertEqual(card_val, "€****", f"Card '{card_title}' should mask sensitive value")

    # -------------------------------------------------------------------------
    # AC-3, AC-7: Branch Budget Rollup & Zero Double-Counting
    # -------------------------------------------------------------------------

    def test_branch_budget_rollup_no_double_counting(self):
        """AC-3, AC-7: Parent target overrides child limits, eliminating double counting."""
        # Housing parent limit: €1,500
        # Mortgage child limit: €1,200
        # Home Insurance child limit: €200
        # Total branch budget should be €1,500 (NOT 1500 + 1200 + 200 = 2900)
        set_category_budget(self.conn, 1, 1500.0)
        set_category_budget(self.conn, 2, 1200.0)
        set_category_budget(self.conn, 3, 200.0)

        # Food parent has no explicit limit (0), but children have limits:
        # Groceries: €500, Restaurants: €250 -> Effective branch budget: €750
        set_category_budget(self.conn, 4, 0.0)
        set_category_budget(self.conn, 5, 500.0)
        set_category_budget(self.conn, 6, 250.0)

        res = calculate_budget_variance(self.conn, year_month="2026-03")

        # Total budget = Housing branch (€1,500) + Food branch (€750) = €2,250.00
        self.assertEqual(res["total_budget_eur"], 2250.0)

        # Check categories dataframe
        df = res["categories_df"]
        housing_row = df[df["category_id"] == 1].iloc[0]
        self.assertTrue(housing_row["is_parent"])
        self.assertEqual(housing_row["budget_eur"], 1500.0)

        food_row = df[df["category_id"] == 4].iloc[0]
        self.assertTrue(food_row["is_parent"])
        self.assertEqual(food_row["budget_eur"], 750.0)

    def test_branch_spend_aggregation_and_status(self):
        """AC-3: Child spending aggregates into parent categories accurately."""
        # Set budgets
        set_category_budget(self.conn, 1, 1500.0) # Housing budget €1500
        set_category_budget(self.conn, 2, 1200.0) # Mortgage child €1200

        # Insert spending:
        # Mortgage child spend: €1,300 (over budget for child)
        # Direct Housing spend: €100
        # Total Housing branch spend: €1,400 (on track for parent budget of €1500)
        self.conn.execute(
            """
            INSERT INTO transactions (account_id, booking_date, amount_eur_minor, category_id, is_internal_transfer)
            VALUES (1, '2026-03-01', -130000, 2, 0)
            """
        )
        self.conn.execute(
            """
            INSERT INTO transactions (account_id, booking_date, amount_eur_minor, category_id, is_internal_transfer)
            VALUES (1, '2026-03-02', -10000, 1, 0)
            """
        )

        res = calculate_budget_variance(self.conn, year_month="2026-03")
        self.assertEqual(res["total_spent_eur"], 1400.0)
        self.assertEqual(res["variance_eur"], 100.0) # 1500 - 1400 = 100 surplus

        df = res["categories_df"]
        housing_row = df[df["category_id"] == 1].iloc[0]
        self.assertEqual(housing_row["spent_eur"], 1400.0)
        self.assertEqual(housing_row["status"], "🟡 Near Limit") # 1400 / 1500 = 93.3% >= 85%

        mortgage_row = df[df["category_id"] == 2].iloc[0]
        self.assertEqual(mortgage_row["spent_eur"], 1300.0)
        self.assertEqual(mortgage_row["status"], "⚠️ Over Budget") # 1300 > 1200

    # -------------------------------------------------------------------------
    # AC-4, AC-5: Modal Dialog Functionality & Mortage Linking
    # -------------------------------------------------------------------------

    def test_dialog_functions_decorated(self):
        """AC-4, AC-5: Verify dialog functions are decorated as Streamlit dialogs."""
        self.assertTrue(
            hasattr(set_category_budget_dialog, "__wrapped__"),
            "set_category_budget_dialog should be wrapped by @st.dialog",
        )
        self.assertTrue(
            hasattr(assign_mortgage_dialog, "__wrapped__"),
            "assign_mortgage_dialog should be wrapped by @st.dialog",
        )

    def test_mortgage_assignment_flow(self):
        """AC-5: Assigning an uncategorized payment links to liability schedule and merchant rule."""
        # Insert liability
        self.conn.execute(
            """
            INSERT INTO liabilities (id, name, lender, loan_type, original_principal_minor)
            VALUES (1, 'Primary Home Mortgage', 'ABN AMRO', 'annuity', 40000000)
            """
        )

        # Insert uncategorized transaction
        cur = self.conn.execute(
            """
            INSERT INTO transactions (account_id, booking_date, amount_eur_minor, description_raw, merchant_normalized, category_id, is_internal_transfer)
            VALUES (1, '2026-03-01', -150000, 'ABN AMRO Hypotheek', 'ABN AMRO Bank', NULL, 0)
            """
        )
        tx_id = cur.lastrowid

        # Simulate assignment logic inside dialog
        mortgage_cat = self.conn.execute("SELECT id FROM categories WHERE name = 'Mortgage'").fetchone()
        mortgage_cat_id = mortgage_cat["id"]

        with self.conn:
            self.conn.execute(
                "UPDATE transactions SET category_id = ?, category_source = 'user' WHERE id = ?",
                (mortgage_cat_id, tx_id),
            )
            database.upsert_category_rule(self.conn, "ABN AMRO Bank", mortgage_cat_id, source="user")
            self.conn.execute(
                "UPDATE liabilities SET payment_match_pattern = COALESCE(payment_match_pattern, ?) WHERE id = ?",
                ("ABN AMRO Bank", 1),
            )
            self.conn.execute(
                """
                INSERT INTO liability_extra_payments (liability_id, paid_date, amount_minor, recalc)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(liability_id, paid_date) DO UPDATE SET amount_minor = excluded.amount_minor
                """,
                (1, "2026-03-01", 150000, "lower_payment"),
            )

        # Verify transaction updated
        updated_tx = self.conn.execute("SELECT * FROM transactions WHERE id = ?", (tx_id,)).fetchone()
        self.assertEqual(updated_tx["category_id"], mortgage_cat_id)
        self.assertEqual(updated_tx["category_source"], "user")

        # Verify rule upserted
        rule = self.conn.execute("SELECT * FROM merchant_category_rules WHERE merchant_normalized = 'ABN AMRO Bank'").fetchone()
        self.assertIsNotNone(rule)
        self.assertEqual(rule["category_id"], mortgage_cat_id)

        # Verify extra payment recorded
        extra = self.conn.execute("SELECT * FROM liability_extra_payments WHERE liability_id = 1").fetchone()
        self.assertIsNotNone(extra)
        self.assertEqual(extra["amount_minor"], 150000)
        self.assertEqual(extra["recalc"], "lower_payment")

    # -------------------------------------------------------------------------
    # AC-6: Streamlit Fragment Decorations
    # -------------------------------------------------------------------------

    def test_fragments_decorated(self):
        """AC-6: Verify spending layout sections are isolated via @st.fragment."""
        self.assertTrue(
            hasattr(_render_analytics_fragment, "__wrapped__"),
            "_render_analytics_fragment must be decorated with @st.fragment",
        )
        self.assertTrue(
            hasattr(_render_budget_tracker_fragment, "__wrapped__"),
            "_render_budget_tracker_fragment must be decorated with @st.fragment",
        )


if __name__ == "__main__":
    unittest.main()
