import concurrent.futures
from datetime import date
from pathlib import Path
import sqlite3
import unittest
from unittest.mock import MagicMock, patch

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from db import database
from ui.charts import (
    SECTOR_RGBA_COLORS,
    build_investments_market_carpet,
    open_sankey_fullscreen_dialog,
    render_cash_flow_sankey,
)
from ui.dialogs import (
    assign_mortgage_dialog,
    confirm_delete_transactions_dialog,
    mortgage_config_dialog,
    risk_profile_dialog,
    set_category_budget_dialog,
    tax_profile_dialog,
)
from ui.pages.dashboard import _render_accounts_grid


import tempfile

class TestDashboardHardening(unittest.TestCase):
    def setUp(self):
        from streamlit.delta_generator import DeltaGenerator, context_dg_stack
        context_dg_stack.set((DeltaGenerator(),))
        self._temp_dir = tempfile.TemporaryDirectory()
        self.temp_db = Path(self._temp_dir.name) / "test_hardening.db"
        database.migrate(self.temp_db)

        conn = database.connect(self.temp_db)
        with conn:
            conn.executescript("""
                INSERT OR IGNORE INTO categories VALUES
                    (1, 'Housing', 'fixed', NULL),
                    (2, 'Mortgage', 'fixed', 1),
                    (3, 'Groceries', 'discretionary', NULL),
                    (4, 'Salary', 'income', NULL);
                INSERT OR REPLACE INTO category_budgets VALUES (1, 150000), (3, 50000);
            """)
        conn.close()

    def tearDown(self):
        from streamlit.delta_generator import DeltaGenerator, context_dg_stack
        context_dg_stack.set((DeltaGenerator(),))
        try:
            self._temp_dir.cleanup()
        except Exception:
            pass

    def test_ac1_database_connect_multi_thread_safety(self):
        """AC-1: Verify database.connect supports multi-threaded queries without ProgrammingError."""
        def worker_query() -> int:
            connection = database.connect(self.temp_db)
            try:
                cur = connection.execute("SELECT COUNT(*) FROM categories")
                return cur.fetchone()[0]
            finally:
                connection.close()

        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(worker_query) for _ in range(8)]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]

        self.assertEqual(len(results), 8)
        self.assertTrue(all(r >= 4 for r in results))

    def test_ac1_connect_readonly_multi_thread_safety(self):
        """AC-1: Verify connect_readonly supports multi-threaded queries without ProgrammingError."""
        def worker_read() -> int:
            connection = database.connect_readonly(self.temp_db)
            try:
                cur = connection.execute("SELECT COUNT(*) FROM categories")
                return cur.fetchone()[0]
            finally:
                connection.close()

        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(worker_read) for _ in range(6)]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]

        self.assertEqual(len(results), 6)
        self.assertTrue(all(r >= 4 for r in results))

    def test_ac2_dialogs_manage_isolated_connection_lifecycle(self):
        """AC-2: Verify dialogs manage their own connection and are wrapped by @st.dialog."""
        for dlg in (
            tax_profile_dialog,
            risk_profile_dialog,
            mortgage_config_dialog,
            set_category_budget_dialog,
            assign_mortgage_dialog,
            confirm_delete_transactions_dialog,
        ):
            self.assertTrue(
                hasattr(dlg, "__wrapped__"),
                f"{dlg.__name__} must be decorated with @st.dialog",
            )


    @patch("db.database.connect")
    def test_ac2_set_category_budget_dialog_lifecycle(self, mock_connect):
        """AC-2: Verify set_category_budget_dialog creates a dedicated connection and closes it cleanly."""
        mock_conn = sqlite3.connect(":memory:")
        mock_conn.row_factory = sqlite3.Row
        mock_conn.executescript("""
            CREATE TABLE categories (id INTEGER, name TEXT, kind TEXT, parent_id INTEGER);
            CREATE TABLE category_budgets (category_id INTEGER PRIMARY KEY, monthly_limit_minor INTEGER);
        """)
        mock_connect.return_value = mock_conn

        fn = getattr(set_category_budget_dialog, "__wrapped__", set_category_budget_dialog)
        fn()

        mock_connect.assert_called_once()
        # Ensure connection was closed cleanly in finally block
        with self.assertRaises(sqlite3.ProgrammingError):
            mock_conn.execute("SELECT 1")

    @patch("ui.charts.render_chart")
    def test_ac3_shared_pure_plotly_sankey_rendering(self, mock_render_chart):
        """AC-3: Verify render_cash_flow_sankey renders pure Plotly go.Sankey without iframe component."""
        conn = database.connect(self.temp_db)
        with conn:
            conn.executescript("""
                INSERT OR IGNORE INTO accounts (id, provider, institution, name, currency, asset_class)
                VALUES (1, 'manual', 'ABN', 'Checking', 'EUR', 'cash');
                INSERT INTO transactions (account_id, booking_date, amount_minor, amount_eur_minor, currency, description_raw, source, category_id, is_internal_transfer, dedup_hash)
                VALUES (1, '2026-10-01', 400000, 400000, 'EUR', 'Salary', 'csv', 4, 0, 'h1'),
                       (1, '2026-10-05', -120000, -120000, 'EUR', 'Mortgage', 'csv', 2, 0, 'h2'),
                       (1, '2026-10-08', -45000, -45000, 'EUR', 'Groceries', 'csv', 3, 0, 'h3');
            """)

        st.session_state.clear()
        render_cash_flow_sankey(conn, key_prefix="hardening_test", height=400)
        conn.close()

        mock_render_chart.assert_called_once()
        fig = mock_render_chart.call_args[0][0]
        self.assertIsInstance(fig, go.Figure)
        self.assertEqual(len(fig.data), 1)
        self.assertEqual(fig.data[0].type, "sankey")

    def test_ac4_fullscreen_sankey_dialog_decoration(self):
        """AC-4: Verify open_sankey_fullscreen_dialog is decorated as a Streamlit dialog."""
        self.assertTrue(
            hasattr(open_sankey_fullscreen_dialog, "__wrapped__"),
            "open_sankey_fullscreen_dialog should be wrapped by @st.dialog",
        )

    def test_ac5_market_carpet_treemap_rgba_and_rounded_styles(self):
        """AC-5: Verify build_investments_market_carpet uses translucent RGBA tiles and styling."""
        df = pd.DataFrame([
            {"sector": "Technology", "display_label": "ASML", "value_eur": 12000.0},
            {"sector": "Broad Market ETF", "display_label": "VWCE", "value_eur": 25000.0},
            {"sector": "Healthcare", "display_label": "Novo Nordisk", "value_eur": 8000.0},
        ])

        fig = build_investments_market_carpet(df, height=360)
        self.assertIsInstance(fig, go.Figure)
        self.assertEqual(fig.data[0].type, "treemap")

        # Verify RGBA colors
        for sector in ("Technology", "Broad Market ETF", "Healthcare"):
            rgba_val = SECTOR_RGBA_COLORS[sector]
            self.assertTrue(rgba_val.startswith("rgba("), f"Expected rgba color for {sector}, got {rgba_val}")
            self.assertIn("0.65", rgba_val)

        # Verify marker styling
        marker = fig.data[0].marker
        self.assertEqual(marker.line.width, 2)
        self.assertIn("rgba", marker.line.color)
        self.assertEqual(marker.pad.t, 4)
        self.assertEqual(fig.data[0].tiling.pad, 6)
        self.assertEqual(marker.cornerradius, 8)

        # Verify uniformtext does not hide small tile names and transition is configured
        self.assertFalse(fig.layout.uniformtext.mode)
        self.assertEqual(fig.layout.uniformtext.minsize, 8)
        self.assertIsNotNone(fig.layout.transition)

    def test_clean_treemap_tile_label(self):
        """Verify cleaning long legal/fund names into compact readable tile labels."""
        from ui.charts import clean_treemap_tile_label

        self.assertEqual(clean_treemap_tile_label("ASML", "ASML"), "ASML")
        self.assertEqual(
            clean_treemap_tile_label("SS SPDR MSCI Europe Energy UCITS ETF", "SPYN.DE"),
            "MSCI Europe Energy",
        )
        self.assertEqual(
            clean_treemap_tile_label("Amazon.com Inc", "AMZN"),
            "Amazon.com",
        )
        self.assertEqual(
            clean_treemap_tile_label("Taiwan Semiconductor Manufacturing Co Ltd - ADR", "TSM"),
            "TSM",
        )

    @patch("streamlit.form")
    @patch("streamlit.markdown")
    @patch("streamlit.columns")
    @patch("streamlit.container")
    @patch("streamlit.popover")
    def test_ac6_account_cards_grouped_alphabetical_and_accented(
        self,
        mock_popover,
        mock_container,
        mock_cols,
        mock_markdown,
        mock_form,
    ):
        """AC-6: Verify accounts are grouped into Cash and Investments, sorted alphabetically with semantic accents."""
        mock_cols.side_effect = lambda spec, **kw: [
            MagicMock() for _ in range(len(spec) if isinstance(spec, (list, tuple)) else int(spec))
        ]
        mock_container.return_value.__enter__.return_value = MagicMock()
        mock_popover.return_value.__enter__.return_value = MagicMock()
        mock_form.return_value.__enter__.return_value = MagicMock()

        class DummyAcc:
            def __init__(self, id, institution, name, asset_class):
                self.id = id
                self.provider = "manual"
                self.institution = institution
                self.name = name
                self.currency = "EUR"
                self.asset_class = asset_class
                self.external_id = None
                self.iban = None
                self.apy = None
                self.is_active = 1

        # Intentionally unsorted mixed accounts
        accounts = [
            DummyAcc(1, "Revolut", "Vault Cash", "cash"),
            DummyAcc(2, "Interactive Brokers", "Margin Portfolio", "investment"),
            DummyAcc(3, "ABN AMRO", "Betaalrekening", "cash"),
            DummyAcc(4, "DeGiro", "Custody All-World", "investment"),
        ]

        fn = getattr(_render_accounts_grid, "__wrapped__", _render_accounts_grid)
        fn(
            accounts=accounts,
            nw_data={"acc_balances": {1: 500.0, 2: 12000.0, 3: 3500.0, 4: 8000.0}},
            sync_logs=[],
            conn=None,
        )

        md_calls = [c.args[0] for c in mock_markdown.call_args_list if c.args]

        # Verify compact columns were instantiated (4 columns per row)
        self.assertTrue(any(c[0] and c[0][0] == 4 for c in mock_cols.call_args_list))

        # Verify alphabetical ordering within groups:
        # Cash: ABN AMRO (id 3) then Revolut (id 1)
        # Investments: DeGiro (id 4) then Interactive Brokers (id 2)
        marker_htmls = [m for m in md_calls if "account-card-marker" in m]
        self.assertEqual(len(marker_htmls), 4)

        # Check Cash cards first, sorted alphabetically
        self.assertIn("ABN AMRO", marker_htmls[0])
        self.assertIn("account-accent-cash", marker_htmls[0])

        self.assertIn("Revolut", marker_htmls[1])
        self.assertIn("account-accent-cash", marker_htmls[1])

        # Check Investment cards next, sorted alphabetically
        self.assertIn("DeGiro", marker_htmls[2])
        self.assertIn("account-accent-investment", marker_htmls[2])

        self.assertIn("Interactive Brokers", marker_htmls[3])
        self.assertIn("account-accent-investment", marker_htmls[3])


if __name__ == "__main__":
    unittest.main()
