# 0018. Data product robustness upgrade

**Date**: 2026-10-13
**Status**: In Progress

## Summary

This upgrade turns the local finance app into a sturdier data product. It checks data coming in from the banks and eToro before it reaches the database, records every sync run and its health, encrypts sensitive counterparty details at rest, tightens the database migration runner, links every ledger row to where it came from, and redacts sensitive values from logs. The work is split into six child specs that share one small schema change and run in order, starting with a thin path through Enable Banking.

## Structure

An umbrella of six related decisions. Each child is a complete build spec on its own.

- [0018-ingestion-contracts.md](0018-ingestion-contracts.md): strict Pydantic validation of every PSD2 and eToro payload before storage, plus a quarantine for bad records. Supports the inbound data contract decision.
- [0018-connector-resilience-health.md](0018-connector-resilience-health.md): bounded retries with backoff, the `sync_run` and `connector_health` tables, and the offline and stale signal in Settings. Supports the resilience, offline first and synthetic SLA decision.
- [0018-database-durability.md](0018-database-durability.md): hardened migration runner (checksums, transactions, automatic backups, Python data migrations) and confirmed dedup keys. Supports the durability and idempotency decision.
- [0018-encryption-at-rest.md](0018-encryption-at-rest.md): field level Fernet encryption of counterparty identifiers, reusing the vault key, with a one time backfill. Supports the encryption at rest decision.
- [0018-lineage-observability.md](0018-lineage-observability.md): provenance and run link columns, redacted structured logging, and the zero leak context handling for the copilot. Supports the lineage and observability decision.
- [0018-memory-recycling.md](0018-memory-recycling.md): targeted garbage collection and release of large frame temporaries on heavy pages. Supports the memory decision. Deferred until resident memory is measured.

**Cross child contract** (holds for every child):

- **Validation is the only door.** No connector maps an unvalidated dictionary into a `Raw*` dataclass. Every write passes the Pydantic gate first.
- **Every ledger write is attributable.** A `transactions` or `holdings` write carries `provenance`, and, for connector runs, a `sync_run_id`.
- **Encryption covers identifiers only.** Amounts, dates, descriptions and merchant fields stay plaintext so sums, search and categorization keep working.
- **Migrations are forward only**, checksummed, transactional, backed up, and never wipe user data.
- **No sensitive value reaches a log line.** Amounts, IBANs and counterparty names are redacted by a logging filter.
- **Existing behavior is preserved.** Mock or demo mode, session state, credential management, and the copilot read only authorizer are unchanged.

## Requirements

**User stories**:

- As the owner, I want malformed bank or broker data stopped at the door, so a provider change can never corrupt my ledger.
- As the owner, I want every sync recorded with its health, so I can see when a provider is degrading or my data is stale.
- As the owner, I want sensitive counterparty details encrypted on disk, so a copied database file does not leak who I paid.
- As the owner, I want schema changes to be safe and reversible in effect, so I never lose years of history to a bad migration.
- As the owner, I want to know where each row came from, so I can trust and audit the ledger.
- As the owner, I want no amounts or names in my logs, and no prompt content written to disk, so privacy holds.
- As the owner, I want the app to stay usable offline on cached data, so a provider outage does not stop me.

**Acceptance criteria** (umbrella level, each checkable):

- **AC-1**: No existing feature regresses. Mock or demo mode, session state keys, credential management, the copilot read only SQL authorizer, and the whole existing test suite still pass.
- **AC-2**: All schema changes ship as forward only migrations; running the app against an existing `data/finance.db` preserves every existing row, and a pre migrate backup is written first.
- **AC-3**: Every new ingestion path passes the validation gate, and every transaction and holding write carries a provenance value (and a `sync_run_id` for connector runs).
- **AC-4**: No amount, IBAN or counterparty name appears in any plaintext log line, verified by a test that feeds a known value through the logger and asserts it is absent.
- **AC-5**: With the network unavailable, every page renders from the last synced local data and no page raises; the Settings health panel shows the stale or error state.

## Decision

