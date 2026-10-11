# Database Layer

## Overview

The database layer manages SQLite persistence for the personal finance assistant. It establishes WAL mode connections, runs startup schema migrations, seeds default category structures, and provides upsert functions for accounts, balances, and transactions.

## Key files

| File | Owns |
|---|---|
| `db/database.py` | Connection factory, migration steps, and data access routines |
| `db/schema.sql` | Core table definitions, constraints, default indexes, and foreign keys |
| `db/seed.sql` | Initial category hierarchy seeds for income, fixed, and discretionary expenses |
| `db/repository.py` | Additional query helpers and aggregate data retrieval methods |

## Conventions

- Store monetary values as integer minor units (cents) to avoid precision loss.
- Always acquire connections through `database.connect()` to guarantee WAL mode and active foreign keys.
- Use parameterized query bindings exclusively (`?` or named parameters) to prevent SQL syntax errors and injection risks.
- Ensure all connection instances are closed properly or managed using `with` context blocks.

## Gotchas

- SQLite connections must not be shared across threads; background jobs must instantiate their own connection.
- `database.migrate()` runs during application startup; ensure all schema mutations remain safe to execute repeatedly without duplicating rows or columns.

_Drafted by /audit from the repo, worth a quick human pass. Edit freely: once a line stops matching this draft, later runs treat it as curated and will flag rather than overwrite it._
