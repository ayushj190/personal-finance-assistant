from dataclasses import dataclass
from datetime import date
from typing import Protocol


@dataclass(frozen=True)
class RawAccount:
    external_id: str
    institution: str
    name: str
    currency: str
    asset_class: str  # 'cash', 'investment', 'liability'
    iban: str | None = None
    balance_minor: int | None = None


@dataclass(frozen=True)
class RawTransaction:
    account_external_id: str
    booking_date: date
    amount_minor: int  # signed minor units (cents): negative = outflow, positive = inflow
    currency: str
    description: str
    value_date: date | None = None
    external_ref: str | None = None
    counterparty_name: str | None = None
    counterparty_iban: str | None = None
    mcc: str | None = None


@dataclass(frozen=True)
class RawHolding:
    account_external_id: str
    ticker: str
    quantity: float
    currency: str
    asset_type: str  # 'etf', 'stock', 'crypto', 'bond', 'commodity', 'other'
    cost_basis_minor: int | None = None
    isin: str | None = None
    name: str | None = None
    region: str | None = None
    sector: str | None = None


class NeedsReauth(Exception):
    pass


class Connector(Protocol):
    name: str

    def is_configured(self) -> bool: ...
    def fetch_accounts(self) -> list[RawAccount]: ...
    def fetch_transactions(self, since: date) -> list[RawTransaction]: ...
    def fetch_holdings(self) -> list[RawHolding]: ...
