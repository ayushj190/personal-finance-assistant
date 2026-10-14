"""Regression net for Copilot tool call reliability (spec 0022).

Covers the dropped date_scope argument path, navigation on a failed turn, the
grounding gate, and the net worth wording, with no Ollama (AC-1 to AC-7).
"""

import contextlib
import json
import re
import unittest
from unittest.mock import patch

from agent import copilot
from agent.tool_schemas import COPILOT_TOOLS_SCHEMA
from agent.tools.insights import tool_get_net_worth_history, tool_get_spending_forecast
from agent.tools.navigation import tool_open_view


def _assistant_msg(tool_calls):
    return {
        "role": "assistant",
        "content": "",
        "tool_calls": [
            {"function": {"name": name, "arguments": json.dumps(args)}}
            for name, args in tool_calls
        ],
    }


def _run(prompt, tool_calls, stream_text="ok", execute=None):
    """Drive a Copilot turn with a scripted model and a fixed answer stream."""
    msg = _assistant_msg(tool_calls)
    with contextlib.ExitStack() as stack:
        stack.enter_context(patch("agent.copilot.chat_with_tools", return_value=msg))
        stack.enter_context(
            patch("agent.copilot.generate_stream", return_value=iter([stream_text]))
        )
        if execute is not None:
            stack.enter_context(
                patch("agent.copilot.execute_tool", side_effect=execute)
            )
        return copilot.run_copilot(prompt)


def _fake_exec(name, arguments):
    """open_view behaves for real; every other tool reports success with no data."""
    if name == "open_view":
        return tool_open_view(**arguments)
    return {"success": True, "message": "ok"}


class TestForecastDateScope(unittest.TestCase):
    """AC-1: the forecast accepts a period and its schema declares it."""

    def test_schema_declares_date_scope(self):
        by_name = {t["function"]["name"]: t for t in COPILOT_TOOLS_SCHEMA}
        self.assertIn(
            "date_scope",
            by_name["get_spending_forecast"]["function"]["parameters"]["properties"],
        )

    def test_scoped_forecast_reports_the_window(self):
        res = tool_get_spending_forecast(date_scope={"preset": "Last Month"})
        self.assertTrue(res["success"], res.get("message"))
        self.assertIn("projected_month_end_eur", res)
        self.assertIn("over ", res["period"])
        self.assertGreaterEqual(res["months_count"], 1)

    def test_unscoped_forecast_keeps_the_trailing_behavior(self):
        res = tool_get_spending_forecast()
        self.assertTrue(res["success"], res.get("message"))
        self.assertIn("projected_month_end_eur", res)
        self.assertEqual(res["period"], "over the last 3 months")

    def test_unknown_scope_is_rejected(self):
        res = tool_get_spending_forecast(date_scope="whenever")
        self.assertFalse(res["success"])


class TestDroppedDateScope(unittest.TestCase):
    """AC-3: a benign date_scope is dropped; any other unknown argument still errors."""

    def test_benign_date_scope_is_dropped_and_the_tool_runs(self):
        res = copilot.execute_tool(
            "get_current_net_worth", {"date_scope": {"preset": "Last Month"}}
        )
        self.assertNotEqual(res.get("success"), False)
        self.assertEqual(res["diagnostics"]["error_type"], "DroppedArgument")

    def test_other_unknown_argument_still_returns_the_guided_error(self):
        res = copilot.execute_tool("get_current_net_worth", {"nonsense": 1})
        self.assertFalse(res["success"])
        self.assertIn("does not accept", res["message"])
        self.assertEqual(res["diagnostics"]["error_type"], "UnknownArgumentError")

    def test_declared_date_scope_is_passed_through(self):
        res = copilot.execute_tool(
            "get_spending_by_category", {"date_scope": {"preset": "Last Month"}}
        )
        self.assertTrue(res["success"], res.get("message"))
        self.assertNotEqual(
            (res.get("diagnostics") or {}).get("error_type"), "DroppedArgument"
        )


