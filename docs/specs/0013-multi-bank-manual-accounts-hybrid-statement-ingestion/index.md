# 0013. Multi Bank Manual Accounts and Hybrid Statement Ingestion

**Date**: 2026-10-12
**Status**: Accepted

## Summary

This build spec establishes manual bank account management and a hybrid statement ingestion pipeline for Slice 12. Users can create, update, and track balances for manual bank accounts across institutions and currencies via dedicated modal dialogs in Settings and Import Files. Statement file uploads gain an intelligent extraction workflow that uses fast deterministic table parsing via pypdf for structured bank formats (including Turkish and English Türkiye İş Bankası statements), falling back gracefully to local Ollama extraction for unfamiliar or irregular layouts. Users can review detected accounts, adjust target mappings, and confirm imported balances with high precision.

## Requirements

**User stories**:
- As a multi bank account holder, I want to manually create and track bank accounts (such as Türkiye İş Bankası, Garanti, or custom cash accounts) so that my net worth includes non API banks.
- As an account holder uploading bank statements, I want the importer to automatically parse diverse PDF statements in Turkish and English so that I do not need manual CSV conversions.
- As a privacy conscious user, I want unparsed or complex statements to process via local Ollama models without external cloud transmission.
- As an importer, I want to review target account mappings and opening or ending balances before transactions commit to the ledger.

**Acceptance criteria**:
- **AC-1**: A reusable modal dialog `manual_account_dialog` in `ui/dialogs.py` (accessible from Settings and Import Files) allows users to create and edit manual accounts with Name, Institution, Asset Class ('cash', 'investment', 'liability'), Currency, APY, and optional Initial Balance.
- **AC-2**: When creating an account with an initial balance, an initial snapshot is recorded in `account_snapshots` using integer minor units (cents) to establish the starting balance baseline.
- **AC-3**: `connectors/file_import/` provides a deterministic PDF extractor for Türkiye İş Bankası statements supporting both Turkish headers (Hesap Özeti, Tarih, Açıklama, Tutar, Bakiye) and English headers (Account Statement, Date, Description, Amount, Balance).
- **AC-4**: When deterministic extraction does not recognize a statement format or finds no valid transactions, the ingestion pipeline falls back to `parse_statement_with_llm` using local Ollama (`generate_json`) to extract structured transaction records.
- **AC-5**: The file import interface in `ui/pages/import_files.py` auto matches candidate accounts from detected IBANs or institution names, presenting an account selectbox allowing the user to confirm or reassign the target account before importing.
- **AC-6**: Non EUR accounts (such as TRY or USD) store exact minor amounts in `amount_minor` with matching `currency`, populating `amount_eur_minor` with `amount_minor` without forced FX conversion to preserve ledger transparency.
- **AC-7**: Detected ending balance (Bakiye / Eindsaldo) is extracted from PDF headers or footers, allowing the user to verify or adjust before updating account snapshots.

## Decision

**Chosen option**: Option 1: Reusable account dialog, deterministic pypdf parser with local Ollama fallback, and interactive target confirmation (see `rationale.md`).

We provide explicit manual account creation via Streamlit dialogs, a hybrid deterministic plus local LLM ingestion pipeline, and clear account mapping confirmation.

## Feature design

**Data model sketch**:
Uses existing tables without requiring new schema migrations:
- `accounts`: `id`, `provider` ('manual'), `institution`, `external_id`, `name`, `currency`, `asset_class`, `apy`, `is_active`, `created_at`
- `account_snapshots`: `account_id`, `snapshot_date`, `balance_minor`, `balance_eur_minor`
- `transactions`: `account_id`, `dedup_hash`, `booking_date`, `amount_minor`, `currency`, `amount_eur_minor`, `description_raw`, `counterparty_name`, `source` ('pdf', 'csv', 'mt940')

**API and module surface**:

