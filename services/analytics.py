from datetime import datetime, timedelta
import statistics
from typing import Any


def calculate_savings_rate(income: float, expenses: float) -> float:
    if income <= 0:
        return 0.0
    return ((income - expenses) / income) * 100.0


def calculate_burn_and_runway(
    monthly_expenses: list[float],
    liquid_cash: float,
) -> tuple[float, float, float]:
    """Returns (burn_rate, runway_months, runway_days).

    Burn rate is calculated from trailing 3 complete months (or available).
    """
    if not monthly_expenses:
        return 0.0, 0.0, 0.0

    recent_3 = monthly_expenses[-3:] if len(
        monthly_expenses) >= 3 else monthly_expenses
    burn_rate = sum(recent_3) / len(recent_3)

    if burn_rate <= 0:
        return 0.0, 999.0, 999.0 * 30.44

    runway_months = liquid_cash / burn_rate
    runway_days = runway_months * 30.44
    return burn_rate, runway_months, runway_days


def detect_recurring_charges(
    transactions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Detects recurring subscriptions / bills from transaction history.

    Filters: >=3 charges, amount within +-10% of median, cadence near 7, 30, or 365 days.
    """
    if not transactions:
        return []

    # Group by merchant
    by_merchant: dict[str, list[dict[str, Any]]] = {}
    for tx in transactions:
        if tx.get("is_internal_transfer"):
            continue
        # Subscriptions and recurring bills are outflows (negative in v_transactions)
        if tx.get("amount_eur", 0.0) >= 0 or tx.get("category_kind") == "income":
            continue
        amt = abs(tx.get("amount_eur", 0.0))
        if amt < 0.5:  # ignore micro test charges
            continue
        merchant = tx.get("merchant") or tx.get("merchant_normalized") or ""
        merchant = merchant.strip()
        if not merchant:
            continue
        by_merchant.setdefault(merchant, []).append(tx)

    recurring: list[dict[str, Any]] = []

    for merchant, txs in by_merchant.items():
        if len(txs) < 3:
            continue

        # Sort by date
        sorted_txs = sorted(
            txs,
            key=lambda x: (
                datetime.strptime(x["booking_date"][:10], "%Y-%m-%d").date()
                if isinstance(x["booking_date"], str)
                else x["booking_date"]
            ),
        )

        amounts = [abs(t.get("amount_eur", 0.0)) for t in sorted_txs]
        med_amt = statistics.median(amounts)
        if med_amt <= 0:
            continue

        # Check amount stability (+-10%)
        if not all(0.85 * med_amt <= a <= 1.15 * med_amt for a in amounts):
            continue

        dates = [
            datetime.strptime(t["booking_date"][:10], "%Y-%m-%d").date()
            if isinstance(t["booking_date"], str)
            else t["booking_date"]
            for t in sorted_txs
        ]

        intervals = [
            (dates[i] - dates[i - 1]).days for i in range(1, len(dates))]
        med_interval = statistics.median(intervals)

        cadence = None
        annual_mult = 0.0
        if 25 <= med_interval <= 35:
            cadence = "Monthly"
            annual_mult = 12.0
            next_date = dates[-1] + timedelta(days=30)
        elif 6 <= med_interval <= 8:
            cadence = "Weekly"
            annual_mult = 52.0
            next_date = dates[-1] + timedelta(days=7)
        elif 350 <= med_interval <= 380:
            cadence = "Yearly"
            annual_mult = 1.0
            next_date = dates[-1] + timedelta(days=365)

        if cadence:
            recurring.append(
                {
                    "merchant": merchant,
                    "cadence": cadence,
                    "amount_eur": round(med_amt, 2),
                    "annual_cost_eur": round(med_amt * annual_mult, 2),
                    "last_date": dates[-1].isoformat(),
                    "next_expected_date": next_date.isoformat(),
                    "occurrences": len(sorted_txs),
                }
            )

    return sorted(recurring, key=lambda x: x["annual_cost_eur"], reverse=True)
