"""Regression net for Copilot view intelligence (spec 0019).

Covers the view whitelist, the deterministic topic map, the shared page panel session
keys, the seven read tools, and the confirm gated write tokens, with no Ollama
(AC-1, AC-2, AC-3, AC-6, AC-7, AC-8, AC-14).
"""

import os
import tempfile
import unittest
from unittest.mock import patch

from agent.tools.actions import _args_token
from agent.tools.actions import (
    tool_categorize_transactions,
    tool_delete_transaction,
    tool_edit_transaction,
    tool_mark_as_transfer,
    tool_set_budget_cap,
)
from agent.tools.insights import (
    tool_compare_periods,
    tool_get_account_balances,
    tool_get_budget_status,
    tool_get_income_summary,
    tool_get_net_worth_history,
    tool_get_spending_forecast,
    tool_get_upcoming_bills,
)
from agent.tools.navigation import tool_open_view
from services.navigation import EXPOSURE_DIMENSIONS, VIEW_WHITELIST, topic_map_intent
from ui import page_panel, state


class TestTopicMap(unittest.TestCase):
    def test_one_question_per_domain_routes(self):
        cases = {
            "what did I spend over the past 3 months": "spending",
            "which tech stocks and ETFs do I hold": "investments",
            "how much do I owe on my mortgage": "mortgage",
            "what is my tax situation": "tax",
            "show me my recent transactions": "transactions",
            "how has my net worth changed": "dashboard",
        }
        for prompt, page in cases.items():
            intent = topic_map_intent(prompt)
            self.assertIsNotNone(intent, prompt)
            self.assertEqual(intent["page"], page, prompt)

    def test_weak_prompt_moves_nothing(self):
        self.assertIsNone(topic_map_intent("hello there"))
        self.assertIsNone(topic_map_intent("what is the weather"))

    def test_tie_moves_nothing(self):
        self.assertIsNone(topic_map_intent("compare my tax and mortgage"))

    def test_topic_map_carries_requested_scope(self):
        intent = topic_map_intent(
            "what did I spend", date_scope={"preset": "Last 3 Months"}
        )
        self.assertTrue(intent["date_scope"]["requested"])
        self.assertEqual(intent["date_scope"]["preset"], "Last 3 Months")


class TestViewWhitelist(unittest.TestCase):
    def test_whitelist_shape(self):
        self.assertEqual(VIEW_WHITELIST["spending"], ("category",))
        self.assertEqual(set(VIEW_WHITELIST["transactions"]), {"category", "search"})
        self.assertEqual(
            set(VIEW_WHITELIST["investments"]), {"exposure_dimension", "focus"}
        )

    def test_unknown_view_key_is_ignored_with_note(self):
        res = tool_open_view("spending", view={"focus": "Technology"})
        self.assertTrue(res["success"])
        self.assertEqual(res["view"], {})
        self.assertIn("Ignored unknown view option 'focus'", res["note"])

    def test_invalid_dimension_is_ignored(self):
        res = tool_open_view("investments", view={"exposure_dimension": "Food"})
        self.assertEqual(res["view"], {})
        self.assertIn("Ignored exposure dimension", res["note"])

    def test_valid_dimension_is_kept(self):
        for dim in EXPOSURE_DIMENSIONS:
            res = tool_open_view("investments", view={"exposure_dimension": dim})
            self.assertEqual(res["view"]["exposure_dimension"], dim)

    def test_category_and_search_are_kept(self):
        res = tool_open_view(
            "transactions", view={"category": "Groceries", "search": "albert"}
        )
        self.assertEqual(res["view"], {"category": "Groceries", "search": "albert"})


class TestPagePanel(unittest.TestCase):
    def test_set_and_clear_panel(self):
        with patch("streamlit.session_state", {}):
            page_panel.set_panel("spending", object(), "Headline")
            stored = state.get(state.K.COPILOT_PAGE_PANEL)
            self.assertEqual(stored["page"], "spending")
            self.assertEqual(stored["headline"], "Headline")
            page_panel.clear_panel()
            self.assertIsNone(state.get(state.K.COPILOT_PAGE_PANEL))


