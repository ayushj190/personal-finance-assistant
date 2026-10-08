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

    def test_mask_if_not_hidden(self):
        with patch("streamlit.session_state", {"hide_amounts": False}):
            self.assertEqual(mask_if_hidden("€1,234.56"), "€1,234.56")
            self.assertEqual(mask_if_hidden("+€50.00"), "+€50.00")

    def test_status_badge(self):
        badge = status_badge("🟢 Synced 12:00", "success")
        self.assertIn("status-dot-success", badge)
        self.assertIn("🟢 Synced 12:00", badge)


if __name__ == "__main__":
    unittest.main()
