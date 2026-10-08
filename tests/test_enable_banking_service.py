import unittest
from unittest.mock import MagicMock, patch
from datetime import date
from connectors.enable_banking_service import EnableBankingService


class TestEnableBankingServiceDefensive(unittest.TestCase):
    @patch.object(EnableBankingService, "_headers", return_value={"Authorization": "Bearer test"})
    @patch("connectors.enable_banking_service.secrets_vault.get", return_value="sess-123")
    @patch("connectors.enable_banking_service.httpx.Client")
    def test_fetch_accounts_handles_string_accounts_and_aspsp(self, mock_client_cls, _mock_vault_get, _mock_headers):

        # Mock response where accounts is a list of strings (UIDs) and aspsp is a string
        mock_session_resp = MagicMock()
        mock_session_resp.status_code = 200
        mock_session_resp.json.return_value = {
            "session_id": "sess-123",
            "aspsp": "Rabobank",
            "accounts": ["acc-uid-001", "acc-uid-002"],
        }

        # Mock response for /accounts/{uid}
        mock_acc_resp = MagicMock()
        mock_acc_resp.status_code = 200
        mock_acc_resp.json.return_value = {
            "account_id": {"iban": "NL91RABO0123456789"},
            "currency": "EUR",
        }

        # Mock response for balances
        mock_bal_resp = MagicMock()
        mock_bal_resp.status_code = 200
        mock_bal_resp.json.return_value = {
            "balances": [{"balance_amount": {"amount": "1250.50", "currency": "EUR"}}]
        }

        def mock_get(url, **kwargs):
            if "/sessions/" in url:
                return mock_session_resp
            elif "/balances" in url:
                return mock_bal_resp
            else:
                return mock_acc_resp

        mock_client = MagicMock()
        mock_client.__enter__.return_value.get.side_effect = mock_get
        mock_client_cls.return_value = mock_client

        eb = EnableBankingService()
        accounts = eb.fetch_accounts()

        self.assertEqual(len(accounts), 2)
        self.assertEqual(accounts[0].institution, "Rabobank")
        self.assertEqual(accounts[0].external_id, "acc-uid-001")
        self.assertEqual(accounts[0].iban, "NL91RABO0123456789")
        self.assertEqual(accounts[0].balance_minor, 125050)

    @patch.object(EnableBankingService, "_headers", return_value={"Authorization": "Bearer test"})
    @patch("connectors.enable_banking_service.secrets_vault.get", return_value="sess-123")
    @patch("connectors.enable_banking_service.httpx.Client")
    def test_fetch_transactions_handles_defensive_fields(self, mock_client_cls, _mock_vault_get, _mock_headers):

        # Mock session response
        mock_session_resp = MagicMock()
        mock_session_resp.status_code = 200
        mock_session_resp.json.return_value = {
            "session_id": "sess-123",
            "aspsp": {"name": "ABN AMRO"},
            "accounts": [{"uid": "acc-1", "iban": "NL01ABNA0000000000", "currency": "EUR"}],
        }

        # Mock transactions response
        mock_tx_resp = MagicMock()
        mock_tx_resp.status_code = 200
        mock_tx_resp.json.return_value = {
            "transactions": [
                {
                    "transaction_amount": {"amount": "45.00", "currency": "EUR"},
                    "credit_debit_indicator": "DBIT",
                    "booking_date": "2026-10-01",
                    "remittance_information": ["Albert Heijn", "Store 1234"],
                    "creditor": {"name": "Albert Heijn"},
                    "entry_reference": "TX123",
                }
            ]
        }

        def mock_get(url, **kwargs):
            if "/sessions/" in url:
                return mock_session_resp
            elif "/balances" in url:
                mock_b = MagicMock()
                mock_b.status_code = 200
                mock_b.json.return_value = {"balances": []}
                return mock_b
            else:
                return mock_tx_resp

        mock_client = MagicMock()
        mock_client.__enter__.return_value.get.side_effect = mock_get
        mock_client_cls.return_value = mock_client

        eb = EnableBankingService()
        txs = eb.fetch_transactions(since=date(2026, 9, 1))

        self.assertEqual(len(txs), 1)
        self.assertEqual(txs[0].amount_minor, -4500)
        self.assertEqual(txs[0].description, "Albert Heijn Store 1234")
        self.assertEqual(txs[0].counterparty_name, "Albert Heijn")


if __name__ == "__main__":
    unittest.main()
