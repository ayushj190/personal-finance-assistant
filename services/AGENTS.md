# Services Layer

## Overview

The services layer contains the core financial computation engines and business logic. It handles Dutch tax optimization (Box 1, Box 3, Jaarruimte pension room, Groenfondsen), mortgage amortization, transaction categorization, RAG retrieval, and encrypted credential storage.

## Key files

| File | Owns |
|---|---|
| `services/tax_optimizer.py` | Dutch fiscal math for Jaarruimte, Box 3 asset taxes, and green investment arbitrage |
| `services/mortgage.py` | Amortization tables, interest tax deductions (HRA), and early prepayment savings |
| `services/analytics.py` | Aggregates liquid cash, investment portfolios, and real estate equity for net worth metrics |
| `services/categorization.py` | Rule based and merchant pattern classification for raw transaction descriptions |
| `services/rag_service.py` | Vector search and text chunk retrieval over Dutch tax guides and financial laws |
| `services/secrets_vault.py` | Fernet encryption for API keys backed by Windows Credential Manager via keyring |
| `services/sync_service.py` | Coordination of background sync tasks across active banking and broker connectors |

## Conventions

- Domain calculation functions must remain decoupled from Streamlit UI elements and session state.
- Keep tax formulas and parameter constants aligned with verified Dutch Belastingdienst rules.
- Store and retrieve sensitive credentials using `secrets_vault.py` rather than configuration files.

## Gotchas

- Dutch tax thresholds (Box 3 exemptions, Jaarruimte formulas) update each fiscal year; ensure routines specify the active tax year.
- Large transaction imports should be processed in batches inside database transaction blocks to prevent locks.

_Drafted by /audit from the repo, worth a quick human pass. Edit freely: once a line stops matching this draft, later runs treat it as curated and will flag rather than overwrite it._
