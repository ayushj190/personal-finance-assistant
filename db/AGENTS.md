# Database Layer

## Overview

The database layer manages SQLite persistence for the personal finance assistant. It establishes WAL mode connections, runs startup schema migrations, seeds default category structures, and provides upsert functions for accounts, balances, and transactions.

## Key files

| File | Owns |
|---|---|
| `db/database.py` | Connection factory, migration runner trigger, and data access routines |
| `db/models.py` | Typed dataclass models for accounts, transactions, holdings, and liabilities |
| `db/repositories/` | Dedicated repository classes for accounts, transactions, holdings, and liabilities |
| `db/migrations/` | Forward only migrations (`NNNN_name.sql` schema, `NNNN_name.py` data) and the hardened runner in `runner.py` (checksums, one transaction per migration, pre migrate backups) |
| `db/schema.sql` | Core table definitions, constraints, default indexes, and foreign keys |
| `db/seed.sql` | Initial category hierarchy seeds for income, fixed, and discretionary expenses |

## Conventions

- Store monetary values as integer minor units (cents) to avoid precision loss.
- Always acquire connections through `database.connect()` to guarantee WAL mode and active foreign keys.
- Use `database.connect_readonly()` with SQLite authorizer when read only query guarantees are required (e.g. AI Copilot tools).
- Use parameterized query bindings exclusively (`?` or named parameters) to prevent SQL syntax errors and injection risks.
- Ensure all connection instances are closed properly or managed using `with` context blocks.
- Track active and closed lifecycle status on holdings (`v_holdings` filters active only) and reconcile statement imports atomically.
- Migrations are forward only and append only: add a `NNNN_name.sql` (schema) or `NNNN_name.py` (Python data migration exposing `migrate(conn)`), never edit an applied file. The runner records a SHA256 over LF normalized bytes in `schema_version`, runs each migration inside one `BEGIN IMMEDIATE` transaction, and writes a verified backup to `data/backups/` before the first pending migration. A changed applied file stops startup unless `PFA_ALLOW_MIGRATION_DRIFT=1`; `PFA_BACKUP_KEEP` sets backup retention (default 5).

## Gotchas

- SQLite connections are initialized with check_same_thread=False for Streamlit dialog thread compatibility; background jobs must still instantiate their own connection.
- `database.migrate()` runs during application startup; ensure all schema mutations remain safe to execute repeatedly without duplicating rows or columns.
- A Python data migration must be safe to re-run (the runner records it, so a passing run never repeats) and must not run `VACUUM` or a WAL checkpoint inside the migration transaction; do those after it commits.

_Drafted by /audit from the repo, worth a quick human pass. Edit freely: once a line stops matching this draft, later runs treat it as curated and will flag rather than overwrite it._
