"""Tests for Slice 18 Live Portfolio View (Spec 0021).

Covers AC-1 through AC-20:
- Live quotes service (market hours, cached quotes, timeout resilience).
- Consolidated live rows computation (day P&L, day change %, weights, sparkline).
- Portfolio snapshots table and rollover idempotency.
- Copilot open_view view validation (sort, movers, search).
- Copilot analyze_investments day_pnl and movers payload.
"""

from datetime import datetime
import sqlite3
import tempfile
import unittest
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo
import pandas as pd

from agent.tools.investments import tool_analyze_investments
from agent.tools.navigation import _clean_view
from db.database import connect, migrate, upsert_account
from db.repositories.holding_repository import HoldingRepository
from services.live_quotes import cached_quotes, market_clock, market_session_state, refresh_live_quotes
from services.portfolio import build_live_rows, record_daily_portfolio_snapshot


class TestLiveQuotes(unittest.TestCase):
    def test_market_session_state(self):
        tz = ZoneInfo("Europe/Amsterdam")

        # Monday 14:00 Amsterdam -> open
        mon_open = datetime(2026, 10, 12, 14, 0, 0, tzinfo=tz)
        self.assertEqual(market_session_state(mon_open), "open")

        # Monday 08:30 Amsterdam -> closed
        mon_early = datetime(2026, 10, 12, 8, 30, 0, tzinfo=tz)
        self.assertEqual(market_session_state(mon_early), "closed")

        # Monday 22:30 Amsterdam -> closed
        mon_late = datetime(2026, 10, 12, 22, 30, 0, tzinfo=tz)
        self.assertEqual(market_session_state(mon_late), "closed")

        # Saturday 14:00 Amsterdam -> closed
        sat = datetime(2026, 10, 17, 14, 0, 0, tzinfo=tz)
        self.assertEqual(market_session_state(sat), "closed")

        # Sunday 14:00 Amsterdam -> closed
        sun = datetime(2026, 10, 18, 14, 0, 0, tzinfo=tz)
        self.assertEqual(market_session_state(sun), "closed")

    def test_market_clock(self):
        tz = ZoneInfo("Europe/Amsterdam")
        t = datetime(2026, 10, 14, 15, 30, 0, tzinfo=tz)
        clock = market_clock(t)
        self.assertIn("session_state", clock)
        self.assertEqual(clock["current_time_amsterdam"], "15:30:00")
        self.assertEqual(clock["open_time"], "09:00")
        self.assertEqual(clock["close_time"], "22:00")

    def test_cached_quotes_accessor(self):
        temp_dir = tempfile.TemporaryDirectory()
        db_path = f"{temp_dir.name}/test_q.db"
        migrate(db_path)
        conn = connect(db_path)
        with conn:
            conn.execute(
                "INSERT INTO market_quotes (ticker, quote_date, close, prev_close, currency, fetched_at) "
                "VALUES ('AAPL', '2026-10-14', 220.0, 215.0, 'USD', '2026-10-14T10:00:00')"
            )
        res = cached_quotes(conn)
        conn.close()
        temp_dir.cleanup()

        self.assertIn("quotes", res)
        self.assertIn("AAPL", res["quotes"])
        self.assertEqual(res["quotes"]["AAPL"]["price"], 220.0)


