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


if __name__ == "__main__":
    unittest.main()
