from datetime import date
import unittest

from services.mortgage import calculate_mortgage_schedule


class TestMortgage(unittest.TestCase):
    def test_annuity_schedule_amortization(self):
        # €300,000 annuity loan at 3.6% annual rate for 360 months
        schedule = calculate_mortgage_schedule(
            loan_type="annuity",
            principal_cents=30000000,
            start_date=date(2024, 1, 1),
            term_months=360,
            rate_periods=[{"from_date": "2024-01-01", "annual_rate": 0.036, "fixed_until": None}],
            extra_payments=[],
        )
        self.assertEqual(len(schedule), 360)

        # Standard annuity monthly payment for 300k, 3.6%, 360 mo ≈ €1,363.94
        first_month = schedule[0]
        payment_eur = first_month["payment_minor"] / 100.0
        self.assertAlmostEqual(payment_eur, 1363.94, delta=2.0)

        # Final month balance should reach 0
        final_month = schedule[-1]
        self.assertEqual(final_month["balance_minor"], 0)

    def test_linear_schedule(self):
        # €120,000 linear loan for 120 months (fixed principal = €1,000 / month)
        schedule = calculate_mortgage_schedule(
            loan_type="linear",
            principal_cents=12000000,
            start_date=date(2024, 1, 1),
            term_months=120,
            rate_periods=[{"from_date": "2024-01-01", "annual_rate": 0.04, "fixed_until": None}],
            extra_payments=[],
        )
        self.assertEqual(len(schedule), 120)
        # Principal in each month should be 1000.00
        for m in schedule[:-1]:
            self.assertEqual(m["principal_minor"], 100000)
        self.assertEqual(schedule[-1]["balance_minor"], 0)

    def test_extra_payment_lowers_balance(self):
        # Annuity with lump-sum extra payment of €10,000 at month 12
        extra = [{"paid_date": date(2025, 1, 1), "amount_minor": 1000000, "recalc": "lower_payment"}]
        schedule = calculate_mortgage_schedule(
            loan_type="annuity",
            principal_cents=30000000,
            start_date=date(2024, 1, 1),
            term_months=360,
            rate_periods=[{"from_date": "2024-01-01", "annual_rate": 0.036, "fixed_until": None}],
            extra_payments=extra,
        )
        # Payment after month 12 should be lower than initial payment
        initial_p = schedule[0]["payment_minor"]
        post_extra_p = schedule[15]["payment_minor"]
        self.assertLess(post_extra_p, initial_p)

    def test_sync_liability_schedule_and_db_flow(self):
        import sqlite3
        from db import database
        from services.mortgage import sync_liability_schedule

        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        with conn:
            with open(database.SCHEMA_FILE, "r", encoding="utf-8") as f:
                conn.executescript(f.read())
            with open(database.SEED_FILE, "r", encoding="utf-8") as f:
                conn.executescript(f.read())

            cur = conn.execute(
                """
                INSERT INTO liabilities (name, lender, loan_type, original_principal_minor, start_date, term_months)
                VALUES ('Test Loan', 'ABN AMRO', 'annuity', 30000000, '2024-01-01', 360)
                """
            )
            lib_id = cur.lastrowid
            conn.execute(
                "INSERT INTO liability_rate_periods (liability_id, from_date, annual_rate, fixed_until) VALUES (?, '2024-01-01', 0.036, '2034-01-01')",
                (lib_id,),
            )

        sync_liability_schedule(conn, lib_id)
        sched_rows = conn.execute("SELECT * FROM liability_schedule WHERE liability_id = ? ORDER BY month_idx ASC", (lib_id,)).fetchall()
        self.assertEqual(len(sched_rows), 360)
        self.assertGreater(sched_rows[0]["payment_minor"], 0)
        self.assertEqual(sched_rows[-1]["balance_minor"], 0)
        conn.close()


if __name__ == "__main__":
    unittest.main()