class TestReadTools(unittest.TestCase):
    def test_compare_periods_returns_success(self):
        res = tool_compare_periods({"preset": "Last Month"}, {"preset": "MTD"})
        self.assertTrue(res["success"])
        self.assertIn("delta_spending_eur", res)

    def test_account_balances(self):
        res = tool_get_account_balances()
        self.assertTrue(res["success"])
        self.assertIn("accounts", res)

    def test_budget_status(self):
        res = tool_get_budget_status()
        self.assertTrue(res["success"])
        self.assertIn("total_budget_eur", res)

    def test_spending_forecast(self):
        res = tool_get_spending_forecast()
        self.assertTrue(res["success"])
        self.assertIn("projected_month_end_eur", res)

    def test_income_summary(self):
        res = tool_get_income_summary()
        self.assertTrue(res["success"])
        self.assertIn("income_eur", res)

    def test_upcoming_bills(self):
        res = tool_get_upcoming_bills()
        self.assertTrue(res["success"])
        self.assertIn("bills", res)

    def test_net_worth_history_is_approximate(self):
        res = tool_get_net_worth_history()
        self.assertTrue(res["success"])
        self.assertTrue(res["approximate"])


class TestConfirmGatedWrites(unittest.TestCase):
    def _temp_db(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        db_path = os.path.join(tmp.name, "view_intel.db")
        from db.database import migrate
        from db import database
        from db.repositories import AccountRepository

        migrate(db_path)
        conn = database.connect(db_path)
        try:
            acc_id = AccountRepository.upsert(
                conn,
                {
                    "provider": "manual",
                    "institution": "Test Bank",
                    "external_id": "test_acc",
                    "name": "Test Account",
                    "currency": "EUR",
                    "asset_class": "cash",
                },
            )
            with conn:
                cur = conn.execute(
                    """
                    INSERT INTO transactions
                        (account_id, dedup_hash, booking_date, amount_minor, currency,
                         amount_eur_minor, description_raw, merchant_normalized,
                         is_internal_transfer, source)
                    VALUES (?, 'h1', '2026-10-01', -1000, 'EUR', -1000, 'Test Merchant',
                            'Test Merchant', 0, 'csv')
                    """,
                    (acc_id,),
                )
                tx_id = cur.lastrowid
            cat = conn.execute(
                "SELECT name FROM categories WHERE name != 'Uncategorized' ORDER BY name LIMIT 1"
            ).fetchone()
        finally:
            conn.close()
        return db_path, cat["name"], int(tx_id)

    def test_args_token_is_deterministic_and_order_stable(self):
        self.assertEqual(_args_token("x", 1, "a"), _args_token("x", 1, "a"))
        self.assertNotEqual(_args_token("x", 1, "a"), _args_token("x", 1, "b"))

    def test_delete_proposes_then_applies_and_refuses_wrong_token(self):
        db_path, _cat, tx_id = self._temp_db()
        with patch("agent.tools.actions.DB_PATH", db_path):
            proposal = tool_delete_transaction(tx_id)
            self.assertTrue(proposal["success"])
            self.assertTrue(proposal["confirm_token"])
            refused = tool_delete_transaction(tx_id, confirm_token="deadbeef")
            self.assertFalse(refused["success"])
            applied = tool_delete_transaction(
                tx_id, confirm_token=proposal["confirm_token"]
            )
            self.assertTrue(applied["deleted"])

    def test_set_budget_cap_proposes_then_applies_and_refuses_mismatch(self):
        db_path, cat_name, _tx = self._temp_db()
        with patch("agent.tools.actions.DB_PATH", db_path):
            proposal = tool_set_budget_cap(cat_name, 200.0)
            self.assertTrue(proposal["success"])
            refused = tool_set_budget_cap(
                cat_name, 999.0, confirm_token=proposal["confirm_token"]
            )
            self.assertFalse(refused["success"])
            applied = tool_set_budget_cap(
                cat_name, 200.0, confirm_token=proposal["confirm_token"]
            )
            self.assertTrue(applied["success"])

    def test_categorize_and_transfer_and_edit(self):
        db_path, cat_name, tx_id = self._temp_db()
        with patch("agent.tools.actions.DB_PATH", db_path):
            cp = tool_categorize_transactions(cat_name, transaction_ids=[tx_id])
            ca = tool_categorize_transactions(
                cat_name, transaction_ids=[tx_id], confirm_token=cp["confirm_token"]
            )
            self.assertEqual(ca.get("updated"), 1)

            tp = tool_mark_as_transfer([tx_id])
            ta = tool_mark_as_transfer([tx_id], confirm_token=tp["confirm_token"])
            self.assertEqual(ta.get("updated"), 1)

            ep = tool_edit_transaction(tx_id, description="Edited")
            ea = tool_edit_transaction(
                tx_id, description="Edited", confirm_token=ep["confirm_token"]
            )
            self.assertTrue(ea["success"])


if __name__ == "__main__":
    unittest.main()
