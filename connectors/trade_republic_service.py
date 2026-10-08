from datetime import date

from connectors.base import RawAccount, RawHolding, RawTransaction


class TradeRepublicService:
    def is_configured(self) -> bool:
        # Trade Republic is configured as a savings cash account
        return True

    def fetch_accounts(self) -> list[RawAccount]:
        return [
            RawAccount(
                external_id="tr_cash_eur",
                institution="Trade Republic",
                name="Trade Republic Cash",
                currency="EUR",
                asset_class="cash",
            ),
        ]

    def fetch_holdings(self) -> list[RawHolding]:
        return []

    def fetch_transactions(self, since: date) -> list[RawTransaction]:
        return []
