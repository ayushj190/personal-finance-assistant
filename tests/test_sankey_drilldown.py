import sqlite3
import unittest
from unittest.mock import patch
import plotly.graph_objects as go
import streamlit as st

from ui.charts import build_cash_flow_sankey, prepare_cash_flow_sankey_data


class TestSankeyDrilldown(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript("""
            CREATE TABLE tax_profile (
                id INTEGER PRIMARY KEY,
                gross_annual_income REAL DEFAULT 80000.0,
                has_partner INTEGER DEFAULT 0
            );
            INSERT INTO tax_profile (id, gross_annual_income) VALUES (1, 80000.0);

            CREATE TABLE categories (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                kind TEXT NOT NULL,
                parent_id INTEGER
            );
            INSERT INTO categories VALUES
                (1, 'Housing', 'fixed', NULL),
                (2, 'Mortgage', 'fixed', 1),
                (3, 'Food & Dining', 'discretionary', NULL),
                (4, 'Groceries', 'discretionary', 3),
                (5, 'Salary', 'income', NULL);

            CREATE TABLE transactions (
                id INTEGER PRIMARY KEY,
                booking_date TEXT,
                amount_eur_minor INTEGER,
                category_id INTEGER,
                is_internal_transfer INTEGER DEFAULT 0
            );
            INSERT INTO transactions VALUES
                (1, date('now', '-5 days'), 500000, 5, 0),    -- +€5,000 salary
                (2, date('now', '-4 days'), -120000, 2, 0),   -- -€1,200 mortgage
                (3, date('now', '-3 days'), -40000, 4, 0);    -- -€400 groceries
        """)

    def tearDown(self):
        self.conn.close()

    def test_prepare_cash_flow_sankey_data(self):
        """Verify income, taxes, fixed and discretionary expenses are prepared correctly."""
        data = prepare_cash_flow_sankey_data(self.conn, days=30)
        self.assertGreater(data["gross_salary"], 0)
        self.assertGreater(data["net_salary"], 0)
        self.assertAlmostEqual(data["fixed_spent"], 1200.0, places=1)
        self.assertAlmostEqual(data["disc_spent"], 400.0, places=1)
        self.assertIn("Housing", data["fixed_cats"])
        self.assertIn("Food & Dining", data["disc_cats"])

    def test_build_full_flow_sankey(self):
        """Verify Full Flow Sankey builds valid traces with ordered coordinate stages."""
        data = prepare_cash_flow_sankey_data(self.conn, days=30)
        fig = build_cash_flow_sankey(data, drilldown_flow="Full Flow")
        self.assertIsInstance(fig, go.Figure)
        self.assertEqual(len(fig.data), 1)

        sankey_trace = fig.data[0]
        # Verify node coordinates exist and have 4 distinct stages
        xs = list(sankey_trace.node.x)
        self.assertTrue(any(x < 0.1 for x in xs))     # stage 0 (inflow)
        self.assertTrue(any(0.2 < x < 0.35 for x in xs))  # stage 1 (taxes/net)
        self.assertTrue(any(0.55 < x < 0.7 for x in xs))  # stage 2 (buckets)
        self.assertTrue(any(x > 0.9 for x in xs))    # stage 3 (categories)

    def test_drilldown_hides_upstream(self):
        """Verify drilling down into Fixed Expenses hides Gross Salary, Taxes, and Net Income."""
        data = prepare_cash_flow_sankey_data(self.conn, days=30)
        fig = build_cash_flow_sankey(data, drilldown_flow="Fixed Expenses")
        self.assertIsInstance(fig, go.Figure)

        sankey_trace = fig.data[0]
        labels = list(sankey_trace.node.label)

        # Upstream stages must be hidden
        self.assertNotIn("Gross Salary", labels)
        self.assertNotIn("Taxes (Box 1)", labels)
        self.assertNotIn("Net Income", labels)

        # Fixed Expenses root and its children must be present
        self.assertIn("Fixed Expenses", labels)
        self.assertIn("Housing", labels)

    def test_drilldown_discretionary(self):
        """Verify drilling down into Discretionary hides upstream stages and shows child categories."""
        data = prepare_cash_flow_sankey_data(self.conn, days=30)
        fig = build_cash_flow_sankey(data, drilldown_flow="Discretionary")
        self.assertIsInstance(fig, go.Figure)

        sankey_trace = fig.data[0]
        labels = list(sankey_trace.node.label)

        self.assertNotIn("Gross Salary", labels)
        self.assertNotIn("Fixed Expenses", labels)
        self.assertIn("Discretionary", labels)
        self.assertIn("Food & Dining", labels)

    @patch("ui.charts.is_hidden", return_value=True)
    def test_sankey_privacy_mode(self, mock_is_hidden):
        """Verify hover templates are censored when privacy mode is active."""
        data = prepare_cash_flow_sankey_data(self.conn, days=30)
        fig = build_cash_flow_sankey(data, drilldown_flow="Full Flow")
        sankey_trace = fig.data[0]

        self.assertIn("Censored", sankey_trace.node.hovertemplate)
        self.assertIn("Censored", sankey_trace.link.hovertemplate)

    def test_prepare_cash_flow_sankey_data_with_date_range(self):
        """Verify Sankey data filters strictly within start_date and end_date (MTD)."""
        data = prepare_cash_flow_sankey_data(
            self.conn,
            start_date="2026-10-01",
            end_date="2026-10-31",
        )
        self.assertIsInstance(data, dict)
        self.assertIn("gross_salary", data)
        self.assertIn("fixed_spent", data)
        self.assertIn("disc_spent", data)

    @patch("streamlit.rerun")
    @patch("ui.sankey_component.component.render_interactive_sankey")
    def test_render_cash_flow_sankey_click_event(self, mock_render_component, mock_rerun):
        """Verify clicking a flow node in the diagram updates drilldown state and triggers rerun."""
        from ui.charts import render_cash_flow_sankey

        # Simulate user clicking 'Fixed Expenses' on the diagram
        mock_render_component.return_value = {"clicked": "Fixed Expenses", "ts": 12345}

        st.session_state.clear()
        render_cash_flow_sankey(self.conn, key_prefix="test_sankey")

        self.assertEqual(st.session_state.get("test_sankey_drilldown_state"), "Fixed Expenses")
        mock_rerun.assert_called_once_with(scope="fragment")

    @patch("streamlit.rerun")
    @patch("ui.sankey_component.component.render_interactive_sankey")
    def test_render_cash_flow_sankey_reset_click(self, mock_render_component, mock_rerun):
        """Verify clicking reset or active root node returns to Full Flow."""
        from ui.charts import render_cash_flow_sankey

        st.session_state["test_reset_drilldown_state"] = "Fixed Expenses"
        st.session_state["test_reset_last_click_ts"] = 11111

        mock_render_component.return_value = {"clicked": "RESET", "ts": 22222}
        render_cash_flow_sankey(self.conn, key_prefix="test_reset")

        self.assertEqual(st.session_state.get("test_reset_drilldown_state"), "Full Flow")
        mock_rerun.assert_called_once_with(scope="fragment")


if __name__ == "__main__":
    unittest.main()