class TestBuildLiveRows(unittest.TestCase):
    def test_build_live_rows_calculations(self):
        # Consolidated holdings matching get_consolidated_holdings_df output:
        # direct AAPL + copy constituent AAPL + copy constituent MSFT
        consolidated = pd.DataFrame([
            {
                "ticker": "AAPL",
                "name": "Apple Inc",
                "asset_type": "stock",
                "quantity": 10.0,
                "cost_basis_minor": 150000,
                "cost_basis": 1500.0,
                "value_eur": 1800.0,
                "currency": "EUR",
                "is_copy": False,
                "copies_str": "-",
            },
            {
                "ticker": "AAPL",
                "name": "Apple Inc",
                "asset_type": "stock",
                "quantity": 0.0,
                "cost_basis_minor": 40000,
                "cost_basis": 400.0,
                "value_eur": 400.0,
                "currency": "EUR",
                "is_copy": True,
                "copies_str": "Jeppe Kirk",
            },
            {
                "ticker": "MSFT",
                "name": "Microsoft Corp",
                "asset_type": "stock",
                "quantity": 0.0,
                "cost_basis_minor": 60000,
                "cost_basis": 600.0,
                "value_eur": 600.0,
                "currency": "USD",
                "is_copy": True,
                "copies_str": "Jeppe Kirk",
            },
        ])

        aggregated = pd.DataFrame([
            {
                "ticker": "AAPL",
                "name": "Apple Inc",
                "asset_type": "stock",
                "quantity": 10.0,
                "cost_basis_minor": 150000,
                "cost_basis": 1500.0,
                "currency": "EUR",
            }
        ])

        mirror_cache = [
            {
                "trader_name": "Jeppe Kirk",
                "positions": [
                    {"symbol": "MSFT", "amount_usd": 600.0, "pnl_usd": 60.0, "current_rate": 400.0, "open_rate": 360.0},
                    {"symbol": "AAPL", "amount_usd": 400.0, "pnl_usd": 40.0, "current_rate": 180.0, "open_rate": 162.0},
                ],
            }
        ]

        quote_cache = {
            "quotes": {
                "AAPL": {
                    "price": 180.0,
                    "prev_close": 175.0,
                    "day_change_pct": 2.857,
                    "currency": "EUR",
                    "is_live": True,
                },
                "MSFT": {
                    "price": 400.0,
                    "prev_close": 410.0,
                    "day_change_pct": -2.439,
                    "currency": "USD",
                    "is_live": True,
                },
            }
        }

        close_series = {
            "AAPL": [170.0, 172.0, 175.0, 180.0],
            "MSFT": [420.0, 415.0, 410.0, 400.0],
        }

        live_df = build_live_rows(
            consolidated,
            aggregated,
            mirror_cache=mirror_cache,
            quote_cache=quote_cache,
            fx_rate=1.0,
            close_series=close_series,
        )
        self.assertFalse(live_df.empty)

        # AAPL appears: direct (10 * 180 = 1800) + mirror (400 / 162 * 180 = 444.44) = 2244.44 value
        aapl_row = live_df[live_df["ticker"] == "AAPL"].iloc[0]
        self.assertEqual(aapl_row["name"], "Apple Inc")
        self.assertTrue(aapl_row["is_copy"])
        self.assertAlmostEqual(aapl_row["day_change_pct"], 2.857, places=2)
        self.assertGreater(aapl_row["day_pnl_eur"], 0)
        self.assertEqual(len(aapl_row["sparkline"]), 4)

        # MSFT appears from copy portfolio: 600 / 360 * 400 = 666.67
        msft_row = live_df[live_df["ticker"] == "MSFT"].iloc[0]
        self.assertAlmostEqual(msft_row["value_eur"], 666.67, places=1)
        self.assertAlmostEqual(msft_row["day_change_pct"], -2.439, places=2)
        self.assertLess(msft_row["day_pnl_eur"], 0)

        # Total allocation sums to ~100%
        self.assertAlmostEqual(live_df["weight_pct"].sum(), 100.0, delta=0.5)

    def test_build_live_rows_copy_portfolio_valuation(self):
        holdings = pd.DataFrame([
            {
                "ticker": "COPY:Michalhla",
                "name": "Michal Hlouschka",
                "asset_type": "copy_trader",
                "quantity": 1.0,
                "cost_basis": 8000.0,
                "value_eur": 8800.0,
                "currency": "USD",
            }
        ])
        agg_holdings = holdings.copy()
        mirror_cache = [
            {
                "username": "Michalhla",
                "ticker": "COPY:Michalhla",
                "invested_usd": 9000.0,
                "value_usd": 10000.0,
                "unrealized_pnl_usd": 1000.0,
                "return_pct": 11.11,
            }
        ]
        df = build_live_rows(
            holdings,
            agg_holdings,
            mirror_cache=mirror_cache,
            fx_rate=0.9,
        )
        self.assertEqual(len(df), 1)
        row = df.iloc[0]
        self.assertEqual(row["ticker"], "COPY:Michalhla")
        self.assertTrue(row["is_copy"])
        self.assertTrue(row["is_priced"])
        self.assertEqual(row["quote_age_str"], "Mirror NAV")
        self.assertAlmostEqual(row["cost_basis"], 8100.0)  # 9000 * 0.9
        self.assertAlmostEqual(row["value_eur"], 9000.0)    # 10000 * 0.9

    def test_build_live_rows_pence_quote_normalization(self):
        holdings = pd.DataFrame([
            {
                "ticker": "IWG.L",
                "name": "IWG PLC",
                "asset_type": "stock",
                "quantity": 10.0,
                "cost_basis": 20.0,
                "currency": "GBP",
            }
        ])
        quote_cache = {
            "quotes": {
                "IWG.L": {
                    "price": 184.5,  # 184.5 pence (GBp)
                    "prev_close": 180.0,
                    "currency": "GBP",
                }
            }
        }
        df = build_live_rows(
            holdings,
            holdings,
            quote_cache=quote_cache,
            fx_rate=0.9,
        )
        row = df.iloc[0]
        # 184.5 pence divided by 100 = 1.845 GBP * 1.16 EUR/GBP ~ 2.14 EUR per share -> total value ~ 21.4 EUR (NOT 2140 EUR)
        self.assertAlmostEqual(row["price"], 1.845, places=3)
        self.assertLess(row["value_eur"], 50.0)


