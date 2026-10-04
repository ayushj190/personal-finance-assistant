import asyncio
from datetime import date, datetime
import json
from pathlib import Path
from typing import Any

from connectors.base import NeedsReauth, RawAccount, RawHolding, RawTransaction
from connectors.file_import.csv_profiles import to_minor
from services import secrets_vault


class TradeRepublicService:
    def is_configured(self) -> bool:
        cookies_str = secrets_vault.get("tr_cookies")
        return bool(cookies_str)

    def fetch_accounts(self) -> list[RawAccount]:
        if not self.is_configured():
            return []

        # Return Cash and Portfolio accounts
        return [
            RawAccount(
                external_id="tr_cash_eur",
                institution="Trade Republic",
                name="Trade Republic Cash",
                currency="EUR",
                asset_class="cash",
            ),
            RawAccount(
                external_id="tr_portfolio_eur",
                institution="Trade Republic",
                name="Trade Republic Securities",
                currency="EUR",
                asset_class="investment",
            ),
        ]

    def fetch_holdings(self) -> list[RawHolding]:
        if not self.is_configured():
            return []

        holdings_cache = secrets_vault.get("tr_holdings_cache")
        if holdings_cache:
            try:
                data = json.loads(holdings_cache)
                return [
                    RawHolding(
                        account_external_id="tr_portfolio_eur",
                        ticker=item.get("ticker", item.get("isin", "UNKNOWN")),
                        isin=item.get("isin"),
                        quantity=float(item.get("quantity", 0.0)),
                        currency="EUR",
                        asset_type=item.get("asset_type", "etf"),
                        cost_basis_minor=item.get("cost_basis_minor"),
                        name=item.get("name"),
                    )
                    for item in data
                ]
            except Exception:
                pass
        return []

    def fetch_transactions(self, since: date) -> list[RawTransaction]:
        return []
