import unittest

from services.portfolio import allocate_contribution, calculate_drift, full_rebalance, rebalance_without_selling


class TestPortfolio(unittest.TestCase):
    def test_drift_and_5_25_rule(self):
        # 80/20 target. Current: 90/10 with total 100k
        values = {"equity": 90000.0, "bond": 10000.0}
        targets = {"equity": 80.0, "bond": 20.0}

        drift = calculate_drift(values, targets, drift_band_pct=5.0)
        # Bond: actual 10%, target 20% -> diff -10 pp -> exceeds 5pp band and 25% of target
        bond_drift = next(d for d in drift if d["bucket"] == "bond")
        self.assertEqual(bond_drift["actual_pct"], 10.0)
        self.assertEqual(bond_drift["target_pct"], 20.0)
        self.assertEqual(bond_drift["drift_pp"], -10.0)
        self.assertTrue(bond_drift["alert"])

    def test_rebalance_without_selling(self):
        # Current: 900 equity, 100 bond. Target: 50% equity, 50% bond.
        # To hit 50/50 without selling equity (which is 900), total portfolio must become 1800 -> need 800 more bond
        values = {"equity": 900.0, "bond": 100.0}
        targets = {"equity": 50.0, "bond": 50.0}

        needed_cash, buys = rebalance_without_selling(values, targets)
        self.assertAlmostEqual(needed_cash, 800.0, places=1)
        self.assertAlmostEqual(buys["bond"], 800.0, places=1)
        self.assertAlmostEqual(buys.get("equity", 0.0), 0.0, places=1)

    def test_allocate_contribution(self):
        # Current: 800 ETF, 100 stock. Target: 80% ETF, 20% stock (stock is underweight).
        # Contribution 100 should mostly go to stock
        values = {"etf": 800.0, "stock": 100.0}
        targets = {"etf": 80.0, "stock": 20.0}

        alloc = allocate_contribution(values, targets, contribution=100.0)
        self.assertGreater(alloc["stock"], alloc["etf"])

    def test_full_rebalance(self):
        # Current: 600 equity, 400 bond. Target: 50/50 on total 1000 -> target 500 each.
        values = {"equity": 600.0, "bond": 400.0}
        targets = {"equity": 50.0, "bond": 50.0}

        deltas = full_rebalance(values, targets)
        self.assertAlmostEqual(deltas["equity"], -100.0, places=1)
        self.assertAlmostEqual(deltas["bond"], 100.0, places=1)


if __name__ == "__main__":
    unittest.main()
