import unittest
from agent import tools


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

    def test_portfolio_summary_and_sql(self):
        summary = tools.tool_get_portfolio_and_risk_summary()
        self.assertTrue(summary["success"])
        self.assertIn("asset_classes_eur", summary)

        sql_res = tools.tool_query_financial_data(
            "SELECT count(*) as total_accounts FROM accounts")
        self.assertTrue(sql_res["success"])
        self.assertIsNotNone(sql_res["df"])


if __name__ == "__main__":
    unittest.main()