class TestPortfolioSnapshots(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = f"{self.temp_dir.name}/test_snapshots.db"
        migrate(self.db_path)
        self.conn = connect(self.db_path)

    def tearDown(self):
        self.conn.close()
        self.temp_dir.cleanup()

    def test_upsert_portfolio_snapshot_idempotency(self):
        today = "2026-10-14"
        # First write
        HoldingRepository.upsert_portfolio_snapshot(self.conn, today, 1000000, 800000, 20000)
        snaps = HoldingRepository.get_portfolio_snapshots(self.conn)
        self.assertEqual(len(snaps), 1)
        self.assertEqual(snaps[0]["market_value_eur_minor"], 1000000)

        # Second write on same day: updates row without error or duplicates
        HoldingRepository.upsert_portfolio_snapshot(self.conn, today, 1050000, 800000, 70000)
        snaps = HoldingRepository.get_portfolio_snapshots(self.conn)
        self.assertEqual(len(snaps), 1)
        self.assertEqual(snaps[0]["market_value_eur_minor"], 1050000)
        self.assertEqual(snaps[0]["day_pnl_eur_minor"], 70000)

    def test_record_daily_portfolio_snapshot(self):
        acc_id = upsert_account(self.conn, {
            "provider": "etoro",
            "institution": "eToro",
            "external_id": "acc-1",
            "name": "Main",
            "currency": "EUR",
        })
        HoldingRepository.upsert_holdings(self.conn, [
            {
                "account_id": acc_id,
                "ticker": "VWCE.DE",
                "name": "Vanguard All-World",
                "asset_type": "etf",
                "quantity": 10.0,
                "cost_basis_minor": 100000,
                "currency": "EUR",
            }
        ])

        today = "2026-10-14"
        record_daily_portfolio_snapshot(self.conn, today)
        snaps = HoldingRepository.get_portfolio_snapshots(self.conn)
        self.assertEqual(len(snaps), 1)
        self.assertEqual(snaps[0]["snapshot_date"], today)
        self.assertEqual(snaps[0]["cost_basis_eur_minor"], 100000)


class TestNavigationSortMovers(unittest.TestCase):
    def test_clean_view_investments_allowed_keys(self):
        raw = {
            "sort": "day_pnl_eur",
            "movers": "gainers",
            "search": "AAPL",
            "exposure_dimension": "Sector",
            "focus": "Technology",
        }
        cleaned, note = _clean_view("investments", raw)
        self.assertEqual(cleaned["sort"], "day_pnl_eur")
        self.assertEqual(cleaned["movers"], "gainers")
        self.assertEqual(cleaned["search"], "AAPL")
        self.assertEqual(cleaned["exposure_dimension"], "Sector")
        self.assertEqual(cleaned["focus"], "Technology")
        self.assertEqual(note, [])

    def test_clean_view_investments_invalid_sort_rejected(self):
        raw = {"sort": "unknown_col"}
        cleaned, note = _clean_view("investments", raw)
        self.assertNotIn("sort", cleaned)
        self.assertTrue(any("Ignored sort column" in n for n in note))

    def test_clean_view_investments_invalid_movers_rejected(self):
        raw = {"movers": "sideways"}
        cleaned, note = _clean_view("investments", raw)
        self.assertNotIn("movers", cleaned)
        self.assertTrue(any("Ignored movers option" in n for n in note))


class TestCopilotLiveInvestments(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = f"{self.temp_dir.name}/test_copilot_inv.db"
        migrate(self.db_path)
        self.conn = connect(self.db_path)
        self.acc_id = upsert_account(self.conn, {
            "provider": "etoro",
            "institution": "eToro",
            "external_id": "acc-1",
            "name": "Main",
            "currency": "EUR",
        })
        HoldingRepository.upsert_holdings(self.conn, [
            {
                "account_id": self.acc_id,
                "ticker": "AAPL",
                "name": "Apple Inc",
                "asset_type": "stock",
                "quantity": 10.0,
                "cost_basis_minor": 150000,
                "currency": "EUR",
            }
        ])

    def tearDown(self):
        self.conn.close()
        self.temp_dir.cleanup()

    def test_analyze_investments_returns_day_pnl_and_movers(self):
        mock_quotes = {
            "quotes": {
                "AAPL": {"price": 200.0, "day_change_pct": 5.0, "day_pnl_eur": 100.0, "is_live": True},
            }
        }
        with patch("agent.tools.investments.DB_PATH", self.db_path):
            with patch("agent.tools.investments.cached_quotes", return_value=mock_quotes):
                res = tool_analyze_investments()
                self.assertIn("day_pnl_eur", res)
                self.assertIn("movers", res)
                self.assertIn("gainers", res["movers"])
                self.assertIn("losers", res["movers"])


if __name__ == "__main__":
    unittest.main()
