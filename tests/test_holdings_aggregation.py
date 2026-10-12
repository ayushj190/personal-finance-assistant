import unittest

import pandas as pd

from services.portfolio import aggregate_distinct_holdings


def _h(ticker, qty, cost_eur, native, ccy, close=0.0, value=0.0, pnl=0.0, name="N", atype="etf"):
    return {
        "ticker": ticker,
        "name": name,
        "asset_type": atype,
        "quantity": qty,
        "cost_basis": cost_eur,
        "cost_basis_native": native,
        "currency": ccy,
        "latest_close": close,
        "value_eur": value,
        "unrealized_pnl_eur": pnl,
    }


class TestHoldingsAggregation(unittest.TestCase):
    def test_sums_lots_and_uses_native_average(self):
        df = pd.DataFrame([
            _h("VWCE.DE", 10, 1000, 1000, "EUR", 110, 1100, 100),
            _h("VWCE.DE", 5, 500, 500, "EUR", 110, 550, 50),
        ])
        agg, label = aggregate_distinct_holdings(df)
        self.assertEqual(len(agg), 1)
        row = agg.iloc[0]
        self.assertAlmostEqual(row["quantity"], 15)
        self.assertAlmostEqual(row["cost_basis"], 1500)
        self.assertAlmostEqual(row["value_eur"], 1650)
        self.assertAlmostEqual(row["unrealized_pnl_eur"], 150)
        self.assertAlmostEqual(row["avg_open_price"], 1500 / 15)
        self.assertEqual(label, "Avg Open")

    def test_copy_row_keeps_key_and_falls_back_to_eur(self):
        df = pd.DataFrame([_h("COPY:alice", 0, 2000, 0, "USD", name="Copy: alice")])
        agg, label = aggregate_distinct_holdings(df)
        self.assertEqual(agg.iloc[0]["ticker"], "COPY:alice")
        self.assertEqual(label, "Avg Open (EUR)")
        self.assertAlmostEqual(agg.iloc[0]["avg_open_price"], 0.0)

    def test_mixed_currency_marks_column_eur(self):
        df = pd.DataFrame([
            _h("XYZ", 10, 1000, 900, "USD"),
            _h("XYZ", 10, 1000, 1000, "EUR"),
        ])
        agg, label = aggregate_distinct_holdings(df)
        self.assertEqual(agg.iloc[0]["currency"], "MIXED")
        self.assertEqual(label, "Avg Open (EUR)")

    def test_empty_frame(self):
        agg, label = aggregate_distinct_holdings(pd.DataFrame())
        self.assertTrue(agg.empty)
        self.assertEqual(label, "Avg Open")


if __name__ == "__main__":
    unittest.main()
