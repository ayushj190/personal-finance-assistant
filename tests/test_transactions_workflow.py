import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch
import pandas as pd

from db.database import (
    bulk_categorize_transactions,
    connect,
    delete_transactions,
    migrate,
    set_transactions_internal_transfer,
    upsert_account,
    upsert_transactions,
)
from ui.dialogs import confirm_delete_transactions_dialog
from ui.pages.transactions import render


class TestTransactionsWorkflow(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_tx_workflow.db")
        migrate(self.db_path)
        self.conn = connect(self.db_path)
        self._open_conns = [self.conn]

        self.acc_id = upsert_account(
            self.conn,
            {
                "provider": "manual",
                "institution": "ABN AMRO",
                "name": "Checking",
                "currency": "EUR",
                "asset_class": "cash",
                "external_id": "abn_wf_test",
            },
        )

        self.txs = [
            {
                "account_id": self.acc_id,
                "dedup_hash": f"hash_tx_wf_{i}",
                "booking_date": f"2026-10-0{i}",
                "amount_minor": -2500 * i,
                "currency": "EUR",
                "amount_eur_minor": -2500 * i,
                "description_raw": f"Payment to Merchant {i}",
                "merchant_normalized": f"Merchant {i}",
                "source": "csv",
            }
            for i in range(1, 4)
        ]
        upsert_transactions(self.conn, self.txs)
        rows = self.conn.execute("SELECT id FROM transactions ORDER BY id ASC").fetchall()
        self.tx_ids = [r["id"] for r in rows]

    def tearDown(self):
        for c in self._open_conns:
            try:
                c.close()
            except Exception:
                pass
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass


    def test_ac5_mark_and_unmark_transfer_atomic(self):
        """AC-5, AC-7: Mark Transfer sets is_internal_transfer=1 and Transfer category; Unmark reverts to 0."""
        # Mark transfer
        count = set_transactions_internal_transfer(self.conn, self.tx_ids[:2], is_transfer=True)
        self.assertEqual(count, 2)

        rows = self.conn.execute(
            "SELECT id, is_internal_transfer, category_id, category_source FROM transactions WHERE id IN (?, ?)",
            (self.tx_ids[0], self.tx_ids[1]),
        ).fetchall()
        for r in rows:
            self.assertEqual(r["is_internal_transfer"], 1)
            self.assertEqual(r["category_source"], "user")
            self.assertIsNotNone(r["category_id"])

        # Third transaction remains untouched
        row3 = self.conn.execute("SELECT is_internal_transfer FROM transactions WHERE id = ?", (self.tx_ids[2],)).fetchone()
        self.assertEqual(row3["is_internal_transfer"], 0)

        # Unmark transfer
        unmark_count = set_transactions_internal_transfer(self.conn, [self.tx_ids[0]], is_transfer=False)
        self.assertEqual(unmark_count, 1)
        row1 = self.conn.execute("SELECT is_internal_transfer FROM transactions WHERE id = ?", (self.tx_ids[0],)).fetchone()
        self.assertEqual(row1["is_internal_transfer"], 0)

    def test_ac6_bulk_categorize_with_and_without_rules(self):
        """AC-6, AC-7: Bulk categorize updates category_id, category_source, and optionally merchant rules."""
        cat_row = self.conn.execute("SELECT id FROM categories WHERE kind = 'discretionary' LIMIT 1").fetchone()
        self.assertIsNotNone(cat_row)
        target_cat_id = cat_row["id"]

        # 1. Bulk categorize without rule updates
        count = bulk_categorize_transactions(
            self.conn,
            [self.tx_ids[0]],
            target_cat_id,
            source="user",
            update_rules=False,
        )
        self.assertEqual(count, 1)

        row1 = self.conn.execute("SELECT category_id, category_source FROM transactions WHERE id = ?", (self.tx_ids[0],)).fetchone()
        self.assertEqual(row1["category_id"], target_cat_id)
        self.assertEqual(row1["category_source"], "user")

        rule1 = self.conn.execute(
            "SELECT * FROM merchant_category_rules WHERE merchant_normalized = 'Merchant 1'"
        ).fetchone()
        self.assertIsNone(rule1)

        # 2. Bulk categorize with rule updates
        count2 = bulk_categorize_transactions(
            self.conn,
            [self.tx_ids[1], self.tx_ids[2]],
            target_cat_id,
            source="user",
            update_rules=True,
        )
        self.assertEqual(count2, 2)

        rule2 = self.conn.execute(
            "SELECT category_id, source, confidence FROM merchant_category_rules WHERE merchant_normalized = 'Merchant 2'"
        ).fetchone()
        self.assertIsNotNone(rule2)
        self.assertEqual(rule2["category_id"], target_cat_id)
        self.assertEqual(rule2["source"], "user")
        self.assertEqual(rule2["confidence"], 1.0)

    def test_ac5_delete_selected_confirmation_dialog_decorated(self):
        """AC-5: confirm_delete_transactions_dialog is decorated as a Streamlit modal dialog."""
        self.assertTrue(
            hasattr(confirm_delete_transactions_dialog, "__wrapped__"),
            "confirm_delete_transactions_dialog must be decorated with @st.dialog",
        )

    def test_ac7_delete_transactions_atomic(self):
        """AC-5, AC-7: delete_transactions removes rows atomically from SQLite."""
        deleted = delete_transactions(self.conn, [self.tx_ids[0], self.tx_ids[1]])
        self.assertEqual(deleted, 2)

        remaining = self.conn.execute("SELECT id FROM transactions").fetchall()
        self.assertEqual(len(remaining), 1)
        self.assertEqual(remaining[0]["id"], self.tx_ids[2])

    @patch("streamlit.data_editor")
    @patch("streamlit.button")
    @patch("streamlit.columns")
    @patch("streamlit.text_input")
    @patch("streamlit.checkbox")
    @patch("streamlit.markdown")
    @patch("streamlit.caption")
    @patch("db.database.connect")
    def test_ac4_transactions_page_renders_with_select_and_no_inline_transfer_col(
        self,
        mock_connect,
        mock_caption,
        mock_markdown,
        mock_checkbox,
        mock_text_input,
        mock_columns,
        mock_button,
        mock_data_editor,
    ):
        """AC-4: transactions page includes select column, omits inline transfer checkbox, provides helper buttons."""
        def open_conn(*a, **kw):
            c = connect(self.db_path)
            self._open_conns.append(c)
            return c

        mock_connect.side_effect = open_conn
        mock_checkbox.return_value = False
        mock_text_input.return_value = ""
        mock_button.return_value = False

        mock_columns.side_effect = lambda spec, *a, **kw: [MagicMock() for _ in range(len(spec) if isinstance(spec, list) else spec)]


        # Setup mock data_editor return
        mock_df = pd.DataFrame(
            [
                {
                    "select": False,
                    "id": self.tx_ids[0],
                    "booking_date": "2026-10-01",
                    "account": "Checking",
                    "amount_eur": -25.00,
                    "merchant": "Merchant 1",
                    "category": "Groceries",
                    "is_internal_transfer": 0,
                }
            ]
        )
        mock_data_editor.return_value = mock_df

        render()

        # Verify data_editor was called
        self.assertTrue(mock_data_editor.called)
        call_args = mock_data_editor.call_args
        df_passed = call_args[0][0]
        kwargs_passed = call_args[1]

        # Check 'select' column exists in passed dataframe
        self.assertIn("select", df_passed.columns)
        self.assertEqual(df_passed.columns[0], "select")

        # Check column config: 'select' is CheckboxColumn, 'is_internal_transfer' is None (removed from inline editing)
        col_cfg = kwargs_passed.get("column_config", {})
        self.assertIn("select", col_cfg)
        self.assertIsNone(col_cfg.get("is_internal_transfer"))


if __name__ == "__main__":
    unittest.main()
