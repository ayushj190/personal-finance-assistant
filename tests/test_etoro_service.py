import unittest
from connectors.etoro_service import EtoroService
from connectors.base import RawHolding


class TestEtoroService(unittest.TestCase):
    def test_service_initialization(self):
        service = EtoroService()
        self.assertIsNotNone(service)

    def test_holdings_structure(self):
        holding = RawHolding(
            account_external_id="etoro_trading_usd",
            ticker="COPY:Michalhla",
            name="Copy: Michalhla",
            quantity=1.0,
            currency="USD",
            asset_type="other",
            cost_basis_minor=902400,
        )
        self.assertEqual(holding.ticker, "COPY:Michalhla")
        self.assertEqual(holding.cost_basis_minor, 902400)

    def test_accounts_structure(self):
        service = EtoroService()
        accounts = service.fetch_accounts()
        cash_acc = next((a for a in accounts if a.external_id == "etoro_cash_eur"), None)
        self.assertIsNotNone(cash_acc)
        self.assertEqual(cash_acc.iban, "MT49CFTE280040000000000023")

    def test_fetch_transactions_filters_pending_and_rejected(self):
        from unittest.mock import patch, MagicMock
        from datetime import date

        service = EtoroService()
        with patch.object(service, "is_configured", return_value=True), \
             patch("services.secrets_vault.get", return_value="fake_cash_acc_id"), \
             patch("httpx.Client") as mock_client_cls:

            mock_client = MagicMock()
            mock_client_cls.return_value.__enter__.return_value = mock_client

            # Return transactions with settled, pending, rejected, failed, authorized, preAuthorize, reversal, and zero amounts
            mock_client.get.return_value.status_code = 200
            mock_client.get.return_value.json.side_effect = [
                {
                    "results": [
                        {"id": "1", "status": "settled", "postedAt": "2026-10-01T12:00:00Z", "amount": 10.0, "direction": "credit", "currency": "EUR"},
                        {"id": "2", "status": "pending", "postedAt": "2026-10-01T12:00:00Z", "amount": 20.0, "direction": "credit", "currency": "EUR"},
                        {"id": "3", "status": "rejected", "postedAt": "2026-10-01T12:00:00Z", "amount": 30.0, "direction": "credit", "currency": "EUR"},
                        {"id": "4", "status": "settled", "isPending": True, "postedAt": "2026-10-01T12:00:00Z", "amount": 40.0, "direction": "credit", "currency": "EUR"},
                        {"id": "5", "status": "completed", "postedAt": "2026-10-01T12:00:00Z", "amount": 50.0, "direction": "credit", "currency": "EUR"},
                        # Authorization hold (e.g. Cloudflare reversal / 0.00 check)
                        {"id": "6", "status": "authorized", "postedAt": "2026-10-01T12:00:00Z", "amount": 0.0, "direction": "credit", "currency": "EUR", "cardTransactionDetails": {"authorizationStatus": "reversal"}},
                        # Pre-authorization hold
                        {"id": "7", "status": "settled", "postedAt": "2026-10-01T12:00:00Z", "amount": 21.44, "direction": "debit", "currency": "EUR", "cardTransactionDetails": {"authorizationStatus": "preAuthorize"}},
                        # Failed card transaction
                        {"id": "8", "status": "failed", "postedAt": "2026-10-01T12:00:00Z", "amount": 43.45, "direction": "debit", "currency": "EUR", "cardTransactionDetails": {"authorizationStatus": "normal"}},
                        # Missing status
                        {"id": "9", "status": "", "postedAt": "2026-10-01T12:00:00Z", "amount": 15.0, "direction": "debit", "currency": "EUR"},
                    ],
                    "pagination": {"hasNext": False},
                },
                {
                    "trades": [
                        {"positionId": 101, "closeTimestamp": "2026-10-01T12:00:00Z", "netProfit": 15.0, "status": "closed"},
                        {"positionId": 102, "closeTimestamp": "2026-10-01T12:00:00Z", "netProfit": 25.0, "status": "pending"},
                        {"positionId": 103, "closeTimestamp": "2026-10-01T12:00:00Z", "netProfit": 35.0, "status": "rejected"},
                        {"positionId": 104, "closeTimestamp": None, "netProfit": 0.0, "status": "open"},
                    ]
                }
            ]

            txs = service.fetch_transactions(since=date(2026, 1, 1))
            ext_refs = [t.external_ref for t in txs]
            self.assertIn("1", ext_refs)
            self.assertIn("5", ext_refs)
            self.assertNotIn("2", ext_refs)
            self.assertNotIn("3", ext_refs)
            self.assertNotIn("4", ext_refs)
            self.assertNotIn("6", ext_refs)
            self.assertNotIn("7", ext_refs)
            self.assertNotIn("8", ext_refs)
            self.assertNotIn("9", ext_refs)
            self.assertIn("etoro_trade_101", ext_refs)
            self.assertNotIn("etoro_trade_102", ext_refs)
            self.assertNotIn("etoro_trade_103", ext_refs)
            self.assertNotIn("etoro_trade_104", ext_refs)


if __name__ == "__main__":
    unittest.main()

