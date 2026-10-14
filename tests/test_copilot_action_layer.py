"""Tests for the Copilot action layer (spec 0017).

Drives the intent construction, commit on completion, whitelist rejection, the
fast path, the shared date resolver, and the masking rule with a fake model
harness, so nothing here needs Ollama (AC-1, AC-2, AC-3, AC-6, AC-9, AC-18,
AC-19, AC-21, AC-22).
"""

import json
import unittest
from datetime import date
from unittest.mock import patch

from agent import copilot
from agent.tool_schemas import COPILOT_TOOLS_SCHEMA
from agent.tools.navigation import tool_open_view
from services.date_scope import (
    PRESETS,
    is_aligned_fiscal_month,
    resolve_date_scope,
    spending_view_for_scope,
)
from services.navigation import (
    FILTERED_PAGES,
    PAGE_IDS,
    TAB_MAP,
    match_fast_path,
    topic_map_intent,
)
from ui.components import mask_if_hidden

TODAY = date(2026, 10, 13)


class TestDateResolver(unittest.TestCase):
    def test_presets_match_filter_widget_rules(self):
        cases = {
            "MTD": ("2026-10-01", "2026-10-13"),
            "Last Month": ("2026-09-01", "2026-09-30"),
            "Last 3 Months": ("2026-07-15", "2026-10-13"),
            "YTD": ("2026-01-01", "2026-10-13"),
            "Last 12 Months": ("2025-10-13", "2026-10-13"),
            "All Time": (None, "2026-10-13"),
        }
        for preset in PRESETS:
            resolved = resolve_date_scope({"preset": preset}, TODAY)
            self.assertEqual(resolved["start_iso"], cases[preset][0], preset)
            self.assertEqual(resolved["end_iso"], cases[preset][1], preset)

    def test_explicit_range_uses_most_recent_past_occurrence(self):
        resolved = resolve_date_scope({"start": "2027-01-01", "end": "2027-03-31"}, TODAY)
        self.assertEqual(resolved["start_iso"], "2026-01-01")
        self.assertEqual(resolved["end_iso"], "2026-03-31")

    def test_explicit_range_month_end_when_first_of_month(self):
        resolved = resolve_date_scope({"start": "2026-01-01", "end": "2026-02-01"}, TODAY)
        self.assertEqual(resolved["end_iso"], "2026-02-28")

    def test_start_after_end_is_error(self):
        resolved = resolve_date_scope({"start": "2026-05-01", "end": "2026-03-31"}, TODAY)
        self.assertTrue(resolved["error"])

    def test_future_end_is_clamped(self):
        resolved = resolve_date_scope({"start": "2026-09-01", "end": "2026-12-31"}, TODAY)
        self.assertEqual(resolved["end_iso"], "2026-10-13")

    def test_day_window(self):
        resolved = resolve_date_scope("past 90 days", TODAY)
        self.assertEqual(resolved["start_iso"], "2026-07-15")

    def test_unknown_phrase_is_error(self):
        self.assertTrue(resolve_date_scope("whenever", TODAY)["error"])

    def test_no_scope_is_not_requested(self):
        resolved = resolve_date_scope(None, TODAY)
        self.assertFalse(resolved["requested"])


class TestSpendingScopeMapping(unittest.TestCase):
    def test_multi_month_maps_to_all_months(self):
        resolved = resolve_date_scope({"preset": "Last 3 Months"}, TODAY)
        self.assertEqual(spending_view_for_scope(resolved, 1)["option"], "All Months (Monthly Average)")

    def test_single_fiscal_month_selects_that_month(self):
        resolved = resolve_date_scope({"preset": "Last Month"}, TODAY)
        mapped = spending_view_for_scope(resolved, 1)
        self.assertEqual(mapped["option"], "2026-09")

    def test_non_aligned_explicit_range_shows_custom_caption(self):
        resolved = resolve_date_scope({"start": "2026-01-05", "end": "2026-02-20"}, TODAY)
        mapped = spending_view_for_scope(resolved, 1)
        self.assertIn("Custom range", mapped["caption"])

    def test_aligned_fiscal_month_detection(self):
        self.assertEqual(is_aligned_fiscal_month(date(2026, 9, 1), date(2026, 9, 30), 1), "2026-09")
        self.assertIsNone(is_aligned_fiscal_month(date(2026, 9, 2), date(2026, 9, 30), 1))


