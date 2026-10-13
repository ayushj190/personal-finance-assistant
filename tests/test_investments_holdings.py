import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch
import pandas as pd

from db.database import connect, migrate, upsert_account
from db.models import Holding
from db.repositories import HoldingRepository


class TestInvestmentsHoldings(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_investments.db")
        migrate(self.db_path)
        self.conn = connect(self.db_path)

        self.acc_id = upsert_account(
            self.conn,
            {
                "provider": "etoro",
                "institution": "eToro",
                "name": "eToro Main",
                "currency": "EUR",
                "asset_class": "investment",
                "external_id": "etoro_inv_test",
            },
        )

    def tearDown(self):
        self.conn.close()
        self.temp_dir.cleanup()

    def test_holdings_lifecycle_and_v_holdings_filtering(self):
        """AC-5: v_holdings filters active positions where quantity > 0 and status = 'active'."""
        h_active = {
            "account_id": self.acc_id,
            "ticker": "VWCE.DE",
            "name": "Vanguard All-World",
            "asset_type": "etf",
            "quantity": 10.0,
            "cost_basis_minor": 100000,
            "currency": "EUR",
            "status": "active",
            "closed_at": None,
            "updated_at": "2026-10-11T10:00:00",
        }
        h_closed = {
            "account_id": self.acc_id,
            "ticker": "AAPL",
            "name": "Apple Inc",
            "asset_type": "stock",
            "quantity": 0.0,
            "cost_basis_minor": 0,
            "currency": "USD",
            "status": "closed",
            "closed_at": "2026-10-10T12:00:00",
            "updated_at": "2026-10-10T12:00:00",
        }
        HoldingRepository.upsert_holdings(self.conn, [h_active, h_closed])

        # Active holdings view should only contain VWCE.DE
        df_active = HoldingRepository.get_v_holdings_df(self.conn)
        self.assertEqual(len(df_active), 1)
        self.assertEqual(df_active.iloc[0]["ticker"], "VWCE.DE")
        self.assertEqual(df_active.iloc[0]["status"], "active")

        # Include closed holdings should contain both
        df_all = HoldingRepository.get_v_holdings_df(self.conn, include_closed=True)
        self.assertEqual(len(df_all), 2)
        tickers = set(df_all["ticker"])
        self.assertIn("VWCE.DE", tickers)
        self.assertIn("AAPL", tickers)

    def test_atomic_statement_reconciliation(self):
        """AC-5, AC-6: Reconcile statement upserts incoming holdings and closes missing positions."""
        # Initial state: 3 active positions
        initial_holdings = [
            {
                "account_id": self.acc_id,
                "ticker": "ASML.AS",
                "name": "ASML Holding",
                "asset_type": "stock",
                "quantity": 5.0,
                "cost_basis_minor": 350000,
                "currency": "EUR",
            },
            {
                "account_id": self.acc_id,
                "ticker": "NVDA",
                "name": "Nvidia",
                "asset_type": "stock",
                "quantity": 10.0,
                "cost_basis_minor": 120000,
                "currency": "USD",
            },
            {
                "account_id": self.acc_id,
                "ticker": "MSFT",
                "name": "Microsoft",
                "asset_type": "stock",
                "quantity": 4.0,
                "cost_basis_minor": 160000,
                "currency": "USD",
            },
        ]
        HoldingRepository.upsert_holdings(self.conn, initial_holdings)
        self.assertEqual(len(HoldingRepository.get_v_holdings_df(self.conn)), 3)

        # New statement import: NVDA updated, GOOGL added, ASML and MSFT omitted (sold)
        new_statement = [
            {
                "account_id": self.acc_id,
                "ticker": "NVDA",
                "name": "Nvidia Corp",
                "asset_type": "stock",
                "quantity": 15.0,
                "cost_basis_minor": 180000,
                "currency": "USD",
            },
            {
                "account_id": self.acc_id,
                "ticker": "GOOGL",
                "name": "Alphabet Inc",
                "asset_type": "stock",
                "quantity": 8.0,
                "cost_basis_minor": 140000,
                "currency": "USD",
            },
        ]

        result = HoldingRepository.reconcile_account_holdings(
            self.conn, self.acc_id, new_statement
        )
        self.assertEqual(result["upserted"], 2)
        self.assertEqual(result["closed"], 2)  # ASML and MSFT marked closed
        self.assertEqual(result["active_total"], 2)

        # Active holdings check
        df_reconciled = HoldingRepository.get_v_holdings_df(self.conn)
        self.assertEqual(len(df_reconciled), 2)
        active_tickers = set(df_reconciled["ticker"])
        self.assertEqual(active_tickers, {"NVDA", "GOOGL"})

        # Check closed records in DB
        cur = self.conn.execute(
            "SELECT ticker, quantity, status, closed_at FROM holdings WHERE account_id = ? AND status = 'closed'",
            (self.acc_id,),
        )
        closed_rows = cur.fetchall()
        self.assertEqual(len(closed_rows), 2)
        for r in closed_rows:
            self.assertEqual(r["quantity"], 0.0)
            self.assertEqual(r["status"], "closed")
            self.assertIsNotNone(r["closed_at"])

        # Test reopening previously closed position
        reopen_statement = [
            {
                "account_id": self.acc_id,
                "ticker": "ASML.AS",
                "name": "ASML Holding",
                "asset_type": "stock",
                "quantity": 2.0,
                "cost_basis_minor": 140000,
                "currency": "EUR",
            }
        ]
        reopen_res = HoldingRepository.reconcile_account_holdings(
            self.conn, self.acc_id, reopen_statement
        )
        self.assertEqual(reopen_res["upserted"], 1)
        self.assertEqual(reopen_res["active_total"], 1)
        asml_row = self.conn.execute(
            "SELECT quantity, status, closed_at FROM holdings WHERE account_id = ? AND ticker = 'ASML.AS'",
            (self.acc_id,),
        ).fetchone()
        self.assertEqual(asml_row["quantity"], 2.0)
        self.assertEqual(asml_row["status"], "active")
        self.assertIsNone(asml_row["closed_at"])

    def test_missing_quote_cost_basis_fallback(self):
        """AC-7: Holdings with missing market quotes fall back safely to cost basis valuation."""
        holding = {
            "account_id": self.acc_id,
            "ticker": "PRIVATE_FUND",
            "name": "Private Real Estate Fund",
            "asset_type": "other",
            "quantity": 100.0,
            "cost_basis_minor": 500000,  # €5,000.00
            "currency": "EUR",
            "status": "active",
            "updated_at": "2026-10-11T12:00:00",
        }
        HoldingRepository.upsert_holdings(self.conn, [holding])

        # No quotes exist in market_quotes for PRIVATE_FUND
        df = HoldingRepository.get_v_holdings_df(self.conn)
        self.assertEqual(len(df), 1)
        row = df.iloc[0]
        self.assertEqual(row["ticker"], "PRIVATE_FUND")
        self.assertEqual(row["latest_close"], 0.0)
        # Value must equal cost_basis (€5,000.00) instead of crashing to 0.0
        self.assertAlmostEqual(row["value_eur"], 5000.0, places=2)
        self.assertAlmostEqual(row["unrealized_pnl_eur"], 0.0, places=2)

        # Check get_portfolio_kpis
        kpis = HoldingRepository.get_portfolio_kpis(self.conn)
        self.assertAlmostEqual(kpis["total_value"], 5000.0, places=2)
        self.assertAlmostEqual(kpis["total_cost"], 5000.0, places=2)
        self.assertEqual(kpis["unquoted_count"], 1)

    def test_copy_portfolio_labeling_and_privacy_masking(self):
        """AC-2: Format copy portfolios vs direct holdings and privacy masking."""
        from ui.components import format_money

        # Test copy portfolio labeling
        direct_ticker = "VWCE.DE"
        copy_ticker = "COPY:OlivierDanvel"

        label_direct = "Direct Holding" if not direct_ticker.startswith("COPY:") else f"Copy: {direct_ticker}"
        label_copy = (
            f"Copy: {copy_ticker.replace('COPY:', '')}"
            if copy_ticker.startswith("COPY:")
            else "Direct Holding"
        )
        self.assertEqual(label_direct, "Direct Holding")
        self.assertEqual(label_copy, "Copy: OlivierDanvel")

        # Privacy mode masking
        with patch("ui.components.is_hidden", return_value=True):
            masked_val = format_money(12345.67)
            self.assertEqual(masked_val, "€****")

        with patch("ui.components.is_hidden", return_value=False):
            unmasked_val = format_money(12345.67)
            self.assertEqual(unmasked_val, "€12,345.67")

    @patch("ui.pages.investments.update_quotes")
    @patch("streamlit.tabs")
    def test_investments_render_smoke(self, mock_tabs, mock_update_quotes):
        """AC-1: Investments page renders 4 top level tabs without exceptions."""
        from ui.pages import investments

        mock_tab_objects = [MagicMock(), MagicMock(), MagicMock(), MagicMock()]
        mock_tabs.return_value = mock_tab_objects

        # Insert a holding to exercise render flow
        holding = {
            "account_id": self.acc_id,
            "ticker": "IWDA.AS",
            "name": "iShares Core MSCI World",
            "asset_type": "etf",
            "quantity": 25.0,
            "cost_basis_minor": 200000,
            "currency": "EUR",
            "status": "active",
            "updated_at": "2026-10-11T12:00:00",
        }
        HoldingRepository.upsert_holdings(self.conn, [holding])

        with patch("ui.pages.investments.DB_PATH", self.db_path):
            # Render should execute cleanly and call st.tabs with 4 tab labels
            investments.render()
            mock_tabs.assert_called_once()
            tab_labels = mock_tabs.call_args[0][0]
            self.assertEqual(len(tab_labels), 4)
            self.assertIn("📊 Portfolio & Holdings", tab_labels[0])
            self.assertIn("⚖️ Allocation & Drift", tab_labels[1])
            self.assertIn("💰 Income & Tax Strategy", tab_labels[2])
            self.assertIn("🎯 Goals & Planning", tab_labels[3])


    def test_active_positions_calculation_with_copy_portfolio_distinct_assets(self):
        """Active positions counts distinct assets across copy portfolios and direct holdings."""
        from ui.pages.investments import _render_portfolio_fragment

        h1 = {
            "account_id": self.acc_id,
            "ticker": "VWCE.DE",
            "name": "Vanguard All-World",
            "asset_type": "etf",
            "quantity": 10.0,
            "cost_basis_minor": 100000,
            "currency": "EUR",
        }
        h2 = {
            "account_id": self.acc_id,
            "ticker": "COPY:jeppe",
            "name": "Jeppe Kirk",
            "asset_type": "other",
            "quantity": 1.0,
            "cost_basis_minor": 200000,
            "currency": "USD",
        }
        HoldingRepository.upsert_holdings(self.conn, [h1, h2])
        holdings_df = HoldingRepository.get_v_holdings_df(self.conn)
        copy_df = holdings_df[holdings_df["ticker"].str.startswith("COPY:")].copy()
        direct_df = holdings_df[~holdings_df["ticker"].str.startswith("COPY:")].copy()

        # Mirrors cache has 3 distinct positions for COPY:jeppe: AAPL, MSFT, TSLA
        mirrors_map = {
            "COPY:jeppe": {
                "positions": [
                    {"symbol": "AAPL", "amount_usd": 500, "pnl_usd": 50},
                    {"symbol": "MSFT", "amount_usd": 500, "pnl_usd": 50},
                    {"symbol": "TSLA", "amount_usd": 500, "pnl_usd": 50},
                ]
            }
        }

        distinct_assets = set()
        for _, row in holdings_df.iterrows():
            t = str(row["ticker"])
            if t.startswith("COPY:"):
                m = mirrors_map.get(t, {})
                positions = m.get("positions", [])
                if positions:
                    for p in positions:
                        sym = p.get("symbol")
                        if sym:
                            distinct_assets.add(sym)
                else:
                    distinct_assets.add(t)
            elif t:
                distinct_assets.add(t)

        # 1 direct + 3 copy positions = 4 distinct assets (not 2)
        self.assertEqual(len(distinct_assets), 4)

        fn = getattr(_render_portfolio_fragment, "__wrapped__", _render_portfolio_fragment)
        with patch("ui.pages.investments.kpi_card") as mock_kpi:
            with patch("ui.pages.investments.is_hidden", return_value=False):
                fn(
                    holdings_df, copy_df, direct_df, pd.DataFrame(), 0.89, active_positions_count=len(distinct_assets)
                )
                mock_kpi.assert_any_call("Active Positions", "4 assets", subtext="⏱️ 2 quote delayed")

    def test_investments_privacy_masking_active_positions_and_percentages(self):
        """Counts and percentages stay readable under Hide values; only money masks (AC-8)."""
        from unittest.mock import ANY

        from ui.pages.investments import _render_portfolio_fragment

        h1 = {
            "account_id": self.acc_id,
            "ticker": "VWCE.DE",
            "name": "Vanguard All-World",
            "asset_type": "etf",
            "quantity": 10.0,
            "cost_basis_minor": 100000,
            "currency": "EUR",
        }
        HoldingRepository.upsert_holdings(self.conn, [h1])
        holdings_df = HoldingRepository.get_v_holdings_df(self.conn)
        copy_df = pd.DataFrame()
        direct_df = holdings_df.copy()

        fn = getattr(_render_portfolio_fragment, "__wrapped__", _render_portfolio_fragment)
        with patch("ui.pages.investments.kpi_card") as mock_kpi:
            with patch("ui.pages.investments.is_hidden", return_value=True):
                fn(
                    holdings_df, copy_df, direct_df, pd.DataFrame(), 0.89, active_positions_count=5
                )
                mock_kpi.assert_any_call("Active Positions", "5 assets", subtext=ANY)


if __name__ == "__main__":
    unittest.main()
