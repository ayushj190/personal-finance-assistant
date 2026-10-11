# Personal Finance Assistant

## Stack

- **Language / Runtime**: Python 3.11+
- **Framework**: Streamlit
- **Key dependencies**: SQLite3 (WAL mode), Ollama (local LLM), Plotly, Pandas, Cryptography, Keyring
- **Package manager**: pip (virtual environment in `.venv`)

## Build approach

<TBD, set by /scope>

## Commands

```bash
# Setup virtual environment and dependencies
install.ps1

# Run development server
run.bat
# Or run Streamlit directly
.\.venv\Scripts\streamlit.exe run app.py

# Run test suite
python run_tests.py
# Or run pytest directly
.\.venv\Scripts\pytest
```

## Specs

Stored in `docs/specs/`. Format: `docs/specs/NNNN-title.md`.

## Rules

- Local first privacy: financial ledgers remain in `data/finance.db`, credentials stay encrypted in `data/vault.bin` via Windows Credential Manager. No cloud telemetry.
- Currency representation: store money amounts in integer minor units (cents) within SQLite tables. Convert to float only at presentation boundaries.
- Database access: open connections via `db.database.connect()`. Always enforce WAL mode and foreign keys. Close connections cleanly.
- Streamlit lifecycle: keep session state updates deterministic. Background threads must use `add_script_run_ctx` and never access detached UI state.
- Safe execution: AI copilot executes read only SQL through a strict SQLite authorizer. Never permit write operations through the LLM.

## Agent skills

Declined: python-resource-management, sqlite-database-expert

## Context files

- [ui/AGENTS.md](ui/AGENTS.md): Streamlit UI architecture, custom theme CSS, fragments, and state handling
- [agent/AGENTS.md](agent/AGENTS.md): Local Ollama Copilot, tool dispatch, and read only database authorizer
- [db/AGENTS.md](db/AGENTS.md): SQLite schema, migrations, connection management, and table models
- [connectors/AGENTS.md](connectors/AGENTS.md): Banking APIs, eToro, market data, and statement file parsers
- [services/AGENTS.md](services/AGENTS.md): Tax calculation engines, mortgage amortization, and financial analytics

_Drafted by /audit from the repo, worth a quick human pass. Edit freely: once a line stops matching this draft, later runs treat it as curated and will flag rather than overwrite it._
