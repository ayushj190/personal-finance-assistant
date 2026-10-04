from datetime import date
from typing import Any
import uuid
import httpx

from connectors.base import NeedsReauth, RawAccount, RawHolding, RawTransaction
from connectors.file_import.csv_profiles import to_minor
from services import secrets_vault

BASE_URL = "https://public-api.etoro.com/api/v1"


class EtoroService:
    def is_configured(self) -> bool:
        api_key = secrets_vault.get("etoro_api_key")
        user_key = secrets_vault.get("etoro_user_key")
        return bool(api_key and user_key)

    def _headers(self) -> dict[str, str]:
        api_key = secrets_vault.get("etoro_api_key") or ""
        user_key = secrets_vault.get("etoro_user_key") or ""
        return {
            "x-api-key": api_key,
            "x-user-key": user_key,
            "x-request-id": str(uuid.uuid4()),
            "Content-Type": "application/json",
        }

    def fetch_accounts(self) -> list[RawAccount]:
        if not self.is_configured():
            return []

        # eToro portfolio balance endpoint
        balance_minor = None
        try:
            with httpx.Client(timeout=30.0) as client:
                resp = client.get(f"{BASE_URL}/portfolio/balance", headers=self._headers())
                if resp.status_code == 200:
                    data = resp.json()
                    equity = data.get("totalEquity") or data.get("credit", 0)
                    balance_minor = to_minor(equity)
        except Exception:
            pass

        return [
            RawAccount(
                external_id="etoro_trading_usd",
                institution="eToro",
                name="eToro USD Investment",
                currency="USD",
                asset_class="investment",
                balance_minor=balance_minor,
            )
        ]

    def fetch_holdings(self) -> list[RawHolding]:
        if not self.is_configured():
            return []

        holdings: list[RawHolding] = []
        try:
            with httpx.Client(timeout=30.0) as client:
                resp = client.get(f"{BASE_URL}/portfolio/positions", headers=self._headers())
                if resp.status_code in (401, 403):
                    raise NeedsReauth("eToro API keys invalid or unauthorized.")
                if resp.status_code != 200:
                    return holdings

                data = resp.json()
                positions = data.get("positions", [])
                by_symbol: dict[str, dict[str, Any]] = {}
                for pos in positions:
                    symbol = pos.get("instrumentDisplayName") or pos.get("symbol") or f"ID_{pos.get('instrumentId')}"
                    units = float(pos.get("units", 0.0))
                    invested = float(pos.get("amount", 0.0))
                    asset_type = pos.get("instrumentType", "stock").lower()

                    if symbol not in by_symbol:
                        by_symbol[symbol] = {
                            "units": 0.0,
                            "invested": 0.0,
                            "type": asset_type,
                            "name": pos.get("instrumentDisplayName", symbol),
                        }
                    by_symbol[symbol]["units"] += units
                    by_symbol[symbol]["invested"] += invested

                for sym, agg in by_symbol.items():
                    holdings.append(
                        RawHolding(
                            account_external_id="etoro_trading_usd",
                            ticker=sym,
                            quantity=agg["units"],
                            currency="USD",
                            asset_type=agg["type"] if agg["type"] in ("etf", "stock", "crypto", "bond") else "stock",
                            cost_basis_minor=to_minor(agg["invested"]),
                            name=agg["name"],
                        )
                    )
        except Exception:
            pass

        return holdings

    def fetch_transactions(self, since: date) -> list[RawTransaction]:
        return []
