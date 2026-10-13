# Verify: Data Product Robustness · spec 0018 · updated 2026-10-13
_Steps derived from spec 0018 acceptance criteria. `/check verify` runs these; `/test` locks the durable ones. This file currently covers the first built slice, the hardened migration runner (child `0018-database-durability`, AC-1 to AC-7, umbrella AC-2). Later children append their own steps here._

## UI / manual
- [ ] Edit an already applied file in `db/migrations/` (add a comment to `0006_holdings_realized_pnl.sql`), start the app with `run.bat` → an error page names the changed file and the app does not run → AC-1
- [ ] Set `PFA_ALLOW_MIGRATION_DRIFT=1` and start again → the app starts and logs past the drift → AC-1
- [ ] Copy `data/finance.db`, drop a new migration file into `db/migrations/`, start the app against the copy → a `data/backups/finance_<version>_<timestamp>.db` appears before the migration applies, and every pre existing row count is unchanged → AC-3, umbrella AC-2

## Commands
- [ ] `.\.venv\Scripts\pytest.exe tests/test_migration_runner.py -q` → 13 passed → AC-1 to AC-7
- [ ] `.\.venv\Scripts\pytest.exe -q` → 273 passed (no regression) → umbrella AC-1
- [ ] `.\.venv\Scripts\python.exe -c "from db.database import migrate; migrate(); print('ok')"` twice against `data/finance.db` → both print `ok`, no backup on the second run (nothing pending) → AC-1, AC-3
- [ ] Confirm the retained backups: `PFA_BACKUP_KEEP=2`, force two pending migrations, check `data/backups/` keeps only the newest 2 → AC-3
- [ ] Confirm a fresh database writes no backup: migrate an empty temp path → no `backups/` directory is created → AC-3
- [ ] Confirm a failing migration leaves the database untouched: run a migration with one bad statement → error raised, no partial table, `schema_version` has no row for it → AC-2

## Acceptance-criteria coverage
- AC-1 (checksum + drift guard) → covered by the drift manual steps and `test_drift_detected_then_override`, `test_checksum_recorded_and_idempotent`, `test_legacy_row_adopted_trust_on_first_use`
- AC-2 (transaction per migration) → `test_failed_migration_rolls_back`
- AC-3 (pre migrate backup, integrity check, retention, fresh skip) → `test_backup_written_before_pending_migration`, `test_prune_backups_keeps_newest`, `test_fresh_database_skips_backup`, `test_backup_database_direct`
- AC-4 (Python data migrations) → `test_python_data_migration_runs_once`, `test_python_migration_without_migrate_is_rejected`
- AC-5 (transaction dedup) → `test_repeated_sync_inserts_no_duplicate_transactions`
- AC-6 (holdings and quotes idempotent) → `test_repeated_sync_holdings_and_quotes_idempotent`
- AC-7 (startup lock, in lock re check) → `run_migrations` uses `BEGIN IMMEDIATE` and re reads the applied set inside the lock; `test_checksum_recorded_and_idempotent` confirms a second run applies nothing
- umbrella AC-1 (no regression) → full suite run
- umbrella AC-2 (existing rows preserved, backup first) → backup manual step
