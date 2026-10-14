from dataclasses import dataclass
from typing import Optional


@dataclass
class Account:
    id: Optional[int]
    provider: str
    institution: str
    name: str
    asset_class: str
    currency: str = "EUR"
    external_id: Optional[str] = None
    iban: Optional[str] = None
    apy: Optional[float] = None
    is_active: int = 1
    created_at: Optional[str] = None


@dataclass
class Transaction:
    id: Optional[int]
    account_id: int
    dedup_hash: str
    booking_date: str
    amount_minor: int
    amount_eur_minor: int
    description_raw: str
    currency: str = "EUR"
    external_ref: Optional[str] = None
    value_date: Optional[str] = None
    counterparty_name: Optional[str] = None
    counterparty_iban: Optional[str] = None
    merchant_normalized: Optional[str] = None
    mcc: Optional[str] = None
    category_id: Optional[int] = None
    category_source: Optional[str] = None
    is_internal_transfer: int = 0
    source: str = "csv"
    imported_at: Optional[str] = None

    @property
    def amount(self) -> float:
        return self.amount_minor / 100.0

    @property
    def amount_eur(self) -> float:
        return self.amount_eur_minor / 100.0


@dataclass
class Holding:
    id: Optional[int]
    account_id: int
    ticker: str
    asset_type: str
    quantity: float
    currency: str
    updated_at: str
    isin: Optional[str] = None
    name: Optional[str] = None
    region: Optional[str] = None
    sector: Optional[str] = None
    cost_basis_minor: Optional[int] = None
    status: str = "active"
    closed_at: Optional[str] = None
    realized_pnl_minor: int = 0
    realized_proceeds_minor: int = 0

    @property
    def cost_basis(self) -> float:
        return (self.cost_basis_minor or 0) / 100.0

    @property
    def realized_pnl(self) -> float:
        return self.realized_pnl_minor / 100.0

    @property
    def realized_proceeds(self) -> float:
        return self.realized_proceeds_minor / 100.0


@dataclass
class Liability:
    id: Optional[int]
    name: str
    loan_type: str
    original_principal_minor: int
    start_date: str
    lender: str = "ABN AMRO"
    home_value_minor: Optional[int] = None
    term_months: int = 360
    payment_match_pattern: Optional[str] = None
    balance_override_minor: Optional[int] = None
    balance_override_date: Optional[str] = None

    @property
    def original_principal(self) -> float:
        return self.original_principal_minor / 100.0

    @property
    def home_value(self) -> Optional[float]:
        return (self.home_value_minor / 100.0) if self.home_value_minor is not None else None


@dataclass
class TaxProfile:
    id: int = 1
    gross_annual_income: int = 0
    has_fiscal_partner: int = 0
    has_30_percent_ruling: int = 0
    is_entrepreneur: int = 0
    owns_home: int = 0
    birth_year: Optional[int] = None
    has_13th_month: int = 0
    expected_bonus_eur: int = 0
    pension_contribution_pct: float = 0.0
    employer_pension_match_pct: float = 0.0
    factor_a_minor: int = 0
    green_investments_minor: int = 0
    reserveringsruimte_minor: int = 0
    updated_at: Optional[str] = None

