import unittest
from services.tax_optimizer import (
    calculate_jaarruimte,
    calculate_groenfondsen_arbitrage,
    simulate_capital_allocation_tradeoff,
    diagnose_tax_leakage,
    CERTIFIED_DUTCH_GREEN_FUNDS,
)


class TestTaxOptimizer(unittest.TestCase):
    def test_calculate_jaarruimte(self):
        # Case 1: Gross 60,000, Factor A 0
        res = calculate_jaarruimte(gross_income=60000.0, factor_a=0.0)
        self.assertAlmostEqual(res["premiegrondslag"], 60000.0 - 17545.0, places=1)
        expected_room = 0.30 * (60000.0 - 17545.0)
        self.assertAlmostEqual(res["annual_jaarruimte"], expected_room, places=1)
        self.assertEqual(res["marginal_tax_rate"], 0.3697)
        self.assertGreater(res["immediate_tax_rebate"], 0.0)

        # Case 2: Top bracket gross 90,000, Factor A 800
        res_top = calculate_jaarruimte(gross_income=90000.0, factor_a=800.0)
        self.assertEqual(res_top["marginal_tax_rate"], 0.4950)
        expected_top = (0.30 * (90000.0 - 17545.0)) - (3.0 * 800.0)
        self.assertAlmostEqual(res_top["annual_jaarruimte"], expected_top, places=1)
        self.assertAlmostEqual(res_top["immediate_tax_rebate"], expected_top * 0.4950, places=1)

    def test_calculate_groenfondsen_arbitrage(self):
        # Case: Wealth 120,000, Single (€57,000 allowance), Green investment 30,000
        res = calculate_groenfondsen_arbitrage(
            total_wealth=120000.0,
            current_green=0.0,
            prospective_green=30000.0,
            has_fiscal_partner=False,
        )
        self.assertEqual(res["exemption_cap"], 71251.0)
        self.assertEqual(res["effective_exempt_green"], 30000.0)
        expected_box3_saving = 30000.0 * 0.0604 * 0.36
        expected_box1_credit = 30000.0 * 0.001
        self.assertAlmostEqual(res["box3_annual_savings"], expected_box3_saving, places=2)
        self.assertAlmostEqual(res["box1_annual_credit"], expected_box1_credit, places=2)
        self.assertAlmostEqual(res["total_annual_tax_benefit"], expected_box3_saving + expected_box1_credit, places=2)
        self.assertGreaterEqual(len(res["certified_funds"]), 3)

    def test_simulate_capital_allocation_tradeoff(self):
        sim = simulate_capital_allocation_tradeoff(capital_eur=10000.0, horizon_years=10)
        self.assertIn("final_values", sim)
        self.assertIn("winner_strategy", sim)
        self.assertIn("trajectory_df", sim)

        final_vals = sim["final_values"]
        self.assertIn("mortgage", final_vals)
        self.assertIn("pension", final_vals)
        self.assertIn("green", final_vals)
        self.assertIn("taxable_etf", final_vals)

        # All strategies must beat the initial €10,000 principal
        for k, v in final_vals.items():
            self.assertGreater(v, 10000.0)

    def test_diagnose_tax_leakage(self):
        leaks = diagnose_tax_leakage()
        self.assertIsInstance(leaks, list)
        for leak in leaks:
            self.assertIn("severity", leak)
            self.assertIn("title", leak)
            self.assertIn("potential_annual_saving_eur", leak)


if __name__ == "__main__":
    unittest.main()