class TestOpenViewTool(unittest.TestCase):
    def test_unknown_page_is_rejected(self):
        res = tool_open_view("nowhere")
        self.assertFalse(res["success"])
        self.assertNotIn("ui_intent", res)

    def test_unknown_tab_is_rejected(self):
        res = tool_open_view("investments", tab="bogus")
        self.assertFalse(res["success"])

    def test_tab_on_page_without_tabs_is_ignored_with_note(self):
        res = tool_open_view("spending", tab="allocation")
        self.assertTrue(res["success"])
        self.assertIsNone(res["tab"])
        self.assertIn("no tabs", res["message"])

    def test_scope_on_unfiltered_page_gets_no_date_scope_note(self):
        res = tool_open_view("investments", date_scope={"preset": "Last Month"})
        self.assertTrue(res["success"])
        self.assertIn("no date scope", res["message"])
        self.assertNotIn("Applied scope", res["message"])

    def test_scope_on_filtered_page_appends_applied_scope(self):
        res = tool_open_view("spending", date_scope={"preset": "Last Month"})
        self.assertIn("Applied scope: 2026-09-01", res["message"])
        self.assertEqual(res["ui_intent"]["date_scope"]["preset"], "Last Month")

    def test_every_valid_page_and_tab_is_accepted(self):
        for page in PAGE_IDS:
            self.assertTrue(tool_open_view(page)["success"], page)
        for tab in TAB_MAP:
            self.assertTrue(tool_open_view("investments", tab=tab)["success"], tab)

    def test_filtered_pages_constant_is_exactly_spending_and_transactions(self):
        self.assertEqual(set(FILTERED_PAGES), {"spending", "transactions"})


class TestFastPath(unittest.TestCase):
    def test_explicit_navigation_verbs_open_pages(self):
        self.assertEqual(match_fast_path("open spending")["page"], "spending")
        self.assertEqual(match_fast_path("go to tax analysis")["page"], "tax")
        self.assertEqual(match_fast_path("go to rebalancing")["tab"], "allocation")

    def test_content_verbs_no_longer_use_the_fast_path(self):
        # AC-6: the content verbs are removed so a content question reaches the model.
        self.assertIsNone(match_fast_path("show my transactions"))
        self.assertIsNone(match_fast_path("show me my spending for last month"))
        self.assertIsNone(match_fast_path("view my portfolio"))
        self.assertIsNone(match_fast_path("display my holdings"))

    def test_ambiguous_phrase_falls_through(self):
        self.assertIsNone(match_fast_path("show me the last thing"))
        self.assertIsNone(match_fast_path("what are my expenses"))

    def test_fast_path_attaches_preset(self):
        intent = match_fast_path("open spending for last month")
        self.assertEqual(intent["date_scope"]["preset"], "Last Month")
        self.assertTrue(intent["date_scope"]["requested"])


