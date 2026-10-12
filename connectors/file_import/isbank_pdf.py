from datetime import date, datetime
import io
import re
from typing import Optional
import pypdf

from connectors.base import RawTransaction


def _parse_turkish_amount(val_str: str) -> float:
    """Parse Turkish/European formatted amount strings into float."""
    s = val_str.strip().replace("TL", "").replace("TRY", "").replace("EUR", "").replace("USD", "").strip()
    # Check for negative in parentheses or trailing minus
    is_neg = False
    if s.startswith("-") or s.endswith("-"):
        is_neg = True
        s = s.replace("-", "").strip()
    elif s.startswith("(") and s.endswith(")"):
        is_neg = True
        s = s[1:-1].strip()

    if "." in s and "," in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".")

    try:
        val = float(s)
        return -val if is_neg else val
    except ValueError:
        return 0.0


def parse_isbank_pdf(
    pdf_bytes: bytes,
    default_account_id: str = "isbank_account",
) -> tuple[list[RawTransaction], Optional[int], Optional[str]]:
    """
    Deterministic PDF extractor for Türkiye İş Bankası statements.
    Supports both Turkish and English column headers.
    Returns:
        (transactions, ending_balance_minor, detected_iban_or_account)
    """
    if not pdf_bytes or not pdf_bytes.startswith(b"%PDF"):
        return [], None, None

    try:
        reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
    except Exception:
        return [], None, None

    if not reader.pages:
        return [], None, None

    full_text = "\n".join(page.extract_text() or "" for page in reader.pages)
    if not full_text.strip():
        return [], None, None

    text_upper = full_text.upper()

    # Identify Türkiye İş Bankası
    is_isbank = any(
        marker in text_upper
        for marker in [
            "İŞ BANKASI",
            "IS BANKASI",
            "ISBANK",
            "TÜRKİYE İŞ BANKASI",
            "TURKIYE IS BANKASI",
            "HESAP ÖZETİ",
            "ACCOUNT STATEMENT",
        ]
    )

    # Detect Currency
    currency = "TRY"
    if "USD" in text_upper and "TRY" not in text_upper and "TL" not in text_upper:
        currency = "USD"
    elif "EUR" in text_upper and "TRY" not in text_upper and "TL" not in text_upper:
        currency = "EUR"
    elif "GBP" in text_upper and "TRY" not in text_upper and "TL" not in text_upper:
        currency = "GBP"

    # Detect IBAN / Account Number
    detected_iban: Optional[str] = None
    iban_match = re.search(r"\b(TR\d{2}\s?\d{4}\s?\d{4}\s?\d{4}\s?\d{4}\s?\d{4}\s?\d{2})\b", full_text)
    if iban_match:
        detected_iban = iban_match.group(1).replace(" ", "")
    else:
        acc_match = re.search(r"(?:Hesap No|Account No|Hesap Numarası)\s*[:.-]?\s*([0-9-]+)", full_text, re.IGNORECASE)
        if acc_match:
            detected_iban = acc_match.group(1).strip()

    # Detect Ending Balance
    ending_balance_minor: Optional[int] = None
    bal_match = re.search(
        r"(?:Kapanış Bakiyesi|Son Bakiye|Bakiye|Closing Balance|Ending Balance|Kullanılabilir Bakiye)\s*[:.-]?\s*([+-]?\s*[\d.,]+)\s*(?:TL|TRY|EUR|USD|GBP)?",
        full_text,
        re.IGNORECASE,
    )
    if bal_match:
        try:
            bal_flt = _parse_turkish_amount(bal_match.group(1))
            ending_balance_minor = int(round(bal_flt * 100))
        except Exception:
            pass

    # Extract transactions
    transactions: list[RawTransaction] = []
    lines = full_text.splitlines()

    # Match lines starting with date: DD/MM/YYYY or DD.MM.YYYY
    date_regex = re.compile(r"^(\d{2}[./-]\d{2}[./-]\d{4})\s+(.+)$")
    amount_token_regex = re.compile(r"([+-]?[\d.,]+(?:\s*[-(B)])?)$")

    for line in lines:
        line_clean = line.strip()
        if not line_clean:
            continue

        match = date_regex.match(line_clean)
        if not match:
            continue

        date_str, rest = match.groups()
        # Parse date
        d_val: Optional[date] = None
        for fmt in ("%d/%m/%Y", "%d.%m.%Y", "%d-%m-%Y"):
            try:
                d_val = datetime.strptime(date_str, fmt).date()
                break
            except ValueError:
                continue

        if not d_val:
            continue

        # Split remaining line into description and amounts
        tokens = rest.split()
        if len(tokens) < 2:
            continue

        # Look for numbers from the right (Amount, Balance or Debit, Credit, Balance)
        num_indices = []
        for i in range(len(tokens) - 1, -1, -1):
            tok = tokens[i].replace("TL", "").replace("TRY", "").replace("EUR", "").replace("USD", "").strip()
            # Clean trailing (B) for Borç or (A) for Alacak
            is_borc = tok.endswith("(B)") or tok.endswith("B")
            is_alacak = tok.endswith("(A)") or tok.endswith("A")
            tok_num = re.sub(r"[()BAba]", "", tok).strip()
            if re.match(r"^[+-]?\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{1,2})?$", tok_num) or re.match(r"^[+-]?\d+(?:[.,]\d{1,2})?$", tok_num):
                num_indices.append((i, tok_num, is_borc, is_alacak))
            else:
                break

        if not num_indices:
            continue

        num_indices.reverse()
        desc_tokens = tokens[: num_indices[0][0]]
        description = " ".join(desc_tokens).strip()
        if not description:
            description = "İşbank İşlem"

        # Determine amount
        amt_flt = 0.0
        if len(num_indices) >= 2:
            # First is Amount, last is Balance
            tok_idx, raw_amt, is_borc_tok, is_alacak_tok = num_indices[0]
            amt_flt = _parse_turkish_amount(raw_amt)
            is_borc = is_borc_tok or "(B)" in line_clean.upper() or "BORÇ" in line_clean.upper() or "DEBIT" in line_clean.upper()
            is_alacak = is_alacak_tok or "(A)" in line_clean.upper() or "ALACAK" in line_clean.upper() or "CREDIT" in line_clean.upper()

            if is_borc:
                amt_flt = -abs(amt_flt)
            elif is_alacak:
                amt_flt = abs(amt_flt)

            # Check last token as ending balance candidate if none set
            if ending_balance_minor is None:
                try:
                    last_bal_flt = _parse_turkish_amount(num_indices[-1][1])
                    ending_balance_minor = int(round(last_bal_flt * 100))
                except Exception:
                    pass
        else:
            tok_idx, raw_amt, is_borc_tok, is_alacak_tok = num_indices[0]
            amt_flt = _parse_turkish_amount(raw_amt)
            if is_borc_tok or "(B)" in line_clean.upper() or "BORÇ" in line_clean.upper() or "DEBIT" in line_clean.upper():
                amt_flt = -abs(amt_flt)

        amt_minor = int(round(amt_flt * 100))
        if amt_minor == 0:
            continue

        transactions.append(
            RawTransaction(
                account_external_id=default_account_id,
                booking_date=d_val,
                amount_minor=amt_minor,
                currency=currency,
                description=description,
                counterparty_name=description,
            )
        )

    return transactions, ending_balance_minor, detected_iban
