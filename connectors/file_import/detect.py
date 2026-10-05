from enum import Enum
import re
from typing import Callable

from connectors.base import RawHolding, RawTransaction
from connectors.file_import.camt053 import parse_camt053
from connectors.file_import.csv_profiles import (
    parse_abn_amro_tab,
    parse_etoro_money,
    parse_etoro_statement_holdings,
    parse_etoro_statement_transactions,
    parse_revolut_csv,
    parse_trade_republic_csv,
)
from connectors.file_import.mt940 import parse_mt940


from connectors.file_import.trade_republic_pdf import extract_text_from_pdf, parse_trade_republic_pdf


class FileFormat(str, Enum):
    ETORO_MONEY_TSV = "etoro_money_tsv"
    ETORO_STATEMENT_CSV = "etoro_statement_csv"
    REVOLUT_CSV = "revolut_csv"
    ABN_AMRO_TAB = "abn_amro_tab"
    TRADE_REPUBLIC_CSV = "trade_republic_csv"
    TRADE_REPUBLIC_PDF = "trade_republic_pdf"
    MT940 = "mt940"
    CAMT053 = "camt053"
    UNKNOWN = "unknown"


def detect_format(content: str | bytes) -> FileFormat:
    if isinstance(content, bytes):
        if content.startswith(b"%PDF"):
            try:
                pdf_text = extract_text_from_pdf(content)
                snip_pdf = pdf_text[:4000].lower()
                if (
                    "trade republic" in snip_pdf
                    or "kontoauszug" in snip_pdf
                    or "account statement" in snip_pdf
                    or "rekeningafschrift" in snip_pdf
                    or "eindsaldo" in snip_pdf
                ):
                    return FileFormat.TRADE_REPUBLIC_PDF
            except Exception:
                pass
            return FileFormat.UNKNOWN
        try:
            content = content.decode("utf-8", errors="replace")
        except Exception:
            return FileFormat.UNKNOWN

    snippet = content[:4000]

    # Check XML / CAMT.053
    if "<BkToCstmrStmt>" in snippet or "camt.053" in snippet:
        return FileFormat.CAMT053

    # Check MT940
    if re.search(r":20:[^\n]+\n.*:61:", snippet, re.DOTALL) or (":20:" in snippet and ":25:" in snippet):
        return FileFormat.MT940

    # Check eToro Account Statement (Closed Positions / Open Positions / Account Activity)
    if "closed positions" in snippet.lower() or "open positions" in snippet.lower() or "account activity" in snippet.lower():
        return FileFormat.ETORO_STATEMENT_CSV

    # Check eToro Money TSV
    if "Local Amount" in snippet and ("Money Out" in snippet or "Exchange Rate" in snippet):
        return FileFormat.ETORO_MONEY_TSV

    # Check Revolut CSV
    if ("Started Date" in snippet or "Completed Date" in snippet) and "Product" in snippet:
        return FileFormat.REVOLUT_CSV

    # Check ABN AMRO
    if "rekeningnummer" in snippet.lower() or "muntsoort" in snippet.lower():
        return FileFormat.ABN_AMRO_TAB

    # Check lines starting with NL.. IBAN followed by tab or comma
    first_lines = [line.strip() for line in snippet.splitlines() if line.strip()][:3]
    for line in first_lines:
        if re.match(r"^NL\d{2}[A-Z]{4}\d{10}", line):
            return FileFormat.ABN_AMRO_TAB

    # Check Trade Republic CSV
    if "trade republic" in snippet.lower() or (("date" in snippet.lower() or "datum" in snippet.lower()) and ("amount" in snippet.lower() or "betrag" in snippet.lower()) and (";" in snippet or "," in snippet)):
        return FileFormat.TRADE_REPUBLIC_CSV

    return FileFormat.UNKNOWN


def get_parser(fmt: FileFormat) -> Callable[[str, str], list[RawTransaction]] | None:
    match fmt:
        case FileFormat.ETORO_STATEMENT_CSV:
            return parse_etoro_statement_transactions
        case FileFormat.ETORO_MONEY_TSV:
            return parse_etoro_money
        case FileFormat.REVOLUT_CSV:
            return parse_revolut_csv
        case FileFormat.ABN_AMRO_TAB:
            return parse_abn_amro_tab
        case FileFormat.TRADE_REPUBLIC_CSV:
            return parse_trade_republic_csv
        case FileFormat.MT940:
            return parse_mt940
        case FileFormat.CAMT053:
            return parse_camt053
        case _:
            return None


def parse_statement(content: str | bytes, default_account_id: str = "imported_account") -> tuple[FileFormat, list[RawTransaction]]:
    fmt = detect_format(content)
    if fmt == FileFormat.TRADE_REPUBLIC_PDF:
        txs, _, _ = parse_trade_republic_pdf(content, default_account_id)
        return fmt, txs

    if isinstance(content, bytes):
        content = content.decode("utf-8", errors="replace")

    parser = get_parser(fmt)
    if not parser:
        return fmt, []
    return fmt, parser(content, default_account_id)


def parse_statement_holdings(content: str | bytes, default_account_id: str = "imported_account") -> list[RawHolding]:
    fmt = detect_format(content)
    if fmt == FileFormat.TRADE_REPUBLIC_PDF:
        _, holdings, _ = parse_trade_republic_pdf(content, default_account_id)
        return holdings
    if fmt == FileFormat.ETORO_STATEMENT_CSV:
        if isinstance(content, bytes):
            content = content.decode("utf-8", errors="replace")
        return parse_etoro_statement_holdings(content, default_account_id)
    return []

def parse_statement_balance(content: str | bytes, default_account_id: str = "imported_account") -> int | None:
    fmt = detect_format(content)
    if fmt == FileFormat.TRADE_REPUBLIC_PDF:
        _, _, balance = parse_trade_republic_pdf(content, default_account_id)
        return balance
    return None
