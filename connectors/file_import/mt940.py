from decimal import Decimal
from typing import Any
import mt940

from connectors.base import RawTransaction
from connectors.file_import.csv_profiles import to_minor


def parse_mt940(text: str, default_account_id: str = "bank_account") -> list[RawTransaction]:
    transactions = mt940.parse(text)
    raw_txs: list[RawTransaction] = []

    for tx in transactions:
        data: dict[str, Any] = tx.data
        amt_obj = data.get("amount", {})
        amt_val = amt_obj.amount if hasattr(amt_obj, "amount") else Decimal(str(amt_obj.get("amount", "0")))
        status = data.get("status", "D")  # 'C' = credit (inflow), 'D' = debit (outflow)
        currency = str(amt_obj.currency if hasattr(amt_obj, "currency") else amt_obj.get("currency", "EUR"))

        amount_minor = to_minor(amt_val)
        if status == "D" and amount_minor > 0:
            amount_minor = -amount_minor
        elif status == "C" and amount_minor < 0:
            amount_minor = -amount_minor

        booking_date = data.get("date")
        if hasattr(booking_date, "date"):
            booking_date = booking_date.date()

        desc_parts = [
            str(data.get("transaction_details", "")),
            str(data.get("extra_details", "")),
        ]
        desc = " ".join(p.strip() for p in desc_parts if p.strip())

        raw_txs.append(
            RawTransaction(
                account_external_id=default_account_id,
                booking_date=booking_date,
                amount_minor=amount_minor,
                currency=currency,
                description=desc,
                external_ref=data.get("bank_reference"),
            )
        )
    return raw_txs
