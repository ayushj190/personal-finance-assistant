import datetime
from enum import Enum
import re
from typing import Callable

from services.llm_client import generate_json
from connectors.base import RawHolding, RawTransaction
from connectors.file_import.camt053 import parse_camt053
from connectors.file_import.csv_profiles import (
    parse_abn_amro_tab,
    parse_etoro_money,
    parse_etoro_statement_holdings,
    parse_etoro_statement_transactions,
    parse_revolut_csv,
)
from connectors.file_import.mt940 import parse_mt940


class FileFormat(str, Enum):
    ETORO_MONEY_TSV = "etoro_money_tsv"
    ETORO_STATEMENT_CSV = "etoro_statement_csv"
    REVOLUT_CSV = "revolut_csv"
    ABN_AMRO_TAB = "abn_amro_tab"
    MT940 = "mt940"
    CAMT053 = "camt053"
    UNKNOWN = "unknown"


def detect_format(content: str | bytes) -> FileFormat:
    if isinstance(content, bytes):
        if content.startswith(b"%PDF"):
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
    first_lines = [line.strip()
                   for line in snippet.splitlines() if line.strip()][:3]
    for line in first_lines:
        if re.match(r"^NL\d{2}[A-Z]{4}\d{10}", line):
            return FileFormat.ABN_AMRO_TAB



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

        case FileFormat.MT940:
            return parse_mt940
        case FileFormat.CAMT053:
            return parse_camt053
        case _:
            return None


def parse_statement(content: str | bytes, default_account_id: str = "imported_account") -> tuple[FileFormat, list[RawTransaction]]:
    fmt = detect_format(content)

    if isinstance(content, bytes):
        content = content.decode("utf-8", errors="replace")

    parser = get_parser(fmt)
    if not parser:
        return FileFormat.UNKNOWN, parse_statement_with_llm(content, default_account_id)
    return fmt, parser(content, default_account_id)


def parse_statement_with_llm(content: str | bytes, default_account_id: str) -> list[RawTransaction]:
    if isinstance(content, bytes):
        content = content.decode("utf-8", errors="replace")

    # LLM might not handle huge files, limit to first 8k chars
    snippet = content[:8000]
    schema = {
        "type": "object",
        "properties": {
            "transactions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "date": {"type": "string", "description": "YYYY-MM-DD"},
                        "amount": {"type": "number", "description": "Negative for outflows/expenses, positive for income"},
                        "merchant": {"type": "string"},
                        "description": {"type": "string"}
                    },
                    "required": ["date", "amount", "merchant"]
                }
            }
        },
        "required": ["transactions"]
    }

    messages = [
        {"role": "system", "content": "You are a data extraction AI. Extract transactions from the provided raw bank statement. Always convert amounts to negative for expenses and positive for income."},
        {"role": "user", "content": f"Extract transactions from this statement snippet:\n\n{snippet}"}
    ]

    parsed = generate_json(messages, schema=schema)
    if not parsed or "transactions" not in parsed:
        return []

    txs = []
    for tx in parsed["transactions"]:
        try:
            amt_minor = int(float(tx["amount"]) * 100)
            d = datetime.datetime.strptime(tx["date"][:10], "%Y-%m-%d").date()
            txs.append(
                RawTransaction(
                    account_external_id=default_account_id,
                    booking_date=d,
                    amount_minor=amt_minor,
                    currency="EUR",
                    description=tx.get("description", tx["merchant"]),
                    counterparty_name=tx["merchant"]
                )
            )
        except Exception:
            continue
    return txs


def parse_statement_holdings(content: str | bytes, default_account_id: str = "imported_account") -> list[RawHolding]:
    fmt = detect_format(content)
    if fmt == FileFormat.ETORO_STATEMENT_CSV:
        if isinstance(content, bytes):
            content = content.decode("utf-8", errors="replace")
        return parse_etoro_statement_holdings(content, default_account_id)
    return []


def parse_statement_balance(content: str | bytes, default_account_id: str = "imported_account") -> int | None:
    fmt = detect_format(content)
    return None
