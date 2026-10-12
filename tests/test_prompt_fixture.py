import json
import unittest
from unittest.mock import MagicMock, patch

from agent import copilot, tools
from agent.tool_schemas import COPILOT_TOOLS_SCHEMA


# AC-14: the eight prompt evaluation set, asserted with the model mocked.
PROMPT_TOOL_FIXTURE: list[tuple[str, str, dict]] = [
    ("What is my net worth right now?", "get_current_net_worth", {}),
    ("How much did I spend on groceries last month?", "get_spending_by_category", {"year": 2026, "month": 9}),
    ("Show me my most recent transactions.", "get_recent_transactions", {"limit": 10}),
    ("What is my monthly cashflow?", "get_monthly_cashflow", {}),
    ("How is my portfolio allocated against my target?", "analyze_investments", {}),
    ("List my allocation strategies.", "get_allocation_profiles", {}),
    (
        "Create a strategy that is 70 percent ETFs and 30 percent crypto.",
        "create_allocation_profile",
        {"name": "Fixture 70/30", "dimension": "asset_type", "targets": {"etf": 70.0, "crypto": 30.0}},
    ),
    ("Analyze my mortgage schedule.", "analyze_mortgage", {}),
]


class TestPromptFixture(unittest.TestCase):
    def test_every_prompt_maps_to_its_expected_tool(self):
        schema_names = {t["function"]["name"] for t in COPILOT_TOOLS_SCHEMA}
        for prompt, tool_name, args in PROMPT_TOOL_FIXTURE:
            self.assertIn(tool_name, copilot.TOOL_MAP, f"{tool_name} missing from TOOL_MAP")
            self.assertIn(tool_name, schema_names, f"{tool_name} missing from schema")

            captured: dict = {}

            def fake_exec(name, arguments, _captured=captured):
                _captured["name"] = name
                _captured["args"] = arguments
                return {"success": True, "message": "ok"}

            assistant_msg = {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"function": {"name": tool_name, "arguments": json.dumps(args)}}
                ],
            }
            with patch("agent.copilot.chat_with_tools", return_value=assistant_msg), \
                 patch("agent.copilot.execute_tool", side_effect=fake_exec), \
                 patch("agent.copilot.generate_stream", return_value=iter(["ok"])):
                copilot.run_copilot(prompt)

            self.assertEqual(captured.get("name"), tool_name)
            self.assertEqual(captured.get("args"), args)

    def test_unknown_argument_returns_guided_error(self):
        res = copilot.execute_tool("get_spending_by_category", {"nonsense": 1})
        self.assertFalse(res["success"])
        self.assertIn("does not accept", res["message"])

    def test_declared_argument_is_accepted(self):
        res = copilot.execute_tool("get_spending_by_category", {"year": 2026, "month": 9})
        self.assertTrue(res["success"])


class TestMortgageFormatting(unittest.TestCase):
    def test_schedule_rows_carry_euro_twins(self):
        lib = {
            "id": 1,
            "name": "Loan",
            "original_principal_minor": 1000000,
            "home_value_minor": 5000000,
            "balance_override_minor": None,
        }
        rate = {"annual_rate": 3.0, "fixed_until": "2030-01-01"}
        schedule = {
            "due_date": "2026-11-01",
            "payment_minor": 100000,
            "interest_minor": 30000,
            "principal_minor": 70000,
            "balance_minor": 900000,
        }
        conn = MagicMock()
        conn.execute.return_value.fetchall.side_effect = [[lib], [schedule]]
        conn.execute.return_value.fetchone.return_value = rate

        with patch("db.database.connect_readonly", return_value=conn):
            res = tools.tool_analyze_mortgage()

        row = res["mortgages"][0]["upcoming_schedule"][0]
        self.assertEqual(row["payment_eur"], "€1,000.00")
        self.assertEqual(row["interest_eur"], "€300.00")
        self.assertEqual(row["balance_eur"], "€9,000.00")
        self.assertEqual(res["mortgages"][0]["liability"]["original_principal_eur"], "€10,000.00")


if __name__ == "__main__":
    unittest.main()
