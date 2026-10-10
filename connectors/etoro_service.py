from datetime import date
import json
from pathlib import Path
from typing import Any
import uuid
import httpx

from config import DB_PATH
from connectors.base import NeedsReauth, RawAccount, RawHolding, RawTransaction
from db import database
from services import secrets_vault

BASE_URL = "https://public-api.etoro.com/api/v1"
CACHE_FILE = Path(__file__).resolve().parent.parent / \
    "data" / "etoro_mirrors_cache.json"


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

        trading_balance_minor = None
        cash_balance_minor = None
        fx_rate = None

        try:
            with httpx.Client(timeout=30.0) as client:
                resp = client.get(f"{BASE_URL}/balances",
                                  headers=self._headers())
                if resp.status_code in (401, 403):
                    raise NeedsReauth(
                        "eToro API keys invalid or unauthorized.")
                if resp.status_code == 200:
                    data = resp.json()
                    balances = data.get("balances", [])
                    for b in balances:
                        acc_type = b.get("accountType")
                        curr = b.get("currency")
                        bal = float(b.get("balance") or 0.0)
                        if acc_type == "Trading":
                            trading_balance_minor = int(round(bal * 100))
                        elif acc_type == "Cash" or curr == "EUR":
                            cash_balance_minor = int(round(bal * 100))
                            if b.get("accountId"):
                                secrets_vault.put(
                                    "etoro_cash_account_id", str(b["accountId"]))
                            if b.get("exchangeRate"):
                                fx_rate = float(b["exchangeRate"])

            # If FX rate is present in balance response (e.g. 1 EUR = 1.12 USD -> EURUSD=X close = fx_rate)
            if fx_rate and fx_rate > 0:
                try:
                    conn = database.connect(DB_PATH)
                    database.upsert_market_quotes(
                        conn,
                        [
                            {
                                "ticker": "EURUSD=X",
                                "quote_date": date.today().isoformat(),
                                "close": fx_rate,
                                "prev_close": fx_rate,
                                "currency": "USD",
                            }
                        ],
                    )
                    conn.close()
                except Exception:
                    pass

        except NeedsReauth:
            raise
        except Exception as e:
            print(f"Error fetching eToro balances: {e}")

        return [
            RawAccount(
                external_id="etoro_trading_usd",
                institution="eToro",
                name="eToro USD Investment",
                currency="USD",
                asset_class="investment",
                balance_minor=trading_balance_minor,
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
        quotes_to_save: list[dict[str, Any]] = []
        mirrors_cache: list[dict[str, Any]] = []

        try:
            with httpx.Client(timeout=45.0) as client:
                resp = client.get(
                    f"{BASE_URL}/trading/info/real/pnl", headers=self._headers())
                if resp.status_code in (401, 403):
                    raise NeedsReauth(
                        "eToro API keys invalid or unauthorized.")
                if resp.status_code != 200:
                    return holdings

                data = resp.json()
                portfolio = data.get("clientPortfolio", {})
                direct_positions = portfolio.get("positions", [])
                mirrors = portfolio.get("mirrors", [])

                # 1. Fetch metadata for direct position and all mirror instruments
                mirror_pos_ids = {p.get("instrumentID") for m in mirrors for p in m.get(
                    "positions", []) if p.get("instrumentID")}
                inst_ids = sorted(list({p.get("instrumentID") for p in direct_positions if p.get(
                    "instrumentID")} | mirror_pos_ids))
                inst_map: dict[int, dict[str, Any]] = {}
                if inst_ids:
                    # eToro allows comma-separated instrument IDs
                    chunk_size = 50
                    for i in range(0, len(inst_ids), chunk_size):
                        chunk = inst_ids[i: i + chunk_size]
                        m_resp = client.get(
                            f"{BASE_URL}/market-data/instruments",
                            headers=self._headers(),
                            params={"instrumentIds": ",".join(
                                str(cid) for cid in chunk)},
                        )
                        if m_resp.status_code == 200:
                            for inst in m_resp.json().get("instrumentDisplayDatas", []):
                                inst_map[inst["instrumentID"]] = {
                                    "symbol": inst.get("symbolFull") or f"ID_{inst['instrumentID']}",
                                    "name": inst.get("instrumentDisplayName") or inst.get("symbolFull"),
                                    "type_id": inst.get("instrumentTypeID"),
                                }

                # 2. Aggregate direct holdings by symbol
                direct_agg: dict[str, dict[str, Any]] = {}
                today_str = date.today().isoformat()

                for p in direct_positions:
                    iid = p.get("instrumentID")
                    info = inst_map.get(iid, {})
                    symbol = info.get("symbol") or f"ID_{iid}"
                    name = info.get("name") or symbol
                    type_id = info.get("type_id", 5)
                    asset_type = "etf" if type_id == 6 else (
                        "crypto" if type_id == 1 else "stock")

                    units = float(p.get("units") or 0.0)
                    amount = float(p.get("amount") or 0.0)
                    pnl_info = p.get("unrealizedPnL") or {}
                    _pnl = float(pnl_info.get("pnL") or 0.0)
                    close_rate = float(pnl_info.get("closeRate") or 0.0)

                    if symbol not in direct_agg:
                        direct_agg[symbol] = {
                            "units": 0.0,
                            "invested": 0.0,
                            "name": name,
                            "asset_type": asset_type,
                            "close_rate": close_rate,
                        }
                    direct_agg[symbol]["units"] += units
                    direct_agg[symbol]["invested"] += amount
                    if close_rate > 0:
                        direct_agg[symbol]["close_rate"] = close_rate

                for sym, agg in direct_agg.items():
                    holdings.append(
                        RawHolding(
                            account_external_id="etoro_trading_usd",
                            ticker=sym,
                            quantity=agg["units"],
                            currency="USD",
                            asset_type=agg["asset_type"],
                            cost_basis_minor=int(round(agg["invested"] * 100)),
                            name=agg["name"],
                        )
                    )
                    if agg["close_rate"] > 0:
                        quotes_to_save.append(
                            {
                                "ticker": sym,
                                "quote_date": today_str,
                                "close": agg["close_rate"],
                                "prev_close": agg["close_rate"],
                                "currency": "USD",
                            }
                        )

                # 3. Process Copy Portfolios (Mirrors)
                for m in mirrors:
                    parent_username = m.get(
                        "parentUsername") or f"Trader_{m.get('parentCID')}"
                    ticker = f"COPY:{parent_username}"
                    name = f"Copy: {parent_username}"

                    init_inv = float(m.get("initialInvestment") or 0.0)
                    dep_sum = float(m.get("depositSummary") or 0.0)
                    with_sum = float(m.get("withdrawalSummary") or 0.0)
                    invested = init_inv + dep_sum - with_sum

                    avail_cash = float(m.get("availableAmount") or 0.0)
                    mirror_positions = m.get("positions", [])

                    pos_invested = sum(float(p.get("amount") or 0.0)
                                       for p in mirror_positions)
                    pos_pnl = sum(float((p.get("unrealizedPnL") or {}).get(
                        "pnL") or 0.0) for p in mirror_positions)
                    open_pos_val = pos_invested + pos_pnl
                    total_val = open_pos_val + avail_cash
                    unrealized_pnl = total_val - invested

                    # One row in holdings for the copied trader
                    holdings.append(
                        RawHolding(
                            account_external_id="etoro_trading_usd",
                            ticker=ticker,
                            quantity=1.0,
                            currency="USD",
                            asset_type="other",
                            cost_basis_minor=int(round(invested * 100)),
                            name=name,
                        )
                    )

                    # Update quote so v_holdings accurately computes current value and pnl
                    quotes_to_save.append(
                        {
                            "ticker": ticker,
                            "quote_date": today_str,
                            "close": total_val,
                            "prev_close": total_val,
                            "currency": "USD",
                        }
                    )

                    # Save detailed mirror breakdown for expandable UI
                    mirrors_cache.append(
                        {
                            "username": parent_username,
                            "ticker": ticker,
                            "invested_usd": invested,
                            "value_usd": total_val,
                            "unrealized_pnl_usd": unrealized_pnl,
                            "return_pct": (unrealized_pnl / invested * 100.0) if invested > 0 else 0.0,
                            "available_cash_usd": avail_cash,
                            "positions_count": len(mirror_positions),
                            "positions": [
                                {
                                    "position_id": p.get("positionID"),
                                    "instrument_id": p.get("instrumentID"),
                                    "symbol": inst_map.get(p.get("instrumentID"), {}).get("symbol", f"ID_{p.get('instrumentID')}"),
                                    "name": inst_map.get(p.get("instrumentID"), {}).get("name", "Unknown"),
                                    "type_id": inst_map.get(p.get("instrumentID"), {}).get("type_id", 5),
                                    "amount_usd": float(p.get("amount") or 0.0),
                                    "units": float(p.get("units") or 0.0),
                                    "pnl_usd": float((p.get("unrealizedPnL") or {}).get("pnL") or 0.0),
                                }
                                for p in mirror_positions
                            ],
                        }
                    )

            # Save mirror breakdown to local cache file
            try:
                CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
                with open(CACHE_FILE, "w", encoding="utf-8") as f:
                    json.dump(mirrors_cache, f, indent=2)
            except Exception as e:
                print(f"Error saving mirrors cache: {e}")

            # Save quotes directly to DB
            if quotes_to_save:
                try:
                    conn = database.connect(DB_PATH)
                    database.upsert_market_quotes(conn, quotes_to_save)
                    conn.close()
                except Exception as e:
                    print(f"Error saving eToro quotes: {e}")

        except NeedsReauth:
            raise
        except Exception as e:
            print(f"Error fetching eToro holdings: {e}")

        return holdings

    def fetch_transactions(self, since: date) -> list[RawTransaction]:
        if not self.is_configured():
            return []

        txs: list[RawTransaction] = []
        headers = self._headers()

        try:
            with httpx.Client(timeout=45.0) as client:
                # 1. Fetch EUR Cash Account Transactions
                cash_acc_id = secrets_vault.get("etoro_cash_account_id")
                if not cash_acc_id:
                    # Attempt to look up cash account id
                    b_resp = client.get(
                        f"{BASE_URL}/balances/cash", headers=headers, params={"includeZeroBalances": "true"})
                    if b_resp.status_code == 200:
                        b_list = b_resp.json().get("balances", [])
                        if b_list and b_list[0].get("accountId"):
                            cash_acc_id = str(b_list[0]["accountId"])
                            secrets_vault.put(
                                "etoro_cash_account_id", cash_acc_id)

                if cash_acc_id:
                    page_token = None
                    stop_paging = False
                    while not stop_paging:
                        params: dict[str, Any] = {"pageSize": 50}
                        if page_token:
                            params["pageToken"] = page_token

                        resp = client.get(
                            f"{BASE_URL}/money/accounts/cash/{cash_acc_id}/transactions",
                            headers=headers,
                            params=params,
                        )
                        if resp.status_code in (401, 403):
                            raise NeedsReauth(
                                "eToro API keys invalid or unauthorized.")
                        if resp.status_code != 200:
                            break

                        data = resp.json()
                        items = data.get("results", [])
                        if not items:
                            break

                        for item in items:
                            raw_date = item.get("postedAt")
                            if not raw_date:
                                continue
                            try:
                                tx_date = date.fromisoformat(
                                    str(raw_date)[:10])
                            except ValueError:
                                continue

                            if tx_date < since:
                                stop_paging = True
                                break

                            amount_val = float(item.get("amount") or 0.0)
                            direction = str(
                                item.get("direction") or "").lower()
                            # Debit is outflow (negative), credit is inflow (positive)
                            if direction == "debit":
                                amt_minor = -int(round(abs(amount_val) * 100))
                            else:
                                amt_minor = int(round(abs(amount_val) * 100))

                            if amt_minor == 0:
                                continue

                            # Extract merchant / counterparty
                            card_details = item.get(
                                "cardTransactionDetails") or {}
                            counterparty = item.get("counterparty") or {}
                            merchant = card_details.get(
                                "merchantName") or counterparty.get("name")
                            desc = merchant or item.get(
                                "transactionType") or "eToro Cash Transaction"
                            curr = item.get("currency") or "EUR"
                            ext_id = str(item.get("id"))

                            txs.append(
                                RawTransaction(
                                    account_external_id="etoro_cash_eur",
                                    booking_date=tx_date,
                                    amount_minor=amt_minor,
                                    currency=curr,
                                    description=desc,
                                    counterparty_name=merchant,
                                    external_ref=ext_id,
                                )
                            )

                        pag = data.get("pagination", {})
                        if pag.get("hasNext") and pag.get("nextPageToken") and not stop_paging:
                            page_token = pag.get("nextPageToken")
                        else:
                            break

                # 2. Fetch Closed Trades Realized P&L ("Investment Returns")
                try:
                    trades_resp = client.get(
                        f"{BASE_URL}/trading/info/trade/history",
                        headers=headers,
                        params={"minDate": since.isoformat(), "page": 1,
                                "pageSize": 100},
                    )
                    if trades_resp.status_code == 200:
                        trades_data = trades_resp.json()
                        trades = trades_data if isinstance(
                            trades_data, list) else trades_data.get("trades", [])
                        for trade in trades:
                            close_ts = trade.get("closeTimestamp")
                            if not close_ts:
                                continue
                            try:
                                t_date = date.fromisoformat(str(close_ts)[:10])
                            except ValueError:
                                continue

                            if t_date < since:
                                continue

                            net_profit = float(trade.get("netProfit") or 0.0)
                            pos_id = trade.get("positionId")
                            inst_id = trade.get("instrumentId")

                            txs.append(
                                RawTransaction(
                                    account_external_id="etoro_trading_usd",
                                    booking_date=t_date,
                                    amount_minor=int(round(net_profit * 100)),
                                    currency="USD",
                                    description=f"Closed Trade P&L (Instrument #{inst_id})",
                                    counterparty_name="eToro",
                                    external_ref=f"etoro_trade_{pos_id}",
                                )
                            )
                except Exception as e:
                    print(f"Error fetching eToro trade history: {e}")

        except NeedsReauth:
            raise
        except Exception as e:
            print(f"Error fetching eToro transactions: {e}")

        return txs

    def fetch_news(self, limit: int = 5) -> list[dict[str, Any]]:
        """Fetch news feed from eToro API."""
        if not self.is_configured():
            return []
        
        news_items = []
        try:
            with httpx.Client(timeout=15.0) as client:
                resp = client.get(
                    f"{BASE_URL}/feeds/news",
                    headers=self._headers(),
                    params={"take": limit, "reactionsPageSize": 1}
                )
                if resp.status_code == 200:
                    data = resp.json()
                    discussions = data.get("discussions", [])
                    for d in discussions:
                        post = d.get("post", {})
                        owner = post.get("owner", {})
                        message = post.get("message", {})
                        text = message.get("text", "")
                        
                        # Some posts might be just attachments, keep them if text is empty?
                        if not text:
                            continue

                        avatar_obj = owner.get("avatar")
                        avatar_url = avatar_obj.get("medium", "") if isinstance(avatar_obj, dict) else (avatar_obj if isinstance(avatar_obj, str) else "")

                        news_items.append({
                            "text": text,
                            "username": owner.get("username", "Unknown"),
                            "avatar": avatar_url,
                            "created": post.get("created", "")
                        })
        except Exception as e:
            print(f"Error fetching eToro news: {e}")
            
        return news_items
