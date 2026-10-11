import unittest
from agent import tools
from services.rag_service import search_knowledge_base


class TestCopilotTools(unittest.TestCase):
    def test_privacy_and_theme_tools(self):
        res_priv = tools.tool_toggle_privacy_mode(enable=True)
        self.assertTrue(res_priv["success"])

        res_theme = tools.tool_set_theme("light")
        self.assertTrue(res_theme["success"])

        res_theme_dark = tools.tool_set_theme("dark")
        self.assertTrue(res_theme_dark["success"])

        res_theme_inv = tools.tool_set_theme("neon")
        self.assertFalse(res_theme_inv["success"])

    def test_risk_profile_tools(self):
        res_save = tools.tool_save_risk_profile(
            risk_score=8,
            risk_tolerance="Growth",
            notes="Comfortable with market volatility for 10-year goal",
            answers={"horizon": "10+ years", "reaction": "buy more"},
        )
        self.assertTrue(res_save["success"])
        self.assertEqual(res_save["risk_score"], 8)
        self.assertEqual(res_save["risk_tolerance"], "Growth")

        res_get = tools.tool_get_risk_profile()
        self.assertTrue(res_get["success"])
        self.assertEqual(res_get["profile"]["risk_score"], 8)
        self.assertEqual(res_get["profile"]["risk_tolerance"], "Growth")

    def test_allocation_and_savings_tools(self):
        res_alloc = tools.tool_set_active_allocation_profile(
            "80/20 Core-Satellite")
        self.assertTrue(res_alloc["success"])

        res_savings = tools.tool_update_savings_rate("Trade Republic", 3.25)
        self.assertTrue(res_savings["success"])

    def test_portfolio_summary(self):
        summary = tools.tool_get_portfolio_and_risk_summary()
        self.assertTrue(summary["success"])
        self.assertIn("asset_classes_eur", summary)

    def test_deterministic_financial_tools(self):
        # 1. Spending by category
        res_spending = tools.tool_get_spending_by_category()
        self.assertTrue(res_spending["success"])
        self.assertIn("total_spent_eur", res_spending)
        self.assertIn("categories", res_spending)

        # 2. Recent transactions
        res_txs = tools.tool_get_recent_transactions(limit=10)
        self.assertTrue(res_txs["success"])
        self.assertIn("transactions", res_txs)

        # 3. Monthly cashflow
        res_cashflow = tools.tool_get_monthly_cashflow()
        self.assertTrue(res_cashflow["success"])
        self.assertIn("cashflow", res_cashflow)

    def test_knowledge_base_search(self):
        # Test Dutch tax search
        tax_res = tools.tool_search_financial_knowledge_base("Box 3 wealth tax deemed return")
        self.assertTrue(tax_res["success"])
        self.assertGreater(len(tax_res["results"]), 0)

        # Test mortgage guidance search
        mortgage_res = tools.tool_search_financial_knowledge_base("hypotheekrenteaftrek mortgage deduction")
        self.assertTrue(mortgage_res["success"])
        self.assertGreater(len(mortgage_res["results"]), 0)

    def test_tax_optimization_copilot_tools(self):
        # 1. Simulate tax optimization
        sim_res = tools.tool_simulate_tax_optimization(capital_eur=8000.0, horizon_years=5)
        self.assertTrue(sim_res["success"])
        self.assertIn("simulation", sim_res)
        self.assertIsNotNone(sim_res.get("figure"))

        # 2. Calculate pension room
        pension_res = tools.tool_calculate_pension_room(gross_income=70000.0, factor_a=500.0)
        self.assertTrue(pension_res["success"])
        self.assertIn("pension_data", pension_res)

        # 3. Analyze green fund strategy
        green_res = tools.tool_analyze_green_fund_strategy(target_allocation=20000.0)
        self.assertTrue(green_res["success"])
        self.assertIn("arbitrage", green_res)

        # 4. Diagnose tax leaks
        leak_res = tools.tool_diagnose_tax_leaks()
        self.assertTrue(leak_res["success"])
        self.assertIn("recommendations", leak_res)

        # 5. Ingest document
        ingest_res = tools.tool_ingest_financial_document(
            doc_title="Tax Treaty Exemption Note",
            content="Specific note regarding 30% ruling phasing and extraterritorial cost reimbursements.",
            category="tax_strategy",
        )
        self.assertTrue(ingest_res["success"])

        # Cleanup test file
        from services.rag_service import KNOWLEDGE_DIR
        test_file = KNOWLEDGE_DIR / "user_tax_treaty_exemption_note.md"
        if test_file.exists():
            test_file.unlink()


if __name__ == "__main__":
    unittest.main()