| Function / Module | Signature | Key inputs | Outputs / Behavior | Key errors / Guarantees |
|---|---|---|---|---|
| `ui/dialogs.py` | `manual_account_dialog(account_id: int | None = None)` | Optional existing account ID | Modal dialog rendering form to create or edit manual account | Validates non empty name and institution; records initial snapshot if balance given |
| `connectors/file_import/isbank_pdf.py` | `parse_isbank_pdf(pdf_bytes: bytes, default_account_id: str) -> tuple[list[RawTransaction], int | None, str | None]` | Raw PDF bytes, default external ID | Returns extracted transactions list, ending balance minor, and detected IBAN or account number | Handles both Turkish and English column headers; returns empty list on format mismatch |
| `connectors/file_import/detect.py` | `parse_statement(content: str | bytes, default_account_id: str) -> tuple[FileFormat, list[RawTransaction]]` | Raw bytes or string content | Detected format and parsed raw transaction list | Dispatches to deterministic PDF parsers first, falling back to local Ollama when unknown |
| `db/database.py` | `create_manual_account(conn, account_dict: dict, initial_balance_minor: int | None = None) -> int` | Connection, account properties, optional balance minor | Returns new integer account ID | Atomic execution in `with conn:`; creates initial snapshot when balance provided |

**Value sourcing**:

| Action | Value produced / displayed | Source |
|---|---|---|
| Manual Account Dialog | Account fields (Name, Institution, Asset Class, Currency) | User form inputs in modal dialog |
| Initial Account Balance | Starting `account_snapshots` row | User initial balance number input converted to integer minor units |
| PDF Statement Parsing | Raw transaction dates, descriptions, amounts | Extracted from table text via `pypdf` in `isbank_pdf.py` or Ollama JSON schema in `parse_statement_with_llm` |
| Statement Target Account | Selected `account_id` | Auto matched by detected IBAN/institution or explicitly chosen by user selectbox |
| Ending Statement Balance | Account balance snapshot | Extracted from statement header or footer (Bakiye / Balance / Eindsaldo) with user confirmation |

**Key invariants**:
- Privacy first: Statement files and extracted data are processed 100% locally on the device. Ollama runs locally without external cloud API calls.
- Ledger integrity: Amounts are stored as exact integers in minor units (cents / kuruş).
- Idempotency: All imported transactions are deduplicated via `normalization.dedup_hash()` to prevent duplicate entries upon re-upload.

**Security and compliance**:
- Account numbers and balances are masked when `is_hidden()` is active.
- No third party network requests are triggered during statement parsing.

**Critical test scenarios**:
- Manual account creation with initial balance: verifies **AC-1**, **AC-2**
- Türkiye İş Bankası PDF parsing (Turkish and English headers): verifies **AC-3**
- Unrecognized PDF fallback to local Ollama: verifies **AC-4**
- Account auto matching and interactive selectbox confirmation: verifies **AC-5**
- Non EUR native currency storage and balance snapshot updates: verifies **AC-6**, **AC-7**

## Build plan

1. [x] Implement `create_manual_account` helper in `db/database.py`, satisfies **AC-2**
2. [x] Build `manual_account_dialog` in `ui/dialogs.py` and link button triggers in Settings and Import Files, satisfies **AC-1**, **AC-2**
3. [x] Implement `connectors/file_import/isbank_pdf.py` using `pypdf` with Turkish and English header support, satisfies **AC-3**
4. [x] Update `connectors/file_import/detect.py` to route PDF bytes to deterministic parsers with Ollama fallback, satisfies **AC-4**
5. [x] Upgrade `ui/pages/import_files.py` to provide target account selectbox and balance confirmation, satisfies **AC-5**, **AC-7**
6. [x] Ensure native currency preservation for non EUR imports without forced FX conversion, satisfies **AC-6**
7. [x] Write unit tests for manual account creation, İş Bankası PDF parsing, and target account resolution, satisfies **AC-1**, **AC-2**, **AC-3**, **AC-5**, **AC-6**

## Consequences

**Positive**:
- Users can track bank accounts from any country or institution without waiting for open banking API integrations.
- First class support for Turkish and English Türkiye İş Bankası PDF statements.
- Robust hybrid ingestion pipeline that handles both structured and unstructured statements locally.
- Explicit account confirmation eliminates accidental transaction assignment to wrong accounts.

**Negative**:
- PDF layouts that change radically may trigger LLM fallback, which takes a few seconds on local Ollama.
