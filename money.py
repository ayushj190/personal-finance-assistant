from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Iterable, Sequence


@dataclass(frozen=True, slots=True)
class Money:
    cents: int
    currency: str = "EUR"

    @classmethod
    def from_cents(cls, cents: int | None, currency: str = "EUR") -> Money:
        """Create Money from integer cents. None becomes 0."""
        if cents is None:
            return cls(0, currency)
        return cls(int(cents), currency)

    @classmethod
    def from_major(cls, value: str | Decimal | float | int, currency: str = "EUR") -> Money:
        """Create Money from a major currency unit value (e.g. 12.34 -> 1234 cents)."""
        if value is None:
            return cls(0, currency)
        if isinstance(value, float):
            d = Decimal(str(value))
        elif isinstance(value, (int, str)):
            d = Decimal(str(value))
        elif isinstance(value, Decimal):
            d = value
        else:
            raise TypeError(f"Cannot convert {type(value)} to Money")

        # Multiply by 100 and round half up to nearest integer cent
        cents_d = (d * Decimal("100")).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        return cls(int(cents_d), currency)

    def to_major(self) -> float:
        """Return major unit float for presentation boundaries (charts, format)."""
        return self.cents / 100.0

    def __add__(self, other: object) -> Money:
        if not isinstance(other, Money):
            return NotImplemented
        if self.currency != other.currency:
            raise ValueError(f"Currency mismatch: {self.currency} != {other.currency}")
        return Money(self.cents + other.cents, self.currency)

    def __sub__(self, other: object) -> Money:
        if not isinstance(other, Money):
            return NotImplemented
        if self.currency != other.currency:
            raise ValueError(f"Currency mismatch: {self.currency} != {other.currency}")
        return Money(self.cents - other.cents, self.currency)

    def __neg__(self) -> Money:
        return Money(-self.cents, self.currency)

    def __abs__(self) -> Money:
        return Money(abs(self.cents), self.currency)

    def __mul__(self, other: int | Decimal | float) -> Money:
        if isinstance(other, int):
            return Money(self.cents * other, self.currency)
        if isinstance(other, (Decimal, float)):
            d = Decimal(str(other)) if isinstance(other, float) else other
            cents_d = (Decimal(self.cents) * d).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
            return Money(int(cents_d), self.currency)
        return NotImplemented

    def __rmul__(self, other: int | Decimal | float) -> Money:
        return self.__mul__(other)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Money):
            return False
        return self.cents == other.cents and self.currency == other.currency

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, Money):
            return NotImplemented
        if self.currency != other.currency:
            raise ValueError(f"Currency mismatch: {self.currency} != {other.currency}")
        return self.cents < other.cents

    def __le__(self, other: object) -> bool:
        if not isinstance(other, Money):
            return NotImplemented
        if self.currency != other.currency:
            raise ValueError(f"Currency mismatch: {self.currency} != {other.currency}")
        return self.cents <= other.cents

    def __gt__(self, other: object) -> bool:
        if not isinstance(other, Money):
            return NotImplemented
        if self.currency != other.currency:
            raise ValueError(f"Currency mismatch: {self.currency} != {other.currency}")
        return self.cents > other.cents

    def __ge__(self, other: object) -> bool:
        if not isinstance(other, Money):
            return NotImplemented
        if self.currency != other.currency:
            raise ValueError(f"Currency mismatch: {self.currency} != {other.currency}")
        return self.cents >= other.cents


def sum_money(items: Iterable[Money], currency: str = "EUR") -> Money:
    """Sum an iterable of Money items. Returns Money(0, currency) for empty iterable."""
    total_cents = 0
    for item in items:
        if item.currency != currency:
            raise ValueError(f"Currency mismatch in sum_money: {item.currency} != {currency}")
        total_cents += item.cents
    return Money(total_cents, currency)