**Chosen option**: Option 2, harden in place along shared seams, delivered as six child specs, built in dependency order, with a thin Enable Banking thread through every new seam first (the project's Tracer Bullet default).

We keep the existing stack (Python, SQLite via `sqlite3`, Streamlit, Ollama) and add the smallest pieces that close the gaps: Pydantic v2 as the validation gate, field level Fernet for identifiers reusing the vault key, a checksummed and transactional migration runner with automatic backups, two new tables plus a quarantine table, provenance columns, and a logging redaction filter. We reject a whole database encryption engine and a migration framework rewrite because both would break the vector vault and the raw `sqlite3` data layer for no proportionate gain.

**Implementation skills**: none yet. Any skills found for this stack are recorded in Follow-up until `/sync` captures them.

## Feature design

**Data model** (the shared schema change; children reference it):

New tables:

- `sync_run`: one row per (connector, account). `id` INTEGER primary key, `connector` TEXT not null, `account_id` INTEGER null references `accounts(id)` (null for account less connectors such as market data), `started_at` TEXT not null, `finished_at` TEXT null, `status` TEXT not null check in (`running`, `ok`, `partial`, `error`, `needs_reauth`), `records_fetched` INTEGER not null default 0, `records_inserted` INTEGER not null default 0, `records_rejected` INTEGER not null default 0, `error_message` TEXT null (redacted). Timestamps are UTC ISO 8601. Index on (`connector`, `started_at`).
- `connector_health`: one row per logical endpoint call. `id` INTEGER primary key, `sync_run_id` INTEGER not null references `sync_run(id)`, `connector` TEXT not null, `endpoint` TEXT not null, `ok` INTEGER not null, `latency_ms` INTEGER null (successful calls only), `http_status` INTEGER null, `schema_match` INTEGER null (null when no body arrived), `attempts` INTEGER not null default 1, `checked_at` TEXT not null. Index on (`connector`, `checked_at`).
- `ingest_rejection`: `id` INTEGER primary key, `sync_run_id` INTEGER not null references `sync_run(id)`, `connector` TEXT not null, `account_id` INTEGER null references `accounts(id)`, `record_key` TEXT not null, `error_fields` TEXT not null (field paths and error types, never input values), `error` TEXT not null, `created_at` TEXT not null. Unique on (`connector`, `account_id`, `record_key`) so a repeat rejection upserts instead of growing the table; retention 90 days.
- `schema_version` (the existing table, extended): add a `checksum` TEXT column. One row per applied migration with `version`, `checksum`, `applied_at`. We keep the existing table name rather than renaming it, so rollback stays simple.

Changed tables (SQLite allows adding a nullable `REFERENCES` column with a null default):

- `transactions`: add `provenance` TEXT null, `source_file` TEXT null, `sync_run_id` INTEGER null references `sync_run(id)`, `counterparty_iban_enc` TEXT null, `counterparty_name_enc` TEXT null. `imported_at` already is the ingestion timestamp, so no new column is added.
- `holdings`: add `provenance` TEXT null, `sync_run_id` INTEGER null references `sync_run(id)`.

The plaintext `counterparty_iban` and `counterparty_name` columns stay in the schema (nullable) but are set to null once the backfill encrypts them; the pre migrate backups that still hold plaintext fall under the retention rule and are the recovery point for that step.

**API surface** (internal seams, not HTTP endpoints):

| Seam | Where | Key inputs | Key outputs | Auth | Key errors |
|---|---|---|---|---|---|
| `validate_payload` | `connectors/schemas.py` | raw dict, model type | validated model or list of field errors | local | `ValidationError` |
| `with_retry` | `connectors/retry.py` | callable, attempts, base delay | response or last error | local | raises after attempts |
| `record_sync_run` | `services/sync_service.py` | connector, account, counts, status | `sync_run.id` | local | db error |
| `record_health` | `services/sync_service.py` | run id, endpoint, ok, latency, http status, schema match, attempts | `connector_health.id` | local | db error |
| `encrypt_field` / `decrypt_field` | `services/crypto.py` | plaintext / token | token / plaintext | local | key missing |
| health panel | `ui/pages/settings.py` | read `sync_run`, `connector_health` | per connector status, age, latency, schema match | local user | none |

**Value sourcing** (every produced value names its source):

| Action | Value produced / displayed | Source |
|---|---|---|
| Sync run | `status` | derived from run outcome, with precedence `needs_reauth` > `error` > `partial` > `ok`; all records rejected with none inserted is `error`; a mid run 401 or 403 keeps the counts already persisted |
| Sync run | `records_fetched` / `records_inserted` / `records_rejected` | fetched is raw records received; inserted is rows actually inserted (`ON CONFLICT` no ops are not counted); rejected is the rejection count |
| Endpoint call | `schema_match` | result of Pydantic `model_validate` for that payload (null when no body arrived); a missing envelope key is a mismatch |
| Endpoint call | `latency_ms`, `attempts` | wall time of the final attempt; attempt count for the logical call |
| Health panel | stale flag | `now` minus the last `ok` or `partial` `sync_run.started_at` (worst account), compared to `PFA_SYNC_STALE_HOURS`; "never synced" when there is no run |
| Health panel | average latency, schema match rate | aggregate over `connector_health` for the last 50 calls or 7 days |
| Transactions page | counterparty name and IBAN | `decrypt_field` of `*_enc` columns, key from `services/secrets_vault.py`; on failure `None` plus a `counterparty_unavailable` flag, never an empty string |
| Any ledger row | `provenance` | a constant from one provenance module (`psd2_api`, `etoro_portfolio`, `csv_import`, `manual`, `demo`, `legacy`) |
| Log line | safe record | `logging_setup` redaction filter output |

**State transitions**: `sync_run.status` is `running` on insert, then finishes `ok`, `partial`, `error` or `needs_reauth`, with precedence `needs_reauth` > `error` > `partial` > `ok`. `needs_reauth` is terminal for that run and tells the user to reconnect credentials. Only one run per (connector, account) may be active at a time, and any run left `running` past 15 minutes is swept to `error` with an interrupted message at startup.

**Key invariants**:

- No unvalidated dictionary reaches the storage layer.
- Every persisted transaction and holding has a `provenance`; connector runs also carry `sync_run_id`. Rows written before this upgrade are backfilled to `legacy`.
- One repository writer owns `transactions` and always writes `*_enc`; no path writes counterparty plaintext after the backfill.
- Amounts, dates, descriptions and merchant fields are never encrypted, so sums, search and categorization keep working.
- Migrations are forward only, checksummed, transactional and backed up; the recovery path is the pre migrate backup.
- No amount, IBAN or counterparty name is ever written to a log.

**Security model**: single local user, no account roles. The copilot read only authorizer is unchanged. The encryption key stays in Windows Credential Manager behind the existing vault. The database file itself stays plaintext, so the OS disk encryption remains the outer layer; field encryption shrinks the blast radius of a copied `finance.db`. Logs are redacted.

**Configuration required**:

- `PFA_ALLOW_MIGRATION_DRIFT`: set to `1` to bypass the checksum guard when an applied migration file changed on disk (default off).
- `PFA_LOG_FORMAT`: `json` for structured lines, otherwise text (default text).
- `PFA_BACKUP_KEEP`: number of pre migrate backups to retain (default 5).
- `PFA_SYNC_STALE_HOURS`: age after which a connector is marked stale (default 24).
- `PFA_HEALTH_RETENTION_DAYS`: retention for `sync_run`, `connector_health` and `ingest_rejection` (default 90).
- `PFA_RUN_BUDGET_SECONDS`: total wall time budget for one sync run across all retries and pages (default 120).

**Critical test scenarios** (each maps to an acceptance criterion above):

- Happy path: a full Enable Banking sync on demo data validates, persists with provenance and a run link, and the health panel shows it green, verifies **AC-3**, **AC-5**
- Failure case: one record arrives with a non numeric amount; it lands in `ingest_rejection`, the run status is `partial`, and every other record persists, verifies **AC-3**
- Failure case: the provider times out; retries exhaust, the run is `error`, and the app keeps rendering from local data, verifies **AC-5**
- Security: a transaction with a known IBAN is logged; the IBAN is absent from the log output, verifies **AC-4**
- Data safety: migrating an existing populated database preserves the row count and writes a backup first, verifies **AC-2**
- Security: after any ingest path (connector, file import, manual edit, demo seed) the plaintext counterparty columns are null and the ciphertext decrypts back, verifies **AC-3**
- Regression: the existing suite plus the all pages demo smoke test pass, verifies **AC-1**

## Build plan

Tracer Bullet: stand one thin thread through every new seam on a single connector first, then widen it. Each step runs `python run_tests.py` and is committed on its own.

1. Harden the migration runner first (checksums on the existing `schema_version`, one transaction per migration, the automatic backup, Python data migrations), so every later step runs on a protected runner. Satisfies `database-durability` AC-1 to AC-4.
2. Thin Enable Banking tracer end to end: add `connectors/schemas.py` with the PSD2 models, wire the validation gate and the `ingest_rejection` quarantine, add the `sync_run` and `connector_health` tables and their writes, add `connectors/retry.py` with backoff, add the provenance and `sync_run_id` columns, and add the Settings health panel. Satisfies `ingestion-contracts` AC-1 to AC-4, `connector-resilience-health` AC-1 to AC-4, `lineage-observability` AC-1.
3. Add `services/crypto.py`, the counterparty encryption backfill as a Python data migration, and the single repository writer that writes `*_enc` and decrypts on read. Satisfies `encryption-at-rest` AC-1 to AC-9.
4. Widen the tracer to eToro, market data and file imports: route each through the validation gate, retries, `sync_run` and provenance, and confirm each ingest path leaves plaintext null. Satisfies `ingestion-contracts` AC-1 to AC-5, `connector-resilience-health` AC-5, **AC-3**.
5. Add the logging redaction filter, the optional JSON formatter, and the copilot context handling. Satisfies `lineage-observability` AC-2 to AC-5, **AC-4**.
6. Confirm the offline and stale path on all pages, and run the full regression on the demo database. Satisfies **AC-1**, **AC-5**.

Deferred: the memory recycling child (`memory-recycling`), until resident memory is measured and shows a real ceiling. See Follow-up.

## Migration plan

**Strategy**: strangler per seam. New validation, health and encryption paths run alongside the old ones, callers move one connector at a time, and the old direct ingest path is deleted last (step 4).

**Phases**:

1. Harden the runner (checksums, one transaction per migration, the backup, Python data migrations), before any schema or data change.
2. Add nullable columns and the three new tables (forward only, no data touched).
3. Run the encryption backfill as a recorded, idempotent data migration, with `secure_delete` on, then a WAL checkpoint and a `VACUUM` after.
4. Widen connectors and remove the old ingest path.

**Rollback**: code is rolled back per step with `git revert`; data is rolled back by restoring the pre migrate backup (a git revert does not restore data). The encryption backfill is the one irreversible data step, so the backup written just before it is the recovery point, and the migration aborts and is not recorded if the vault key is unavailable.

**Risks**: the vector vault (`sqlite-vec`) must keep working, which is why we do not swap SQLite for SQLCipher. The encryption backfill can lose data if it nulls plaintext before the ciphertext is confirmed, so it writes ciphertext first, verifies, then nulls. PostgreSQL style online migrations are unnecessary here because it is a single local writer.

## Consequences

**Positive**:

- A provider payload change can no longer corrupt the ledger; bad records are quarantined and visible.
- Every sync is measured, so degradation and staleness are visible instead of silent.
- Copied database files no longer expose counterparty identities.
- Schema changes cannot silently wipe history, and every row is attributable.

**Negative / tradeoffs**:

- New ceremony at the connector boundary (a schema per payload) that must be maintained when a provider changes shape.
- Field level encryption means counterparty fields are no longer searchable in SQL; only description and merchant stay searchable, and any equality match on an IBAN needs an HMAC blind index column.
- The encryption backfill is irreversible for the data it touches; the pre migrate backup is the only recovery point.
- The plan touches many files, and the existing test suite is the main safety net.

**Neutral**:

- One small schema change applied as forward only migrations.
- `data/backups/` must be gitignored; the backups hold plaintext counterparty values until the retention rule ages them out.
- `sync_run`, `connector_health` and `ingest_rejection` are pruned on the `PFA_HEALTH_RETENTION_DAYS` schedule.
- The memory child is deferred until resident memory is measured.
- No new hosted services; everything stays local.

## Follow-up

- [ ] Enroll a scope feature for this work (none exists in `docs/scope/`); until then this spec is standalone and its build order lives here.
- [ ] Add `data/backups/` to `.gitignore`, and add `.gitattributes` with `*.sql text eol=lf` and `*.py text eol=lf` so the checksum guard is not tripped by Windows line endings.
- [ ] Memory recycling child deferred: measure resident memory first, and add `gc.collect()` only if a real ceiling is hit.
- [ ] Consider an HMAC blind index column if transfer matching or recurring detection needs IBAN equality after encryption.
- [ ] Decide the `sync_log` retirement once `sync_run` is the source of truth; keep the dual write, with `partial` mapped to `ok` and the message redacted, until then.
- [ ] Installed skills: `developing-with-streamlit` (relevant to the Settings panel) and, from `pydantic/skills`, `building-pydantic-ai-agents` plus three Logfire skills (weak fit; Logfire conflicts with the local first rule). No standalone Pydantic model validation skill exists in that repo.
- [ ] MCP: consider connecting `streamlit-mcp` (headless UI checks) and a read only SQLite MCP. Both are user config steps; codegraph is already connected.
- [ ] `/sync` after done: record the validation gate, provenance, encryption and redacted logging conventions in root and area `AGENTS.md`.
- [ ] Optional later: a repair action to re replay quarantined records once a provider fix lands, and a purge action for plaintext backups.

## Rationale

Reasoning, options considered and the codebase inventory: see [rationale.md](rationale.md).
