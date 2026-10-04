import csv
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
import io
from typing import Iterator

from connectors.base import RawTransaction


def to_minor(val: Decimal | float | str) -> int:
    if isinstance(val, (int, float)):
        d = Decimal(str(val))
    elif isinstance(val, str):
        cleaned = val.replace(" ", "").replace(",", ".").strip()
        d = Decimal(cleaned)
    else:
        d = val
    return int((d * Decimal(100)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def parse_etoro_money(text: str, default_account_id: str = "etoro_money_eur") -> list[RawTransaction]:
    txs: list[RawTransaction] = []
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        return txs

    reader = csv.DictReader(lines, delimiter="\t")
    for row in reader:
        name = row.get("Name", "").strip()
        date_str = row.get("Date", "").strip()
        amount_str = row.get("Amount", "").strip()
        currency = row.get("Currency", "EUR").strip()
        if not name or not date_str or not amount_str:
            continue

        # Date format: DD/MM/YYYY HH:MM:SS
        try:
            ts = datetime.strptime(date_str, "%d/%m/%Y %H:%M:%S")
        except ValueError:
            try:
                ts = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                continue

        amount_minor = to_minor(amount_str)
        desc = name
        local_curr = row.get("Local Currency", "").strip()
        if local_curr and local_curr != currency:
            local_amt = row.get("Local Amount", "").strip()
            fx_rate = row.get("Exchange Rate", "").strip()
            desc += f" [{local_amt} {local_curr} @ {fx_rate}]"

        txs.append(
            RawTransaction(
                account_external_id=default_account_id,
                booking_date=ts.date(),
                amount_minor=amount_minor,
                currency=currency,
                description=desc,
                value_date=ts.date(),
            )
        )
    return txs


def parse_revolut_csv(text: str, default_account_id: str = "revolut_eur") -> list[RawTransaction]:
    txs: list[RawTransaction] = []
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        return txs

    # Sniff delimiter (comma or semicolon)
    sample = "\n".join(lines[:5])
    delimiter = ";" if sample.count(";") > sample.count(",") else ","
    reader = csv.DictReader(lines, delimiter=delimiter)

    for row in reader:
        # Standard Revolut columns: Type, Product, Started Date, Completed Date, Description, Amount, Fee, Currency, State, Balance
        state = row.get("State", "COMPLETED").strip().upper()
        if state not in ("COMPLETED", "FINISHED", ""):
            continue

        date_str = row.get("Completed Date") or row.get("Started Date") or row.get("Date")
        if not date_str:
            continue
        date_str = date_str.strip()

        # Parse date
        ts = None
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%d/%m/%Y %H:%M:%S", "%d/%m/%Y"):
            try:
                ts = datetime.strptime(date_str[:19], fmt)
                break
            except ValueError:
                pass
        if not ts:
            continue

        amount_str = row.get("Amount", "0").strip()
        currency = row.get("Currency", "EUR").strip()
        desc = row.get("Description", "").strip() or row.get("Type", "Revolut transaction").strip()
        amount_minor = to_minor(amount_str)

        txs.append(
            RawTransaction(
                account_external_id=default_account_id,
                booking_date=ts.date(),
                amount_minor=amount_minor,
                currency=currency,
                description=desc,
                value_date=ts.date(),
            )
        )
    return txs


def parse_abn_amro_tab(text: str, default_account_id: str = "abn_checking") -> list[RawTransaction]:
    txs: list[RawTransaction] = []
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        return txs

    # ABN AMRO .TAB is tab-delimited, often without header or with Dutch header:
    # 0: Account, 1: Currency, 2: Date (YYYYMMDD), 3: Before balance, 4: After balance, 5: Date2, 6: Amount, 7: Desc
    first_line = lines[0]
    has_header = "rekening" in first_line.lower() or "iban" in first_line.lower()
    start_idx = 1 if has_header else 0

    for line in lines[start_idx:]:
        cols = [c.strip() for c in line.split("\t")]
        if len(cols) < 7:
            # Try comma or semicolon if not tab
            if "," in line and len(line.split(",")) >= 7:
                cols = [c.strip() for c in line.split(",")]
            elif ";" in line and len(line.split(";")) >= 7:
                cols = [c.strip() for c in line.split(";")]
            else:
                continue

        account_iban = cols[0]
        currency = cols[1] if len(cols) > 1 and len(cols[1]) == 3 else "EUR"
        date_raw = cols[2] if len(cols) > 2 else ""
        try:
            if len(date_raw) == 8 and date_raw.isdigit():
                booking_date = datetime.strptime(date_raw, "%Y%m%d").date()
            else:
                booking_date = datetime.strptime(date_raw[:10], "%Y-%m-%d").date()
        except Exception:
            continue

        amount_raw = cols[6] if len(cols) > 6 else cols[-1]
        amount_minor = to_minor(amount_raw)
        desc = cols[7] if len(cols) > 7 else ""
        if len(cols) > 8:
            desc = " ".join(cols[7:])

        txs.append(
            RawTransaction(
                account_external_id=default_account_id,
                booking_date=booking_date,
                amount_minor=amount_minor,
                currency=currency,
                description=desc,
                counterparty_iban=account_iban if account_iban.startswith("NL") else None,
            )
        )
    return txs


def parse_trade_republic_csv(text: str, default_account_id: str = "tr_cash") -> list[RawTransaction]:
    txs: list[RawTransaction] = []
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        return txs

    sample = "\n".join(lines[:5])
    delimiter = ";" if sample.count(";") > sample.count(",") else ","
    reader = csv.DictReader(lines, delimiter=delimiter)

    for row in reader:
        date_str = row.get("Date") or row.get("Datum")
        if not date_str:
            continue
        try:
            booking_date = datetime.strptime(date_str.strip()[:10], "%Y-%m-%d").date()
        except ValueError:
            try:
                booking_date = datetime.strptime(date_str.strip()[:10], "%d.%m.%Y").date()
            except ValueError:
                continue

        amount_str = row.get("Amount") or row.get("Betrag") or "0"
        amount_minor = to_minor(amount_str)
        desc = row.get("Name") or row.get("Description") or row.get("Typ") or "Trade Republic"

        txs.append(
            RawTransaction(
                account_external_id=default_account_id,
                booking_date=booking_date,
                amount_minor=amount_minor,
                currency="EUR",
                description=desc.strip(),
            )
        )
    return txs
