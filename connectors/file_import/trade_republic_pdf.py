from datetime import date, datetime
import io
import re
from typing import Any
from pypdf import PdfReader

from connectors.base import RawHolding, RawTransaction
from connectors.file_import.csv_profiles import to_minor


def extract_text_from_pdf(content: bytes | str) -> str:
    if isinstance(content, str):
        # Already extracted text or string
        return content
    stream = io.BytesIO(content)
    reader = PdfReader(stream)
    pages = []
    for page in reader.pages:
        txt = page.extract_text()
        if txt:
            pages.append(txt)
    return "\n".join(pages)


def parse_trade_republic_pdf(
    content: bytes | str,
    default_account_id: str = "tr_cash_eur",
) -> tuple[list[RawTransaction], list[RawHolding], int | None]:
    text = extract_text_from_pdf(content)
    txs: list[RawTransaction] = []
    holdings: list[RawHolding] = []

    lines = [l.strip() for l in text.splitlines() if l.strip()]

    is_statement = any(k in text.upper() for k in ("KONTOAUSZUG", "REKENINGAFSCHRIFT", "EINDSALDO", "BEGINSALDO", "ACCOUNT STATEMENT"))
    if not is_statement and ("WERTPAPIERABRECHNUNG" in text.upper() or "ABRECHNUNG" in text.upper()):
        isin_match = re.search(r"\b([A-Z]{2}[A-Z0-9]{9}\d)\b", text)
        date_match = re.search(r"(\d{2}\.\d{2}\.\d{4})", text)
        qty_match = re.search(r"(\d+(?:[,\.]\d+)?)\s*(?:Stk|Stück|St\b)", text, re.IGNORECASE)
        total_match = re.search(
            r"(?:Gesamtbetrag|Gesamt|Ausmachender Betrag|Total)\s*[:\s]*([+-]?\s*[\d\.,]+)\s*(?:€|EUR)",
            text,
            re.IGNORECASE,
        )

        isin = isin_match.group(1) if isin_match else None
        b_date = None
        if date_match:
            try:
                b_date = datetime.strptime(date_match.group(1), "%d.%m.%Y").date()
            except ValueError:
                pass

        if b_date and total_match:
            raw_amt = total_match.group(1).replace(" ", "")
            # If it's a Buy, cash outflow is negative
            is_buy = "KAUF" in text.upper() or "BUY" in text.upper()
            amt_minor = to_minor(raw_amt)
            if is_buy and amt_minor > 0:
                amt_minor = -amt_minor

            desc = f"{'Buy' if is_buy else 'Sell'} {isin or 'Securities'}"
            txs.append(
                RawTransaction(
                    account_external_id=default_account_id,
                    booking_date=b_date,
                    amount_minor=amt_minor,
                    currency="EUR",
                    description=desc,
                )
            )

        if isin and qty_match:
            try:
                qty = float(qty_match.group(1).replace(",", "."))
                holdings.append(
                    RawHolding(
                        account_external_id="tr_portfolio_eur",
                        ticker=isin,
                        isin=isin,
                        name=isin,
                        asset_type="stock",
                        quantity=qty,
                        cost_basis_minor=abs(to_minor(total_match.group(1))) if total_match else 0,
                        currency="EUR",
                    )
                )
            except Exception:
                pass

        if txs or holdings:
            return txs, holdings, None

    # 2. Check for Kontoauszug (Account statement table)
    # Line pattern: DD.MM.YYYY Description [+-]Amount [EUR|€]
    # And handle Dutch dates: DD MMM YYYY (e.g. 01 sep 2026)
    date_regex = re.compile(r"^(\d{2}\.\d{2}\.\d{4}|\d{4}-\d{2}-\d{2}|\d{2}\s+[a-z]{3}\.?\s+\d{4})", re.IGNORECASE)
    nl_months = {"jan": "01", "feb": "02", "maa": "03", "apr": "04", "mei": "05", "jun": "06", 
                 "jul": "07", "aug": "08", "sep": "09", "okt": "10", "nov": "11", "dec": "12"}

    for line in lines:
        line = line.replace("\xa0", " ") # Clean up non-breaking spaces
        d_match = date_regex.match(line)
        if not d_match:
            continue

        date_str = d_match.group(1).replace(".", "")
        try:
            if "." in d_match.group(1):
                booking_date = datetime.strptime(d_match.group(1), "%d.%m.%Y").date()
            elif "-" in d_match.group(1):
                booking_date = datetime.strptime(d_match.group(1), "%Y-%m-%d").date()
            else:
                parts = d_match.group(1).lower().replace(".", "").split()
                d, m, y = parts[0], parts[1], parts[2]
                m_num = nl_months.get(m, "01")
                booking_date = datetime.strptime(f"{d}.{m_num}.{y}", "%d.%m.%Y").date()
        except ValueError:
            continue

        rest = line[len(d_match.group(1)) :].strip()
        # Find all amounts at the end or embedded
        amounts = re.findall(r"([+-]?\s*[\d\.]+,\d{2}|[+-]?\s*[\d,]+\.\d{2})", rest)
        if not amounts:
            continue
            
        # The transaction amount is usually the first amount before the balance, or just the amount if no balance
        raw_amt_str = amounts[-2].replace(" ", "") if len(amounts) >= 2 else amounts[-1].replace(" ", "")
        amt_minor = to_minor(raw_amt_str)
        
        desc_lower = rest.lower()
        if "withdrawal" in desc_lower or "opname" in desc_lower or "af" in desc_lower.split():
            amt_minor = -abs(amt_minor)
        elif "deposit" in desc_lower or "storting" in desc_lower or "interest payment" in desc_lower or "rente" in desc_lower:
            amt_minor = abs(amt_minor)

        # Remove the amounts from description
        desc = rest
        for amt in amounts[-2:]:
            desc = desc.replace(amt, "")
        desc = desc.replace("€", "").replace("", "").strip()
        desc = re.sub(r"\s+", " ", desc)
        if not desc:
            desc = "Trade Republic Transaction"

        txs.append(
            RawTransaction(
                account_external_id=default_account_id,
                booking_date=booking_date,
                amount_minor=amt_minor,
                currency="EUR",
                description=desc,
            )
        )

    # 3. Check for Depotauszug (Positions table)
    # E.g. ISIN Name Quantity Price Value
    isin_pattern = re.compile(r"\b([A-Z]{2}[A-Z0-9]{9}\d)\b")
    for line in lines:
        isin_m = isin_pattern.search(line)
        if not isin_m:
            continue
        isin = isin_m.group(1)
        # Search for quantities and prices after ISIN
        after_isin = line[isin_m.end() :].strip()
        numbers = re.findall(r"[\d\.,]+", after_isin)
        if len(numbers) >= 2:
            try:
                qty = float(numbers[0].replace(".", "").replace(",", "."))
                val_cents = to_minor(numbers[-1])
                if qty > 0:
                    holdings.append(
                        RawHolding(
                            account_external_id="tr_portfolio_eur",
                            ticker=isin,
                            isin=isin,
                            name=isin,
                            asset_type="etf" if isin.startswith(("IE", "LU", "FR")) else "stock",
                            quantity=qty,
                            cost_basis_minor=val_cents,
                            currency="EUR",
                        )
                    )
            except Exception:
                pass

    final_balance_minor = None

    # Priority 1: Check for EINDSALDO / ENDSALDO / CLOSING BALANCE / SALDO EINDE across text
    eindsaldo_match = re.search(
        r"(?:EINDSALDO|ENDSALDO|CLOSING\s+BALANCE|SALDO\s+EINDE)[\s\S]{0,150}?(?:€|EUR)?\s*([+-]?(?:\d{1,3}(?:[.,]\d{3})+|\d+)[.,]\d{2})(?!\s*[\.\-\/]\d)(?!\d)",
        text,
        re.IGNORECASE,
    )
    if eindsaldo_match:
        try:
            final_balance_minor = to_minor(eindsaldo_match.group(1).replace(" ", ""))
        except Exception:
            pass

    # Priority 2: Line-by-line fallback
    if final_balance_minor is None:
        for idx, line in enumerate(lines):
            line_u = line.upper()
            if any(k in line_u for k in ("DEUTSCHE BANK", "BETAALREKENING", "ESCROW-REKENINGEN SALDO", "EINDSALDO", "ENDSALDO")):
                amounts = re.findall(r"([+-]?\s*[\d\.]+,\d{2}|[+-]?\s*[\d,]+\.\d{2})", line)
                if amounts:
                    try:
                        final_balance_minor = to_minor(amounts[-1].replace(" ", ""))
                        break
                    except Exception:
                        pass
                if idx + 1 < len(lines):
                    next_amounts = re.findall(r"([+-]?\s*[\d\.]+,\d{2}|[+-]?\s*[\d,]+\.\d{2})", lines[idx + 1])
                    if next_amounts:
                        try:
                            final_balance_minor = to_minor(next_amounts[-1].replace(" ", ""))
                            break
                        except Exception:
                            pass

    return txs, holdings, final_balance_minor
