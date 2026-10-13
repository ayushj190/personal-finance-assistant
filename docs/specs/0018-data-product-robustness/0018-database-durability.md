# Database durability and idempotency

Part of umbrella spec [0018](index.md). Build spec for one decision.

## Summary

This child makes schema changes safe. The existing hand written migration runner gains a checksum per applied file (so an edited migration that already ran is caught), a transaction per migration (so a failure changes nothing), an automatic backup before the first pending migration, and support for Python data migrations that run in the same numbered sequence. Dedup stays a database guarantee and is confirmed across the newer tables.

## Requirements

**User stories**:

- As the owner, I want a bad or edited migration stopped before it touches data, so I never lose history.
- As the owner, I want a fresh backup taken automatically, so I always have a recovery point.

**Acceptance criteria**:

- **AC-1**: The runner records a SHA256 checksum for each applied file in the existing `schema_version` table (an added `checksum` column); the hash is over normalized (LF) line endings so Windows line ending changes do not trip it. On startup, if an already applied file's checksum has changed, the app shows an error page naming the file and refuses to run unless `PFA_ALLOW_MIGRATION_DRIFT=1` is set. Existing rows without a checksum are adopted trust on first use.
- **AC-2**: Each migration runs inside an explicit transaction (`isolation_level=None`, `BEGIN IMMEDIATE`, per statement execution, since `executescript` auto commits); a failure leaves the database unchanged and raises a clear error.
- **AC-3**: Before applying the first pending migration, the runner backs up the database with the `sqlite3` backup API or `VACUUM INTO` on a dedicated connection, verifies the copy with `PRAGMA integrity_check`, writes it to `data/backups/finance_<version>_<timestamp>.db`, retains the last `PFA_BACKUP_KEEP` (default 5), and aborts the migration if the backup fails (fail closed). It skips the backup on a fresh database.
- **AC-4**: The runner supports Python data migrations (`NNNN_name.py`) alongside SQL files, applied in number order and recorded with a checksum, so data transforms such as the encryption backfill are first class and idempotent by contract.
- **AC-5**: Transaction dedup remains a database guarantee: `UNIQUE(account_id, dedup_hash)` with `ON CONFLICT DO NOTHING`; re running the same sync window inserts zero duplicate rows (verified by a test).
- **AC-6**: Holdings (unique by account and ticker) and `market_quotes` (unique by ticker and quote date) are confirmed unique and idempotent under a repeated sync.
- **AC-7**: The runner locks with `BEGIN IMMEDIATE` and re checks the applied set inside the lock, so two concurrent startups cannot race it.

## Decision

**Chosen option**: harden the existing `sqlite3` migration runner in place; keep Alembic out.

**Implementation skills**: none yet.

## Design

**Data**: the existing `schema_version` table gains a `checksum` TEXT column (one row per applied migration: `version`, `checksum`, `applied_at`). We keep the existing table name rather than renaming it, so rollback stays simple and no bootstrap ordering problem arises.

**Surface**:

| Function | Where | Inputs | Outputs | Errors |
|---|---|---|---|---|
| `run_migrations` | `db/migrations/runner.py` | connection | applied versions | checksum drift, migration failure |
| `backup_database` | `db/migrations/runner.py` | db path, version | backup path | io error |
| `prune_backups` | `db/migrations/runner.py` | keep count | removed paths | none |

**Rules**:

- Checksum each file (SQL or Python) with SHA256 over normalized (LF) bytes before applying; store it on success. Add `.gitattributes` with `*.sql text eol=lf` and `*.py text eol=lf`.
- Use `isolation_level=None` with an explicit `BEGIN IMMEDIATE` and per statement execution; `executescript` auto commits and cannot be wrapped in a transaction.
- Back up with the `sqlite3` `Connection.backup()` API or `VACUUM INTO` on a dedicated connection (never "close writers first", which is not reachable in Streamlit), verify with `PRAGMA integrity_check`, and fail closed if the backup fails.
- Acquire the migration lock with `BEGIN IMMEDIATE` and re check the applied set inside it.
- Adopt existing applied rows trust on first use: compute and store their checksum from the current file.
- Python data migrations receive a connection and must be safe to run again; the runner records them so a passing run never repeats.
- Never add a `NOT NULL` column without a default in a running system; the shared model only adds nullable columns.
- Assign migration numbers at build time (next free number for the schema SQL, the following for the Python backfill); duplicate numbers are rejected.

**Value sourcing**: the backup path uses the current highest applied version and a timestamp; the checksum comes from the normalized file bytes; the retention count is `PFA_BACKUP_KEEP`.

**Invariants**: a migration either fully applies and is recorded, or leaves the database untouched; an applied file is never silently changed; the backup is written before any data migration runs.

## Build plan

1. Add the `checksum` column to `schema_version`, the checksum writing with normalized line endings, the drift guard plus error page, and the `.gitattributes` rule. Satisfies **AC-1**
2. Run each migration in an explicit transaction. Satisfies **AC-2**
3. Add the pre migrate backup (functional backup API, integrity check, fail closed) and pruning. Satisfies **AC-3**
4. Add Python data migration support and the build time numbering rule. Satisfies **AC-4**
5. Add the `BEGIN IMMEDIATE` startup lock and the in lock re check. Satisfies **AC-7**
6. Confirm and test the transaction dedup key and the holdings and quotes keys. Satisfies **AC-5**, **AC-6**

## Consequences

**Positive**: schema changes cannot silently wipe history; edited migrations are caught; every migrate has a recovery point.

**Negative / tradeoffs**: a backup on a large database adds a brief pause at startup when migrations are pending; Python data migrations add a second file type to learn; the irreversible encryption backfill's only recovery is the pre migrate backup, so that backup must not be pruned away before the backfill is verified.

**Neutral**: the `schema_version` table keeps its name and gains a `checksum` column; existing version rows are adopted trust on first use.

## Follow-up

- [ ] Optional later: a `--check-only` migrate flag that reports pending migrations without applying them.
