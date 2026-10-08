import csv
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

from connectors.base import RawHolding, RawTransaction


def to_minor(val: Decimal | float | str | None) -> int:
    if val is None:
        return 0
    if isinstance(val, (int, float)):
        d = Decimal(str(val))
    elif isinstance(val, str):
        cleaned = val.replace(" ", "").strip()
        if not cleaned:
            return 0
        if "." in cleaned and "," in cleaned:
            if cleaned.rfind(",") > cleaned.rfind("."):
                # European: 1.000,00 -> 1000.00
                cleaned = cleaned.replace(".", "").replace(",", ".")
            else:
                # US: 1,000.00 -> 1000.00
                cleaned = cleaned.replace(",", "")
        elif "," in cleaned:
            cleaned = cleaned.replace(",", ".")
        d = Decimal(cleaned)
    else:
        d = val
    return int((d * Decimal(100)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def parse_etoro_money(text: str, default_account_id: str = "etoro_cash_eur") -> list[RawTransaction]:
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

        date_str = row.get("Completed Date") or row.get(
            "Started Date") or row.get("Date")
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
        desc = row.get("Description", "").strip() or row.get(
            "Type", "Revolut transaction").strip()
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
                booking_date = datetime.strptime(
                    date_raw[:10], "%Y-%m-%d").date()
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
                counterparty_iban=account_iban if account_iban.startswith(
                    "NL") else None,
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
            booking_date = datetime.strptime(
                date_str.strip()[:10], "%Y-%m-%d").date()
        except ValueError:
            try:
                booking_date = datetime.strptime(
                    date_str.strip()[:10], "%d.%m.%Y").date()
            except ValueError:
                continue

        amount_str = row.get("Amount") or row.get("Betrag") or "0"
        amount_minor = to_minor(amount_str)
        desc = row.get("Name") or row.get(
            "Description") or row.get("Typ") or "Trade Republic"

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


def _extract_sections(text: str) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {}
    current_sec = "default"
    known_headers = {"closed positions", "open positions",
                     "account activity", "dividends", "financial summary"}

    for line in text.splitlines():
        trimmed = line.strip().strip('"').strip("'").strip()
        lower = trimmed.lower()

        matched_header = None
        for kh in known_headers:
            if lower.startswith(kh):
                matched_header = kh
                break

        if matched_header:
            current_sec = matched_header
            sections[current_sec] = []
            continue

        sections.setdefault(current_sec, []).append(line)
    return sections


def parse_etoro_statement_transactions(text: str, default_account_id: str = "etoro_cash") -> list[RawTransaction]:
    sections = _extract_sections(text)
    act_lines = sections.get(
        "account activity") or sections.get("default") or []
    act_lines = [l for l in act_lines if l.strip(', \t\r\n')]
    if not act_lines:
        return []

    sample = "\n".join(act_lines[:5])
    delim = ";" if sample.count(";") > sample.count(",") else ","
    reader = csv.DictReader(act_lines, delimiter=delim)
    txs: list[RawTransaction] = []

    for row in reader:
        date_str = row.get("Date") or row.get("Date and Time")
        if not date_str:
            continue
        ts = None
        for fmt in ("%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%d/%m/%Y", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                ts = datetime.strptime(date_str.strip()[:19], fmt)
                break
            except ValueError:
                pass
        if not ts:
            continue

        amt_str = row.get("Amount") or row.get("Realized Equity Change") or "0"
        amt_minor = to_minor(amt_str)
        t_type = row.get("Type", "").strip()
        details = row.get("Details", "").strip()
        desc = f"{t_type} - {details}".strip(" -") or "eToro Activity"

        txs.append(
            RawTransaction(
                account_external_id=default_account_id,
                booking_date=ts.date(),
                amount_minor=amt_minor,
                currency="USD",
                description=desc,
                value_date=ts.date(),
            )
        )
    return txs


def parse_etoro_statement_holdings(text: str, default_account_id: str = "etoro_trading_usd") -> list[RawHolding]:
    sections = _extract_sections(text)
    open_lines = sections.get("open positions") or []
    open_lines = [l for l in open_lines if l.strip(', \t\r\n')]
    if not open_lines:
        return []

    sample = "\n".join(open_lines[:5])
    delim = ";" if sample.count(";") > sample.count(",") else ","
    reader = csv.DictReader(open_lines, delimiter=delim)
    holdings: list[RawHolding] = []

    for row in reader:
        action = row.get("Action", "").strip()
        units_str = row.get("Units", "0").strip()
        amt_str = row.get("Amount", "0").strip()
        isin = row.get("ISIN", "").strip() or None
        if not action or not units_str:
            continue

        try:
            qty = float(units_str.replace(",", "."))
        except ValueError:
            continue

        if qty <= 0:
            continue

        cost_cents = to_minor(amt_str)
        ticker = action
        if ticker.lower().startswith("buy "):
            ticker = ticker[4:].strip()
        elif ticker.lower().startswith("sell "):
            ticker = ticker[5:].strip()

        holdings.append(
            RawHolding(
                account_external_id=default_account_id,
                ticker=ticker,
                isin=isin,
                name=ticker,
                asset_type="stock",
                quantity=qty,
                cost_basis_minor=cost_cents,
                currency="USD",
            )
        )
    return holdings
