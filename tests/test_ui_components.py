import unittest
from unittest.mock import patch

from ui.components import format_money, mask_if_hidden, status_badge


class TestUIComponents(unittest.TestCase):
    def test_format_money_normal(self):
        with patch("streamlit.session_state", {}):
            self.assertEqual(format_money(1234.56, "€"), "€1,234.56")
            self.assertEqual(format_money(0, "€"), "€0.00")
            self.assertEqual(format_money(500, "$"), "$500.00")

    def test_format_money_privacy_hidden(self):
        with patch("streamlit.session_state", {"hide_amounts": True}):
            self.assertEqual(format_money(1234.56, "€"), "€****")
            self.assertEqual(format_money(0, "€"), "€****")
            self.assertEqual(format_money(500, "$"), "$****")

    def test_mask_if_hidden(self):
        with patch("streamlit.session_state", {"hide_amounts": True}):
            self.assertEqual(mask_if_hidden("€1,234.56"), "€****")
            self.assertEqual(mask_if_hidden("+€50.00"), "+€****")
            self.assertEqual(mask_if_hidden("-€25.00"), "-€****")
            self.assertEqual(mask_if_hidden("$100.50"), "$****")
            self.assertEqual(mask_if_hidden(
                "Est. +€2.50 accrued"), "Est. +€**** accrued")
            self.assertEqual(mask_if_hidden("12.5% return"), "12.5% return")
            self.assertEqual(mask_if_hidden("+5.0%"), "+5.0%")
            self.assertEqual(mask_if_hidden("-3.2%"), "-3.2%")
            self.assertEqual(mask_if_hidden("10 assets"), "10 assets")

    def test_mask_if_not_hidden(self):
        with patch("streamlit.session_state", {"hide_amounts": False}):
            self.assertEqual(mask_if_hidden("€1,234.56"), "€1,234.56")
            self.assertEqual(mask_if_hidden("+€50.00"), "+€50.00")

    def test_status_badge(self):
        badge = status_badge("🟢 Synced 12:00", "success")
        self.assertIn("status-dot-success", badge)
        self.assertIn("🟢 Synced 12:00", badge)

    def test_institution_logo_svg(self):
        from ui.logos import get_institution_logo_svg
        abn_svg = get_institution_logo_svg("ABN AMRO", size=24)
        self.assertIn("<svg", abn_svg)
        self.assertIn('width="24"', abn_svg)
        self.assertIn("#008269", abn_svg)

        revolut_svg = get_institution_logo_svg("Revolut")
        self.assertIn("<svg", revolut_svg)
        self.assertIn("#191C1F", revolut_svg)

        unknown_svg = get_institution_logo_svg("Unknown Bank")
        self.assertIn("<svg", unknown_svg)
        self.assertIn("#334155", unknown_svg)

    def test_clean_account_name(self):
        from ui.pages.dashboard import clean_account_name
        accounts = [
            {"id": 1, "institution": "eToro", "name": "eToro USD Investment", "asset_class": "investment", "currency": "USD"},
            {"id": 2, "institution": "eToro Bank", "name": "eToro Money (Cash)", "asset_class": "cash", "currency": "EUR"},
            {"id": 3, "institution": "ABN AMRO", "name": "ABN AMRO (EUR)", "asset_class": "cash", "currency": "EUR"},
            {"id": 4, "institution": "Revolut", "name": "Revolut (USD)", "asset_class": "cash", "currency": "USD"},
            {"id": 5, "institution": "Revolut", "name": "Revolut (EUR)", "asset_class": "cash", "currency": "EUR"},
        ]
        self.assertEqual(clean_account_name(accounts[0], accounts), "eToro (Invest)")
        self.assertEqual(clean_account_name(accounts[1], accounts), "eToro (Cash)")
        self.assertEqual(clean_account_name(accounts[2], accounts), "ABN AMRO")
        self.assertEqual(clean_account_name(accounts[3], accounts), "Revolut (USD)")
        self.assertEqual(clean_account_name(accounts[4], accounts), "Revolut (EUR)")

    def test_transactions_privacy_masking(self):
        """Transactions page masks both amounts and merchant names when hide_amounts is True."""
        import pandas as pd
        from ui.components import format_money, is_hidden

        df = pd.DataFrame([
            {"id": 1, "booking_date": "2026-10-01", "account": "Checking", "amount_eur": 45.50, "merchant": "Albert Heijn", "category": "Groceries", "is_internal_transfer": False}
        ])

        with patch("streamlit.session_state", {"hide_amounts": True}):
            self.assertTrue(is_hidden())
            df_display = df.copy()
            df_display["amount_eur"] = df_display["amount_eur"].map(lambda x: format_money(x))
            df_display["merchant"] = "****"

            self.assertEqual(df_display.iloc[0]["amount_eur"], "€****")
            self.assertEqual(df_display.iloc[0]["merchant"], "****")


if __name__ == "__main__":
    unittest.main()
