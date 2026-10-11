from datetime import date, timedelta
import sqlite3
import unittest
from unittest.mock import MagicMock, patch

from ui.pages.dashboard import (
    _calculate_accrued_subtexts,
    _calculate_monthly_cash_flow,
    _render_accounts_grid,
    _render_analytics_section,
    _render_kpi_ribbon,
    _render_market_news_fragment,
    _render_ticker_fragment,
    render,
)


class TestDashboardPage(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("""
            CREATE TABLE transactions (
                id INTEGER PRIMARY KEY,
                account_id INTEGER,
                booking_date TEXT,
                amount_eur_minor INTEGER,
                is_internal_transfer INTEGER DEFAULT 0
            )
        """)

    def tearDown(self):
        self.conn.close()

    def test_fragments_decorated(self):
        """AC-2, AC-3: Verify modular functions are decorated as Streamlit fragments."""
        for fn in (
            _render_ticker_fragment,
            _render_accounts_grid,
            _render_analytics_section,
            _render_market_news_fragment,
        ):
            self.assertTrue(
                hasattr(fn, "__wrapped__"),
                f"Function {fn.__name__} should be wrapped by @st.fragment",
            )

    def test_calculate_monthly_cash_flow_normal(self):
        """AC-1: Calculates net 30-day cash flow in euros."""
        today = date.today().isoformat()
        ten_days_ago = (date.today() - timedelta(days=10)).isoformat()
        forty_days_ago = (date.today() - timedelta(days=40)).isoformat()

        self.conn.executemany(
            """
            INSERT INTO transactions (account_id, booking_date, amount_eur_minor, is_internal_transfer)
            VALUES (?, ?, ?, ?)
            """,
            [
                (1, today, 300000, 0),         # +€3,000 income
                (1, ten_days_ago, -120000, 0),  # -€1,200 expense
                (1, today, 50000, 1),          # +€500 internal transfer (ignored)
                (1, forty_days_ago, 200000, 0), # +€2,000 old income (ignored)
            ],
        )

        flow = _calculate_monthly_cash_flow(self.conn, days=30)
        self.assertAlmostEqual(flow, 1800.0, places=2)

    def test_calculate_monthly_cash_flow_empty(self):
        """AC-6: Returns 0.0 when no transactions exist without raising exception."""
        flow = _calculate_monthly_cash_flow(self.conn, days=30)
        self.assertEqual(flow, 0.0)

    def test_calculate_accrued_subtexts(self):
        """AC-5: Computes accrued interest subtext accurately."""
        class DummyAccount:
            def __init__(self, id, apy):
                self.id = id
                self.apy = apy

        accounts = [
            DummyAccount(1, 3.5),
            DummyAccount(2, None),
        ]
        today = date(2026, 10, 15)
        latest_snapshots = {
            1: {
                "balance_eur_minor": 1000000,  # €10,000
                "snapshot_date": "2026-10-05",  # 10 days prior
            },
            2: {
                "balance_eur_minor": 500000,
                "snapshot_date": "2026-10-05",
            },
        }

        subtexts = _calculate_accrued_subtexts(accounts, latest_snapshots, today)
        self.assertIn("1", str(subtexts))
        self.assertIn("+€", subtexts[1])
        self.assertIn("3.5% APY", subtexts[1])
        self.assertEqual(subtexts[2], "")

    @patch("ui.pages.dashboard.kpi_card")
    @patch("streamlit.columns")
    def test_kpi_ribbon_renders_four_cards(self, mock_columns, mock_kpi_card):
        """AC-1: KPI ribbon renders Net Worth, Liquid Cash, Investments, and Cash Flow."""
        mock_columns.return_value = [MagicMock(), MagicMock(), MagicMock(), MagicMock()]
        nw_data = {
            "net_worth": 75000.0,
            "liquid_cash": 25000.0,
            "invested": 50000.0,
            "home_equity": 0.0,
        }

        _render_kpi_ribbon(self.conn, nw_data, liabilities=[])

        self.assertEqual(mock_kpi_card.call_count, 4)
        card_titles = [call.args[0] for call in mock_kpi_card.call_args_list]
        self.assertIn("Net Worth", card_titles)
        self.assertIn("Liquid Cash", card_titles)
        self.assertIn("Investments", card_titles)
        self.assertIn("Monthly Cash Flow", card_titles)

    @patch("ui.pages.dashboard.kpi_card")
    @patch("streamlit.columns")
    @patch("streamlit.session_state", {"hide_amounts": True})
    def test_kpi_ribbon_privacy_mode(self, mock_columns, mock_kpi_card):
        """AC-1: Sensitive amounts are masked when is_hidden() is active."""
        mock_columns.return_value = [MagicMock(), MagicMock(), MagicMock(), MagicMock()]
        nw_data = {
            "net_worth": 12345.67,
            "liquid_cash": 2345.67,
            "invested": 10000.0,
            "home_equity": 0.0,
        }

        _render_kpi_ribbon(self.conn, nw_data, liabilities=[])

        card_values = [call.args[1] for call in mock_kpi_card.call_args_list]
        for val in card_values:
            self.assertEqual(val, "€****")

    @patch("ui.pages.dashboard.AccountRepository.get_all_latest_snapshots")
    @patch("streamlit.columns")
    @patch("streamlit.container")
    @patch("streamlit.popover")
    @patch("streamlit.form")
    @patch("streamlit.number_input")
    @patch("streamlit.form_submit_button")
    def test_accounts_grid_keys_namespaced(
        self,
        mock_submit,
        mock_num_in,
        mock_form,
        mock_popover,
        mock_container,
        mock_cols,
        mock_snapshots,
    ):
        """AC-4: All account widgets use deterministic keys formatted as dashboard_acc_{id}_*."""
        mock_snapshots.return_value = {}
        mock_cols.side_effect = lambda spec, **kw: [
            MagicMock() for _ in range(len(spec) if isinstance(spec, (list, tuple)) else int(spec))
        ]
        mock_container.return_value.__enter__.return_value = MagicMock()
        mock_popover.return_value.__enter__.return_value = MagicMock()
        mock_form.return_value.__enter__.return_value = MagicMock()
        mock_submit.return_value = False

        class DummyAcc:
            id = 42
            provider = "manual"
            institution = "Revolut"
            name = "Revolut Vault"
            currency = "EUR"
            asset_class = "cash"
            external_id = None
            iban = None
            apy = 2.5
            is_active = 1

        nw_data = {"acc_balances": {42: 1500.0}}

        fn = getattr(_render_accounts_grid, "__wrapped__", _render_accounts_grid)
        fn(
            accounts=[DummyAcc()],
            nw_data=nw_data,
            sync_logs=[],
            conn=self.conn,
        )

        popover_key = mock_popover.call_args.kwargs.get("key")
        self.assertEqual(popover_key, "dashboard_acc_42_popover")

        form_key = mock_form.call_args.args[0]
        self.assertEqual(form_key, "dashboard_acc_42_adjust_form")

        num_in_key = mock_num_in.call_args.kwargs.get("key")
        self.assertEqual(num_in_key, "dashboard_acc_42_bal_in")

        submit_key = mock_submit.call_args.kwargs.get("key")
        self.assertEqual(submit_key, "dashboard_acc_42_submit_btn")

    @patch("ui.pages.dashboard.AccountRepository.get_all_latest_snapshots")
    @patch("streamlit.markdown")
    @patch("streamlit.columns")
    @patch("streamlit.container")
    @patch("streamlit.popover")
    def test_account_card_markdown_no_code_block_breakout(
        self,
        mock_popover,
        mock_container,
        mock_cols,
        mock_markdown,
        mock_snapshots,
    ):
        """Verify account card markdown does not contain multi-line indentation that causes code block breakouts."""
        mock_snapshots.return_value = {}
        mock_cols.side_effect = lambda spec, **kw: [
            MagicMock() for _ in range(len(spec) if isinstance(spec, (list, tuple)) else int(spec))
        ]
        mock_container.return_value.__enter__.return_value = MagicMock()
        mock_popover.return_value.__enter__.return_value = MagicMock()

        class DummyAcc:
            id = 99
            provider = "enable_banking"
            institution = "ABN AMRO"
            name = "Checking"
            currency = "EUR"
            asset_class = "cash"
            external_id = None
            iban = None
            apy = None
            is_active = 1

        fn = getattr(_render_accounts_grid, "__wrapped__", _render_accounts_grid)
        fn(
            accounts=[DummyAcc()],
            nw_data={"acc_balances": {99: 678.0}},
            sync_logs=[],
            conn=self.conn,
        )

        md_calls = [c.args[0] for c in mock_markdown.call_args_list if c.args]
        for md_str in md_calls:
            for line in md_str.split("\n"):
                self.assertFalse(line.startswith("    "), f"Line has 4+ space indentation: {line}")

    @patch("ui.pages.dashboard.empty_state")
    @patch("ui.pages.dashboard.AccountRepository.get_active_accounts")
    def test_empty_state_zero_accounts(self, mock_get_accounts, mock_empty_state):
        """AC-6: Guided empty state renders cleanly when zero accounts exist."""
        mock_get_accounts.return_value = []

        render()

        mock_empty_state.assert_called_once()
        title, msg = mock_empty_state.call_args.args
        self.assertEqual(title, "No Accounts Found")
        self.assertIn("Import", msg)

    @patch("ui.pages.dashboard.empty_state")
    @patch("ui.pages.dashboard.TransactionRepository.get_recent_spending_df")
    def test_empty_state_zero_transactions(
        self,
        mock_get_spend_df,
        mock_empty_state,
    ):
        """AC-6: Guided empty state renders cleanly when zero spending transactions exist."""
        import pandas as pd

        mock_get_spend_df.return_value = pd.DataFrame()

        fn = getattr(_render_analytics_section, "__wrapped__", _render_analytics_section)
        fn(conn=self.conn)

        empty_titles = [call.args[0] for call in mock_empty_state.call_args_list]
        self.assertIn("No Recent Spending", empty_titles)


    def test_get_latest_salary_date(self):
        """Verify get_latest_salary_date retrieves the most recent salary date on or before date."""
        from db.repositories import TransactionRepository

        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL
            )
        """)
        self.conn.execute("INSERT INTO categories VALUES (1, 'Salary')")
        self.conn.execute("ALTER TABLE transactions ADD COLUMN category_id INTEGER")
        self.conn.execute("ALTER TABLE transactions ADD COLUMN description_raw TEXT")
        self.conn.execute("""
            INSERT INTO transactions (account_id, booking_date, amount_eur_minor, is_internal_transfer, category_id, description_raw)
            VALUES (1, '2026-09-24', 450000, 0, 1, 'Salary payout')
        """)

        # Should find 2026-09-24
        s_date = TransactionRepository.get_latest_salary_date(self.conn, "2026-10-10")
        self.assertEqual(s_date, "2026-09-24")

    @patch("ui.pages.dashboard.render_chart")
    @patch("ui.pages.dashboard.render_cash_flow_sankey")
    @patch("ui.pages.dashboard.get_consolidated_holdings_df")
    @patch("ui.pages.dashboard.TransactionRepository.get_recent_spending_df")
    @patch("streamlit.columns")
    def test_render_analytics_section_dual_columns(
        self,
        mock_cols,
        mock_spend_df,
        mock_holdings_df,
        mock_render_sankey,
        mock_render_chart,
    ):
        """Verify analytics section renders Expenses Sankey and Investments Market Carpet side-by-side."""
        import pandas as pd

        mock_cols.side_effect = lambda spec, **kw: [
            MagicMock() for _ in range(len(spec) if isinstance(spec, (list, tuple)) else int(spec))
        ]
        mock_spend_df.return_value = pd.DataFrame([{"category": "Groceries", "amount_eur": 50.0}])
        mock_holdings_df.return_value = pd.DataFrame([
            {"sector": "Technology", "display_label": "ASML", "value_eur": 1000.0}
        ])

        fn = getattr(_render_analytics_section, "__wrapped__", _render_analytics_section)
        fn(conn=self.conn)

        mock_render_sankey.assert_called_once()
        mock_render_chart.assert_called_once()


if __name__ == "__main__":
    unittest.main()