class TestNavigationOnFailedTurn(unittest.TestCase):
    """AC-4: the page still opens when a data tool fails."""

    def test_page_opens_when_a_data_tool_fails(self):
        def failing(name, arguments):
            if name == "open_view":
                return tool_open_view(**arguments)
            return {"success": False, "message": "boom"}

        res = _run(
            "tell me about my spending",
            [("open_view", {"page": "spending"}), ("get_spending_by_category", {})],
            execute=failing,
        )
        self.assertIsNotNone(res["ui_intent"])
        self.assertEqual(res["ui_intent"]["page"], "spending")

    def test_topic_map_fallback_still_routes_on_failure(self):
        def failing(name, arguments):
            return {"success": False, "message": "boom"}

        res = _run(
            "what did I spend over the past 3 months",
            [("get_spending_by_category", {})],
            execute=failing,
        )
        self.assertIsNotNone(res["ui_intent"])
        self.assertEqual(res["ui_intent"]["page"], "spending")


class TestGroundingGate(unittest.TestCase):
    """AC-5: an invented figure cannot reach the user."""

    def test_invented_figure_is_replaced_when_only_navigation_succeeds(self):
        res = _run(
            "what is my portfolio allocation",
            [("open_view", {"page": "investments"})],
            stream_text="Your portfolio is 45% stocks and 30% bonds.",
            execute=_fake_exec,
        )
        text = "".join(res["stream"])
        self.assertIn("could not retrieve", text)
        self.assertNotIn("45%", text)

    def test_fallback_repeats_the_tool_failure_guidance(self):
        def failing(name, arguments):
            if name == "open_view":
                return tool_open_view(**arguments)
            return {"success": False, "message": "Could not read the ledger."}

        res = _run(
            "what is my spending",
            [("open_view", {"page": "spending"}), ("get_spending_by_category", {})],
            stream_text="You spent €999.00 last month.",
            execute=failing,
        )
        text = "".join(res["stream"])
        self.assertIn("Could not read the ledger.", text)
        self.assertNotIn("999", text)

    def test_grounded_answer_passes_through(self):
        res = _run(
            "what is my portfolio worth",
            [("open_view", {"page": "investments"}), ("analyze_investments", {})],
            stream_text="Your portfolio is €12,345.00.",
            execute=_fake_exec,
        )
        text = "".join(res["stream"])
        self.assertIn("€12,345.00", text)

    def test_ungrounded_answer_without_a_figure_is_kept(self):
        res = _run(
            "how is my spending looking",
            [("open_view", {"page": "spending"})],
            stream_text="I opened the Spending page.",
            execute=_fake_exec,
        )
        text = "".join(res["stream"])
        self.assertIn("I opened the Spending page.", text)


class TestNetWorthWording(unittest.TestCase):
    """AC-6: the trend states its scope and points to the true figure."""

    def test_trend_states_its_scope(self):
        res = tool_get_net_worth_history()
        self.assertTrue(res["success"])
        self.assertIn("home equity", res["message"])
        self.assertIn("invested", res["message"])
        self.assertIn("get_current_net_worth", res["message"])
        self.assertIn("approximate", res["headline"].lower())

    def test_prompt_repeats_the_trend_scope(self):
        prompt = copilot.SYSTEM_PROMPT
        self.assertIn("home equity", prompt)
        self.assertIn("get_current_net_worth", prompt)


class TestPromptDateScopeRules(unittest.TestCase):
    """AC-2: the prompt names exactly the tools that accept a period."""

    def test_prompt_forbids_a_period_on_other_tools(self):
        self.assertIn("DATE SCOPE RULES", copilot.SYSTEM_PROMPT)
        self.assertIn("Never pass a period", copilot.SYSTEM_PROMPT)

    def test_prompt_lists_exactly_the_date_scope_tools(self):
        by_name = {t["function"]["name"]: t for t in COPILOT_TOOLS_SCHEMA}
        declaring = {
            name
            for name, t in by_name.items()
            if "date_scope" in t["function"]["parameters"].get("properties", {})
        }
        line = next(
            ln
            for ln in copilot.SYSTEM_PROMPT.splitlines()
            if ln.startswith("- Only these tools accept a period")
        )
        named = set(re.findall(r"[a-z_]+", line)) & set(by_name)
        self.assertEqual(named, declaring)
        self.assertIn("get_spending_forecast", declaring)


if __name__ == "__main__":
    unittest.main()
