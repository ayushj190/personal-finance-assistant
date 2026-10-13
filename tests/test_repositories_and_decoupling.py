import os
import tempfile
import time
import unittest
from unittest.mock import MagicMock, patch

from db.database import connect, migrate
from db.models import Account, Holding, Transaction
from db.repositories import (
    AccountRepository,
    HoldingRepository,
    LiabilityRepository,
    TransactionRepository,
)
from db.migrations.runner import (
    get_available_migrations,
    get_current_version,
    run_migrations,
)
from services.task_coordinator import TaskCoordinator, TaskStatus
from ui.theme import charts, tokens


class TestRepositoriesAndDecoupling(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_repos.db")
        migrate(self.db_path)
        self.conn = connect(self.db_path)

    def tearDown(self):
        self.conn.close()
        self.temp_dir.cleanup()

    def test_account_repository(self):
        # Insert account via repository
        acc = Account(
            id=None,
            provider="manual",
            institution="ABN AMRO",
            name="Main Checking",
            asset_class="cash",
            currency="EUR",
            external_id="abn_main",
            iban="NL91ABNA0417164300",
            apy=1.5,
            is_active=1,
        )
        acc_id = AccountRepository.upsert(self.conn, acc)
        self.assertGreater(acc_id, 0)

        # Retrieve by ID and by provider external ID
        retrieved = AccountRepository.get_by_id(self.conn, acc_id)
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.name, "Main Checking")
        self.assertEqual(retrieved.apy, 1.5)

        by_ext = AccountRepository.get_by_provider_ext_id(self.conn, "manual", "abn_main")
        self.assertIsNotNone(by_ext)
        self.assertEqual(by_ext.id, acc_id)

        # Active accounts
        active = AccountRepository.get_active_accounts(self.conn)
        self.assertTrue(any(a.id == acc_id for a in active))

        # Cash accounts
        cash_accs = AccountRepository.get_cash_accounts(self.conn)
        self.assertTrue(any(a.id == acc_id for a in cash_accs))

        # Update APY
        AccountRepository.update_apy(self.conn, acc_id, 2.25)
        updated = AccountRepository.get_by_id(self.conn, acc_id)
        self.assertEqual(updated.apy, 2.25)

        # Snapshots
        self.conn.execute(
            """
            INSERT INTO account_snapshots (account_id, snapshot_date, balance_minor, balance_eur_minor)
            VALUES (?, '2026-10-10', 250000, 250000)
            """,
            (acc_id,),
        )
        snap = AccountRepository.get_latest_snapshot(self.conn, acc_id)
        self.assertIsNotNone(snap)
        self.assertEqual(snap["balance_minor"], 250000)

        all_snaps = AccountRepository.get_all_latest_snapshots(self.conn)
        self.assertIn(acc_id, all_snaps)

        # Total cash balance & net worth snapshot
        tot_cash = AccountRepository.get_total_cash_balance(self.conn)
        self.assertAlmostEqual(tot_cash, 2500.0)

        nw_snap = AccountRepository.get_latest_net_worth_snapshot(self.conn)
        self.assertAlmostEqual(nw_snap, 2500.0)

    def test_transaction_repository(self):
        acc_id = AccountRepository.upsert(
            self.conn,
            {
                "provider": "manual",
                "institution": "Revolut",
                "name": "Daily Expenses",
                "currency": "EUR",
                "asset_class": "cash",
                "external_id": "rev_daily",
            },
        )
        tx = Transaction(
            id=None,
            account_id=acc_id,
            dedup_hash="hash_supermarket_1",
            booking_date="2026-10-01",
            amount_minor=-4500,
            amount_eur_minor=-4500,
            description_raw="Albert Heijn",
            merchant_normalized="Albert Heijn",
            category_id=41,  # Supermarket
            category_source="rule",
            source="csv",
        )
        inserted = TransactionRepository.upsert_transactions(self.conn, [tx])
        self.assertEqual(inserted, 1)

        recent = TransactionRepository.get_recent(self.conn, limit=10, account_id=acc_id)
        self.assertEqual(len(recent), 1)
        self.assertEqual(recent[0].merchant_normalized, "Albert Heijn")
        self.assertEqual(recent[0].amount, -45.0)

        # Spending dataframe & monthly expenses
        spend_df = TransactionRepository.get_recent_spending_df(self.conn, days=30)
        self.assertFalse(spend_df.empty)

        # Goals
        g_id = TransactionRepository.add_goal(self.conn, "Emergency Fund", 10000.0, acc_id)
        self.assertGreater(g_id, 0)

        goals = TransactionRepository.get_goals(self.conn)
        self.assertTrue(any(g["name"] == "Emergency Fund" for g in goals))

    def test_holding_and_liability_repositories(self):
        acc_id = AccountRepository.upsert(
            self.conn,
            {
                "provider": "etoro",
                "institution": "eToro",
                "name": "Investments",
                "currency": "EUR",
                "asset_class": "investment",
                "external_id": "etoro_inv",
            },
        )
        holding = Holding(
            id=None,
            account_id=acc_id,
            ticker="IWDA.AS",
            name="iShares Core MSCI World",
            asset_type="etf",
            region="Global",
            sector="Diversified",
            quantity=50.0,
            cost_basis_minor=400000,
            currency="EUR",
            updated_at="2026-10-10",
        )
        HoldingRepository.upsert_holdings(self.conn, [holding])

        holdings = HoldingRepository.get_all_holdings(self.conn)
        self.assertEqual(len(holdings), 1)
        self.assertEqual(holdings[0].ticker, "IWDA.AS")

        v_df = HoldingRepository.get_v_holdings_df(self.conn)
        self.assertIn("updated_at", v_df.columns)
        self.assertEqual(v_df.iloc[0]["updated_at"], "2026-10-10")

        # Market quotes & FX quote
        HoldingRepository.upsert_market_quotes(
            self.conn,
            [
                {
                    "ticker": "EURUSD=X",
                    "quote_date": "2026-10-10",
                    "close": 1.085,
                    "prev_close": 1.082,
                    "currency": "USD",
                }
            ],
        )
        fx = HoldingRepository.get_latest_fx_quote(self.conn, "EURUSD=X")
        self.assertEqual(fx, 1.085)

        # Allocation profiles
        profiles = HoldingRepository.get_allocation_profiles(self.conn)
        self.assertGreater(len(profiles), 0)
        targets = HoldingRepository.get_allocation_targets(self.conn, profiles[0]["id"])
        self.assertIsInstance(targets, dict)

        # Liabilities
        self.conn.execute(
            """
            INSERT INTO liabilities (name, lender, loan_type, original_principal_minor, start_date)
            VALUES ('Mortgage Part 1', 'ABN AMRO', 'annuity', 35000000, '2024-01-01')
            """
        )
        liabilities = LiabilityRepository.get_all_liabilities(self.conn)
        self.assertEqual(len(liabilities), 1)
        self.assertEqual(liabilities[0].original_principal, 350000.0)

    def test_migration_runner(self):
        # Verify schema version
        ver = get_current_version(self.conn)
        self.assertGreaterEqual(ver, 1)

        available = get_available_migrations()
        self.assertGreaterEqual(len(available), 1)
        self.assertEqual(available[0][0], 1)

        # Running migrations again is completely idempotent
        executed = run_migrations(self.conn)
        self.assertEqual(executed, [])

    def test_task_coordinator(self):
        coordinator = TaskCoordinator()
        self.assertFalse(coordinator.is_running("test_job"))

        def worker_success():
            time.sleep(0.05)
            return "done"

        started = coordinator.submit("test_job", worker_success)
        self.assertTrue(started)
        self.assertTrue(coordinator.is_running("test_job"))

        # Wait for worker completion
        time.sleep(0.15)
        self.assertFalse(coordinator.is_running("test_job"))
        state = coordinator.get_state("test_job")
        self.assertEqual(state.status, TaskStatus.SUCCESS)
        self.assertEqual(state.result, "done")

        # Worker with exception handling
        def worker_failure():
            raise ValueError("Something went wrong")

        coordinator.submit("failing_job", worker_failure)
        time.sleep(0.1)
        fail_state = coordinator.get_state("failing_job")
        self.assertEqual(fail_state.status, TaskStatus.ERROR)
        self.assertIn("Something went wrong", fail_state.error)

    def test_theme_and_charts_no_monkey_patching(self):
        # Test tokens
        self.assertEqual(tokens.TEAL, "#2DD4BF")
        self.assertIn(tokens.EMERALD, tokens.COLOR_PALETTE)

        # Test plotly registration
        charts.register_plotly_theme()
        import plotly.io as pio
        self.assertIn("pfa_theme", pio.templates)

        # Confirm render_chart calls st.plotly_chart explicitly without monkey patch requirement
        mock_fig = MagicMock()
        mock_fig.layout.paper_bgcolor = None
        mock_fig.layout.plot_bgcolor = None
        mock_fig.layout.template = None

        with patch("streamlit.plotly_chart") as mock_st_chart:
            charts.render_chart(mock_fig, width="stretch")
            mock_st_chart.assert_called_once()
            _, kwargs = mock_st_chart.call_args
            self.assertEqual(kwargs.get("theme"), None)
            self.assertEqual(kwargs.get("width"), "stretch")


if __name__ == "__main__":
    unittest.main()
