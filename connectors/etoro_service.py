from datetime import date
from typing import Any
import uuid
import httpx

from connectors.base import NeedsReauth, RawAccount, RawHolding, RawTransaction
from connectors.file_import.csv_profiles import to_minor
from services import secrets_vault

BASE_URL = "https://public-api.etoro.com/api/v1"
BASE_URL_V2 = "https://public-api.etoro.com/api/v2"


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
        cash_balance_minor = None
        try:
            with httpx.Client(timeout=30.0) as client:
                resp = client.get(f"{BASE_URL}/balances", headers=self._headers())
                print(f"fetch_accounts resp: {resp.status_code} {resp.text}")
                if resp.status_code in (401, 403):
                    raise NeedsReauth("eToro API keys invalid or unauthorized.")
                if resp.status_code == 200:
                    data = resp.json()
                    equity = data.get("totalEquity") or data.get("credit", 0)
                    balance_minor = to_minor(equity)
                    avail_cash = data.get("availantBalance") or data.get("availableBalance") or data.get("cash") or data.get("credit")
                    if avail_cash is not None:
                        cash_balance_minor = to_minor(avail_cash)

                # Try dedicated money balance endpoint if available
                cash_resp = client.get(f"{BASE_URL}/money/transferable-balance", headers=self._headers())
                if cash_resp.status_code == 200:
                    cash_data = cash_resp.json()
                    t_bal = cash_data.get("amount") or cash_data.get("transferableBalance") or cash_data.get("balance")
                    if t_bal is not None:
                        cash_balance_minor = to_minor(t_bal)
        except NeedsReauth:
            raise
        except Exception as e:
            print(f"ERROR fetch_accounts: {e}")

        return [
            RawAccount(
                external_id="etoro_trading_usd",
                institution="eToro",
                name="eToro USD Investment",
                currency="USD",
                asset_class="investment",
                balance_minor=balance_minor,
            ),
            RawAccount(
                external_id="etoro_cash_eur",
                institution="eToro Bank",
                name="eToro Money (Cash)",
                currency="EUR",
                asset_class="cash",
                balance_minor=cash_balance_minor,
            ),
        ]

    def fetch_holdings(self) -> list[RawHolding]:
        if not self.is_configured():
            return []

        holdings: list[RawHolding] = []
        try:
            with httpx.Client(timeout=30.0) as client:
                resp = client.get(f"{BASE_URL_V2}/trading/info/instrument-breakdown", headers=self._headers())
                print(f"fetch_holdings resp: {resp.status_code} {resp.text}")
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
        except NeedsReauth:
            raise
        except Exception as e:
            print(f"ERROR fetch_holdings: {e}")

        return holdings

    def fetch_transactions(self, since: date) -> list[RawTransaction]:
        if not self.is_configured():
            return []

        txs: list[RawTransaction] = []
        headers = self._headers()
        try:
            with httpx.Client(timeout=30.0) as client:
                # 1. Fetch balance/cash history
                params = {"minDate": since.isoformat()}
                resp = client.get(f"{BASE_URL}/balances/history", headers=headers, params=params)
                if resp.status_code in (401, 403):
                    raise NeedsReauth("eToro API keys invalid or unauthorized.")
                
                entries = []
                if resp.status_code == 200:
                    data = resp.json()
                    entries = data.get("history") or data.get("transactions") or data.get("items") or (data if isinstance(data, list) else [])

                # Fallback to trade/cash history endpoint if balances/history is empty or not 200
                if not entries:
                    resp_trade = client.get(f"{BASE_URL_V2}/trading/info/trade/history", headers=headers, params=params)
                    if resp_trade.status_code == 200:
                        t_data = resp_trade.json()
                        entries = t_data.get("history") or t_data.get("trades") or (t_data if isinstance(t_data, list) else [])

                for item in entries:
                    if not isinstance(item, dict):
                        continue

                    raw_date = item.get("date") or item.get("timestamp") or item.get("openDateTime") or item.get("bookingDate")
                    if not raw_date:
                        continue
                    try:
                        tx_date = date.fromisoformat(str(raw_date)[:10])
                    except ValueError:
                        continue

                    if tx_date < since:
                        continue

                    amt = item.get("amount") or item.get("netAmount") or item.get("value") or item.get("profit") or 0
                    amt_minor = to_minor(amt)
                    if amt_minor == 0:
                        continue

                    desc = item.get("description") or item.get("type") or item.get("action") or item.get("instrumentDisplayName") or "eToro Cash Activity"
                    curr = item.get("currency", "USD")
                    ref = str(item.get("id") or item.get("transactionId") or item.get("positionId") or "")

                    txs.append(
                        RawTransaction(
                            account_external_id="etoro_trading_usd",
                            booking_date=tx_date,
                            amount_minor=amt_minor,
                            currency=curr,
                            description=str(desc),
                            external_ref=ref if ref else None,
                        )
                    )
        except NeedsReauth:
            raise
        except Exception as e:
            print(f"ERROR fetch_transactions: {e}")

        return txs

