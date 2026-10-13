import sqlite3
import unittest
from unittest.mock import MagicMock, patch
from streamlit.testing.v1 import AppTest

from agent import copilot, tools
from db import database
from services.llm_client import check_ollama_status


def _render_sidebar_app():
    from ui.copilot_sidebar import render_copilot_sidebar
    render_copilot_sidebar()


class TestCopilotCalmingAndToolHardening(unittest.TestCase):
    """Automated test suite validating copilot calming, read only authorizer, and tool hardening."""

    # -------------------------------------------------------------------------
    # AC-3: Dedicated read only SQLite authorizer
    # -------------------------------------------------------------------------
    def test_connect_readonly_allows_reads(self):
        """Verify that connect_readonly allows SELECT queries and read only PRAGMAs."""
        conn = database.connect_readonly()
        try:
            row = conn.execute("SELECT COUNT(*) as count FROM accounts").fetchone()
            self.assertIsNotNone(row)
            self.assertGreaterEqual(row["count"], 0)

            # Read only PRAGMA inspection must succeed
            pragma_row = conn.execute("PRAGMA table_info(accounts)").fetchall()
            self.assertTrue(len(pragma_row) > 0)
        finally:
            conn.close()

    def test_connect_readonly_denies_writes_and_schema_mutation(self):
        """Verify that connect_readonly strictly blocks INSERT, UPDATE, DELETE, and DDL."""
        conn = database.connect_readonly()
        try:
            # 1. Deny INSERT
            with self.assertRaises(sqlite3.DatabaseError) as ctx_ins:
                conn.execute(
                    "INSERT INTO accounts (institution, name, currency, asset_class) VALUES ('Test', 'Test', 'EUR', 'cash')"
                )
            self.assertIn("not authorized", str(ctx_ins.exception).lower())

            # 2. Deny UPDATE
            with self.assertRaises(sqlite3.DatabaseError) as ctx_upd:
                conn.execute("UPDATE accounts SET name = 'Hacked' WHERE id = 1")
            self.assertIn("not authorized", str(ctx_upd.exception).lower())

            # 3. Deny DELETE
            with self.assertRaises(sqlite3.DatabaseError) as ctx_del:
                conn.execute("DELETE FROM accounts WHERE id = 1")
            self.assertIn("not authorized", str(ctx_del.exception).lower())

            # 4. Deny DROP TABLE
            with self.assertRaises(sqlite3.DatabaseError) as ctx_drop:
                conn.execute("DROP TABLE accounts")
            self.assertIn("not authorized", str(ctx_drop.exception).lower())

            # 5. Deny CREATE TABLE
            with self.assertRaises(sqlite3.DatabaseError) as ctx_create:
                conn.execute("CREATE TABLE malicious (id INT)")
            self.assertIn("not authorized", str(ctx_create.exception).lower())
        finally:
            conn.close()

    # -------------------------------------------------------------------------
    # AC-2: Upfront Ollama connectivity verification
    # -------------------------------------------------------------------------
    @patch("services.llm_client.httpx.get")
    def test_check_ollama_status_online(self, mock_get):
        """Verify check_ollama_status returns online True when HTTP heartbeat succeeds."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_get.return_value = mock_resp

        status = check_ollama_status()
        self.assertTrue(status["online"])
        self.assertIsNone(status["error"])

    @patch("services.llm_client.httpx.get")
    def test_check_ollama_status_offline(self, mock_get):
        """Verify check_ollama_status returns online False and captures error when unreachable."""
        import httpx
        mock_get.side_effect = httpx.ConnectError("Connection refused")

        status = check_ollama_status()
        self.assertFalse(status["online"])
        self.assertIn("Connection refused", status["error"])

    @patch("ui.copilot_sidebar.check_ollama_status")
    def test_sidebar_offline_ollama_renders_guidance_without_task(self, mock_status):
        """Verify sidebar renders friendly 'ollama serve' notice and avoids task launch when offline."""
        mock_status.return_value = {"online": False, "model": "qwen2.5:7b-instruct", "error": "Connection refused"}

        at = AppTest.from_function(_render_sidebar_app)
        at.session_state["pending_copilot_prompt"] = "What is my net worth?"
        at.run()

        # No background thread task should be active
        self.assertNotIn("copilot_active_task", at.session_state)
        # Chat history should record user prompt and assistant troubleshooting advice
        history = at.session_state.get("copilot_history", [])
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0]["role"], "user")
        self.assertEqual(history[1]["role"], "assistant")
        self.assertIn("ollama serve", history[1]["content"])
        self.assertTrue(history[1].get("diagnostics"))

    # -------------------------------------------------------------------------
    # AC-4: Structured query tool error recovery & diagnostics
    # -------------------------------------------------------------------------
    def test_execute_tool_unknown_tool(self):
        """Verify execute_tool handles unknown tools gracefully with diagnostic details."""
        res = copilot.execute_tool("nonexistent_financial_tool", {})
        self.assertFalse(res["success"])
        self.assertIn("Unknown tool", res["message"])
        self.assertIn("diagnostics", res)
        self.assertEqual(res["diagnostics"]["error_type"], "UnknownToolError")

    def test_execute_tool_authorizer_violation_structured_recovery(self):
        """Verify authorizer denial in tool returns friendly security explanation and diagnostics."""
        def bad_tool():
            conn = database.connect_readonly()
            try:
                conn.execute("DELETE FROM accounts")
            finally:
                conn.close()

        with patch.dict(copilot.TOOL_MAP, {"bad_write_tool": bad_tool}):
            res = copilot.execute_tool("bad_write_tool", {})
            self.assertFalse(res["success"])
            self.assertIn("read only database authorizer", res["message"])
            self.assertIn("diagnostics", res)
            self.assertEqual(res["diagnostics"]["tool"], "bad_write_tool")
            self.assertEqual(res["diagnostics"]["error_type"], "DatabaseError")

    def test_execute_tool_generic_exception_structured_recovery(self):
        """Verify generic exception produces structured diagnostics and traceback."""
        def crashing_tool():
            raise ZeroDivisionError("division by zero test")

        with patch.dict(copilot.TOOL_MAP, {"crashing_tool": crashing_tool}):
            res = copilot.execute_tool("crashing_tool", {})
            self.assertFalse(res["success"])
            self.assertIn("division by zero test", res["message"])
            self.assertIn("diagnostics", res)
            self.assertEqual(res["diagnostics"]["error_type"], "ZeroDivisionError")
            self.assertIn("ZeroDivisionError", res["diagnostics"]["traceback"])

    # -------------------------------------------------------------------------
    # AC-5: Informative empty dataset handling
    # -------------------------------------------------------------------------
    def test_empty_dataset_guidance_for_spending(self):
        """Verify empty spending breakdown returns structured guidance instead of blank answers."""
        # Query for a future year with no data
        res = tools.tool_get_spending_by_category(year=2099, month=1)
        self.assertTrue(res["success"])
        self.assertTrue(res.get("empty_dataset"))
        self.assertIn("guidance", res)
        self.assertEqual(res["categories"], [])

    def test_empty_dataset_guidance_for_recent_transactions(self):
        """Verify querying non-existent category returns structured empty guidance."""
        res = tools.tool_get_recent_transactions(category="NonExistentCategoryXYZ")
        self.assertTrue(res["success"])
        self.assertTrue(res.get("empty_dataset"))
        self.assertEqual(res["count"], 0)
        self.assertIn("guidance", res)

    def test_empty_dataset_guidance_for_cashflow(self):
        """Verify empty monthly cashflow returns structured guidance."""
        res = tools.tool_get_monthly_cashflow(year=2099)
        self.assertTrue(res["success"])
        self.assertTrue(res.get("empty_dataset"))
        self.assertEqual(res["cashflow"], [])
        self.assertIn("guidance", res)

    def test_empty_dataset_guidance_for_tax_situation(self):
        """Verify unconfigured tax profile returns structured guidance pointing to Tax Analysis tab."""
        # When tax profile gross income is 0 or unconfigured
        fake_conn = sqlite3.connect(":memory:")
        fake_conn.row_factory = sqlite3.Row
        fake_conn.execute("CREATE TABLE tax_profile (id INT PRIMARY KEY, gross_annual_income REAL)")
        fake_conn.execute("INSERT INTO tax_profile (id, gross_annual_income) VALUES (1, 0)")

        with patch("db.database.connect_readonly", return_value=fake_conn):
            res = tools.tool_analyze_tax_situation()
            self.assertFalse(res["success"])
            self.assertTrue(res.get("empty_dataset"))
            self.assertIn("guidance", res)
            self.assertIn("Tax Analysis", res["guidance"])

    def test_empty_dataset_guidance_for_mortgage(self):
        """Verify empty liabilities table returns structured guidance pointing to Mortgage page."""
        fake_conn = sqlite3.connect(":memory:")
        fake_conn.row_factory = sqlite3.Row
        fake_conn.execute("CREATE TABLE liabilities (id INT PRIMARY KEY)")

        with patch("db.database.connect_readonly", return_value=fake_conn):
            res = tools.tool_analyze_mortgage()
            self.assertFalse(res["success"])
            self.assertTrue(res.get("empty_dataset"))
            self.assertIn("Mortgage", res["guidance"])

    def test_empty_dataset_guidance_for_risk_profile(self):
        """Verify missing risk profile returns structured guidance pointing to Assess Risk."""
        with patch("db.database.get_latest_risk_profile", return_value=None):
            res = tools.tool_get_risk_profile()
            self.assertFalse(res["success"])
            self.assertTrue(res.get("empty_dataset"))
            self.assertIn("Assess Risk", res["guidance"])

    # -------------------------------------------------------------------------
    # AC-6: Transparent quick actions chat logging
    # -------------------------------------------------------------------------
    @patch("services.llm_client.check_ollama_status")
    def test_quick_actions_log_explicit_user_bubble(self, mock_status):
        """Verify clicking quick action button immediately logs user message bubble in chat history."""
        mock_status.return_value = {"online": True, "model": "qwen2.5:7b-instruct", "error": None}
        at = AppTest.from_function(_render_sidebar_app)
        at.run()

        # Locate and click Assess Risk button
        assess_button = next(b for b in at.button if "Assess Risk" in b.label)
        self.assertIn("Assess Risk", assess_button.label)
        assess_button.click().run()

        history = at.session_state.get("copilot_history", [])
        self.assertTrue(len(history) >= 1)
        self.assertEqual(history[0]["role"], "user")
        self.assertIn("investment risk tolerance", history[0]["content"])

    # -------------------------------------------------------------------------
    # AC-7: Parameter sanitization and bounds checking
    # -------------------------------------------------------------------------
    def test_spending_by_category_parameter_sanitization(self):
        """Verify spending tool rejects invalid years and months gracefully."""
        # Year out of bounds
        res_low_yr = tools.tool_get_spending_by_category(year=1850)
        self.assertFalse(res_low_yr["success"])
        self.assertIn("Invalid year", res_low_yr["message"])

        res_high_yr = tools.tool_get_spending_by_category(year=2250)
        self.assertFalse(res_high_yr["success"])
        self.assertIn("Invalid year", res_high_yr["message"])

        # Month out of bounds
        res_bad_mo = tools.tool_get_spending_by_category(year=2026, month=15)
        self.assertFalse(res_bad_mo["success"])
        self.assertIn("Invalid month", res_bad_mo["message"])

        res_zero_mo = tools.tool_get_spending_by_category(year=2026, month=0)
        self.assertFalse(res_zero_mo["success"])
        self.assertIn("Invalid month", res_zero_mo["message"])

    def test_recent_transactions_parameter_sanitization(self):
        """Verify transactions tool handles invalid limits cleanly."""
        res_neg = tools.tool_get_recent_transactions(limit=-5)
        self.assertFalse(res_neg["success"])
        self.assertIn("positive integer", res_neg["message"])

        res_str = tools.tool_get_recent_transactions(limit="invalid_number")
        self.assertFalse(res_str["success"])
        self.assertIn("numeric limit", res_str["message"])

        # Clamps to 100 max
        res_large = tools.tool_get_recent_transactions(limit=500)
        self.assertTrue(res_large["success"])
        self.assertLessEqual(res_large["count"], 100)

    def test_monthly_cashflow_parameter_sanitization(self):
        """Verify cashflow tool validates year correctly."""
        res_bad = tools.tool_get_monthly_cashflow(year=3000)
        self.assertFalse(res_bad["success"])
        self.assertIn("Invalid year", res_bad["message"])

    def test_tax_simulation_parameter_sanitization(self):
        """Verify simulate_tax_optimization validates capital and horizon."""
        res_zero_cap = tools.tool_simulate_tax_optimization(capital_eur=0)
        self.assertFalse(res_zero_cap["success"])
        self.assertIn("greater than 0", res_zero_cap["message"])

        res_bad_horizon = tools.tool_simulate_tax_optimization(capital_eur=5000, horizon_years=99)
        self.assertFalse(res_bad_horizon["success"])
        self.assertIn("between 1 and 50", res_bad_horizon["message"])

    def test_pension_room_parameter_sanitization(self):
        """Verify calculate_pension_room rejects negative inputs."""
        res_neg_inc = tools.tool_calculate_pension_room(gross_income=-1000)
        self.assertFalse(res_neg_inc["success"])
        self.assertIn("cannot be negative", res_neg_inc["message"])

        res_neg_fa = tools.tool_calculate_pension_room(gross_income=50000, factor_a=-500)
        self.assertFalse(res_neg_fa["success"])
        self.assertIn("cannot be negative", res_neg_fa["message"])

    def test_green_fund_parameter_sanitization(self):
        """Verify analyze_green_fund_strategy rejects negative allocations."""
        res_neg = tools.tool_analyze_green_fund_strategy(target_allocation=-2000)
        self.assertFalse(res_neg["success"])
        self.assertIn("cannot be negative", res_neg["message"])

    def test_law_vault_query_sanitization(self):
        """Verify law vault search and article lookup reject empty strings."""
        res_empty_q = tools.tool_search_dutch_law_vault(query="   ")
        self.assertFalse(res_empty_q["success"])
        self.assertIn("cannot be empty", res_empty_q["message"])

        res_bad_yr = tools.tool_search_dutch_law_vault(query="Box 3", effective_year=1800)
        self.assertFalse(res_bad_yr["success"])
        self.assertIn("Invalid effective year", res_bad_yr["message"])

        res_empty_ref = tools.tool_lookup_tax_law_article(article_ref="")
        self.assertFalse(res_empty_ref["success"])
        self.assertIn("cannot be empty", res_empty_ref["message"])


if __name__ == "__main__":
    unittest.main()
