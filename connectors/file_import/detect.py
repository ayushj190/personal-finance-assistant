from enum import Enum
import re
from typing import Callable

from connectors.base import RawTransaction
from connectors.file_import.camt053 import parse_camt053
from connectors.file_import.csv_profiles import (
    parse_abn_amro_tab,
    parse_etoro_money,
    parse_revolut_csv,
    parse_trade_republic_csv,
)
from connectors.file_import.mt940 import parse_mt940


class FileFormat(str, Enum):
    ETORO_MONEY_TSV = "etoro_money_tsv"
    REVOLUT_CSV = "revolut_csv"
    ABN_AMRO_TAB = "abn_amro_tab"
    TRADE_REPUBLIC_CSV = "trade_republic_csv"
    MT940 = "mt940"
    CAMT053 = "camt053"
    UNKNOWN = "unknown"


def detect_format(content: str) -> FileFormat:
    snippet = content[:4000]

    # Check XML / CAMT.053
    if "<BkToCstmrStmt>" in snippet or "camt.053" in snippet:
        return FileFormat.CAMT053

    # Check MT940
    if re.search(r":20:[^\n]+\n.*:61:", snippet, re.DOTALL) or (":20:" in snippet and ":25:" in snippet):
        return FileFormat.MT940

    # Check eToro Money TSV
    if "Local Amount" in snippet and ("Money Out" in snippet or "Exchange Rate" in snippet):
        return FileFormat.ETORO_MONEY_TSV

    # Check Revolut CSV
    if ("Started Date" in snippet or "Completed Date" in snippet) and "Product" in snippet:
        return FileFormat.REVOLUT_CSV

    # Check Trade Republic
    if ("Trade Republic" in snippet or "Cash Account" in snippet) or (
        ("Betrag" in snippet and "Saldo" in snippet) or ("Date" in snippet and "Amount" in snippet and "Balance" in snippet)
    ):
        return FileFormat.TRADE_REPUBLIC_CSV

    # Check ABN AMRO
    if "rekeningnummer" in snippet.lower() or "muntsoort" in snippet.lower():
        return FileFormat.ABN_AMRO_TAB

    # Check lines starting with NL.. IBAN followed by tab or comma
    first_lines = [line.strip() for line in snippet.splitlines() if line.strip()][:3]
    for line in first_lines:
        if re.match(r"^NL\d{2}[A-Z]{4}\d{10}", line):
            return FileFormat.ABN_AMRO_TAB

    return FileFormat.UNKNOWN


def get_parser(fmt: FileFormat) -> Callable[[str, str], list[RawTransaction]] | None:
    match fmt:
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


def parse_statement(content: str, default_account_id: str = "imported_account") -> tuple[FileFormat, list[RawTransaction]]:
    fmt = detect_format(content)
    parser = get_parser(fmt)
    if not parser:
        return fmt, []
    return fmt, parser(content, default_account_id)
