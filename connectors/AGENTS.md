# Connectors Layer

## Overview

The connectors layer manages integrations with outside financial data providers and document parsers. It supports Open Banking synchronization, eToro portfolio extraction, Yahoo Finance market price updates, and local bank statement file parsing.

## Key files

| File | Owns |
|---|---|
| `connectors/base.py` | Shared base connector contract for accounts, balances, and sync operations |
| `connectors/enable_banking_service.py` | Enable Banking AISP client using JWT authorization and bank redirect sessions |
| `connectors/etoro_service.py` | eToro portfolio holdings, cash balance, copy trades, and transaction fetching |
| `connectors/market_data_service.py` | Real time stock quotes, exchange rates, and historical prices via Yahoo Finance |
| `connectors/file_import/` | Statement parsers (CAMT.053, MT940, CSV profiles, İş Bankası PDF) and auto format detection (`detect.py`) |

## Conventions

- Retrieve sensitive tokens and private keys exclusively via `services.secrets_vault.py` rather than plaintext files.
- Compute SHA256 deduplication hashes on transaction fields to ensure idempotent data imports.
- Convert foreign currency transactions into base euro minor units using current market exchange rates.

## Gotchas

- Network requests to external APIs must specify explicit timeouts to prevent UI hangs during background sync runs.
- PDF and MT940 parsing libraries may produce varied transaction descriptions depending on the originating bank; use normalization routines before persistence.

_Drafted by /audit from the repo, worth a quick human pass. Edit freely: once a line stops matching this draft, later runs treat it as curated and will flag rather than overwrite it._
