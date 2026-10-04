import unittest

from services.analytics import calculate_burn_and_runway, calculate_savings_rate, detect_recurring_charges


class TestAnalytics(unittest.TestCase):
    def test_savings_rate(self):
        # 5000 income, 3000 expenses -> 40%
        rate = calculate_savings_rate(5000.0, 3000.0)
        self.assertAlmostEqual(rate, 40.0, places=2)

        # 0 income -> 0%
        self.assertEqual(calculate_savings_rate(0.0, 1000.0), 0.0)

    def test_burn_and_runway(self):
        expenses = [2500.0, 2600.0, 2400.0]  # mean = 2500
        cash = 15000.0
        burn, runway_months, runway_days = calculate_burn_and_runway(expenses, cash)
        self.assertAlmostEqual(burn, 2500.0, places=2)
        self.assertAlmostEqual(runway_months, 6.0, places=2)
        self.assertAlmostEqual(runway_days, 6.0 * 30.44, places=1)

    def test_detect_recurring_charges(self):
        # Synthetic Netflix subscription (3 monthly charges at €15.99)
        synthetic_txs = [
            {"booking_date": "2026-01-10", "merchant": "Netflix", "amount_eur": -15.99, "is_internal_transfer": 0},
            {"booking_date": "2026-02-10", "merchant": "Netflix", "amount_eur": -15.99, "is_internal_transfer": 0},
            {"booking_date": "2026-03-10", "merchant": "Netflix", "amount_eur": -15.99, "is_internal_transfer": 0},
            {"booking_date": "2026-03-05", "merchant": "One-off Store", "amount_eur": -45.00, "is_internal_transfer": 0},
            # Monthly salary (inflow: positive amount) must NOT be detected as a recurring bill
            {"booking_date": "2026-01-25", "merchant": "Employer Salary", "amount_eur": 4500.00, "is_internal_transfer": 0},
            {"booking_date": "2026-02-25", "merchant": "Employer Salary", "amount_eur": 4500.00, "is_internal_transfer": 0},
            {"booking_date": "2026-03-25", "merchant": "Employer Salary", "amount_eur": 4500.00, "is_internal_transfer": 0},
        ]
        recurring = detect_recurring_charges(synthetic_txs)
        self.assertEqual(len(recurring), 1)
        self.assertEqual(recurring[0]["merchant"], "Netflix")
        self.assertEqual(recurring[0]["cadence"], "Monthly")
        self.assertAlmostEqual(recurring[0]["amount_eur"], 15.99, places=2)


if __name__ == "__main__":
    unittest.main()
