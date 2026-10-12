import unittest

import pandas as pd

from services.analytics import aggregate_top_merchants, resolve_iban_country


def _row(merchant, category, parent, minor, date):
    return {
        "merchant": merchant,
        "category": category,
        "parent_category": parent,
        "amount_eur_minor": minor,
        "booking_date": date,
    }


class TestTopMerchants(unittest.TestCase):
    def test_aggregation_location_and_mixed_category(self):
        df = pd.DataFrame([
            _row("Albert Heijn", "Groceries", "Groceries", -5000, "2026-09-01"),
            _row("Albert Heijn", "Groceries", "Groceries", -3000, "2026-09-10"),
            _row("Uber", "Transport", "Transport", -2000, "2026-09-05"),
            _row("Uber", "Dining", "Food & Restaurants", -2000, "2026-09-06"),
        ])
        context = {
            "Albert Heijn": {"location": "Netherlands", "accounts": ["ABN AMRO"]},
            "Uber": {"location": None, "accounts": ["Revolut"]},
        }
        res = aggregate_top_merchants(df, context, scope_total_eur=120.0)

        self.assertTrue(res["has_location"])
        rows = {r["merchant"]: r for r in res["rows"]}

        ah = rows["Albert Heijn"]
        self.assertEqual(ah["transactions"], 2)
        self.assertAlmostEqual(ah["total_eur"], 80.0)
        self.assertAlmostEqual(ah["avg_eur"], 40.0)
        self.assertEqual(ah["last_date"], "2026-09-10")
        self.assertEqual(ah["accounts"], "ABN AMRO")
        self.assertEqual(ah["category"], "Groceries")
        self.assertAlmostEqual(ah["share_pct"], 80.0 / 120.0 * 100.0, places=3)

        uber = rows["Uber"]
        self.assertEqual(uber["category"], "Mixed")
        self.assertAlmostEqual(uber["total_eur"], 40.0)

        self.assertEqual(res["location_totals"][0]["location"], "Netherlands")

    def test_no_location_without_ibans(self):
        df = pd.DataFrame([_row("Shop", "Groceries", "Groceries", -1000, "2026-09-01")])
        res = aggregate_top_merchants(
            df, {"Shop": {"location": None, "accounts": ["Cash"]}}, scope_total_eur=10.0
        )
        self.assertFalse(res["has_location"])
        self.assertEqual(res["location_totals"], [])
        self.assertIsNone(res["rows"][0]["location"])

    def test_month_divisor_averages_totals(self):
        df = pd.DataFrame([_row("Shop", "Groceries", "Groceries", -2000, "2026-08-01"),
                           _row("Shop", "Groceries", "Groceries", -4000, "2026-09-01")])
        res = aggregate_top_merchants(df, {}, scope_total_eur=30.0, month_divisor=2)
        self.assertAlmostEqual(res["rows"][0]["total_eur"], 30.0)

    def test_resolve_iban_country(self):
        self.assertEqual(resolve_iban_country("NL91ABNA0417164300"), "Netherlands")
        self.assertEqual(resolve_iban_country("DE89 3704 0044 0532 0130 00"), "Germany")
        self.assertIsNone(resolve_iban_country(None))
        self.assertIsNone(resolve_iban_country("ZZ00"))


if __name__ == "__main__":
    unittest.main()