class TestFakeModelHarness(unittest.TestCase):
    """A scripted model drives intent construction with no Ollama (AC-22)."""

    def _run_with_tool(self, tool_name, args):
        assistant_msg = {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"function": {"name": tool_name, "arguments": json.dumps(args)}}],
        }
        with patch("agent.copilot.chat_with_tools", return_value=assistant_msg), \
             patch("agent.copilot.generate_stream", return_value=iter(["ok"])):
            return copilot.run_copilot("a prompt")

    def test_open_view_builds_intent(self):
        res = self._run_with_tool("open_view", {"page": "spending", "date_scope": {"preset": "Last Month"}})
        self.assertIsNotNone(res["ui_intent"])
        self.assertEqual(res["ui_intent"]["page"], "spending")

    def test_navigation_survives_a_failed_data_tool(self):
        # AC-4: a failed data tool must not also lose the page the question asked for.
        assistant_msg = {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {"function": {"name": "open_view", "arguments": json.dumps({"page": "spending"})}},
                {"function": {"name": "get_spending_by_category", "arguments": json.dumps({"year": 1850})}},
            ],
        }
        with patch("agent.copilot.chat_with_tools", return_value=assistant_msg), \
             patch("agent.copilot.generate_stream", return_value=iter(["ok"])):
            res = copilot.run_copilot("tell me about my spending")
        self.assertIsNotNone(res["ui_intent"])
        self.assertEqual(res["ui_intent"]["page"], "spending")

    def test_clarifying_turn_moves_nothing(self):
        assistant_msg = {"role": "assistant", "content": "Did you mean Spending or Transactions?", "tool_calls": []}
        with patch("agent.copilot.chat_with_tools", return_value=assistant_msg):
            res = copilot.run_copilot("show me the last thing")
        self.assertIsNone(res["ui_intent"])

    def test_scope_is_inherited_by_a_later_data_call(self):
        assistant_msg = {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {"function": {"name": "open_view", "arguments": json.dumps({"page": "spending", "date_scope": {"preset": "Last Month"}})}},
                {"function": {"name": "get_spending_by_category", "arguments": json.dumps({})}},
            ],
        }
        captured = {}

        def fake_exec(name, arguments):
            captured[name] = arguments
            if name == "open_view":
                return tool_open_view(**arguments)
            return {"success": True, "message": "ok"}

        with patch("agent.copilot.chat_with_tools", return_value=assistant_msg), \
             patch("agent.copilot.execute_tool", side_effect=fake_exec), \
             patch("agent.copilot.generate_stream", return_value=iter(["ok"])):
            copilot.run_copilot("what did I spend last month")

        self.assertEqual(captured["get_spending_by_category"].get("date_scope"), {"preset": "Last Month"})

    def test_explicit_navigation_prompt_set_maps_pages(self):
        """AC-6: explicit navigation phrasing stays instant with no model call."""
        prompts = {
            "open my dashboard": "dashboard",
            "go to my holdings": "investments",
            "open my mortgage": "mortgage",
            "open tax analysis": "tax",
            "go to settings": "settings",
        }
        for prompt, page in prompts.items():
            intent = match_fast_path(prompt)
            self.assertTrue(intent and intent["page"] == page, prompt)

    def test_content_prompt_set_routes_via_topic_map(self):
        """AC-1 / AC-2 / AC-5 / AC-6: a content question routes without an explicit verb."""
        prompts = {
            "what did I spend over the past 3 months": "spending",
            "which tech stocks and ETFs do I hold": "investments",
            "how much do I owe on my mortgage": "mortgage",
            "what is my tax situation": "tax",
            "show me my recent transactions": "transactions",
            "how has my net worth changed": "dashboard",
        }
        for prompt, page in prompts.items():
            self.assertIsNone(match_fast_path(prompt), prompt)
            intent = topic_map_intent(prompt)
            self.assertTrue(intent and intent["page"] == page, prompt)


class TestMasking(unittest.TestCase):
    def test_money_masks_identifiers_stay(self):
        with patch("streamlit.session_state", {"hide_amounts": True}):
            self.assertEqual(mask_if_hidden("€1,234.56 spent"), "€**** spent")
            self.assertEqual(mask_if_hidden("$500.00 in eToro"), "$**** in eToro")
            self.assertEqual(mask_if_hidden("12.5% allocation"), "12.5% allocation")
            self.assertEqual(mask_if_hidden("AAPL +3.1%"), "AAPL +3.1%")
            self.assertEqual(mask_if_hidden("42 assets, 7 delayed"), "42 assets, 7 delayed")


class TestToolSchema(unittest.TestCase):
    def test_open_view_is_in_the_schema(self):
        names = {t["function"]["name"] for t in COPILOT_TOOLS_SCHEMA}
        self.assertIn("open_view", names)

    def test_data_tools_expose_date_scope(self):
        by_name = {t["function"]["name"]: t for t in COPILOT_TOOLS_SCHEMA}
        for name in ("get_spending_by_category", "get_recent_transactions", "get_monthly_cashflow"):
            self.assertIn("date_scope", by_name[name]["function"]["parameters"]["properties"])


if __name__ == "__main__":
    unittest.main()
