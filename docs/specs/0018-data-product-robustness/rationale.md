# 0018. Data product robustness upgrade · reasoning

Decision record for [index.md](index.md). A build does not need this file.

## Context

The app is a personal, local first finance assistant. It pulls accounts and transactions from Enable Banking (PSD2, via JWT and bank redirect sessions) and portfolios from eToro, parses bank statements, stores everything in SQLite, and analyzes it on screen and through a local Ollama copilot. It has grown to roughly 22 thousand lines and about 126 Python files across `connectors/`, `db/`, `services/`, `agent/` and `ui/`.

The forces at play:

- **Third party shapes change without notice.** PSD2 and eToro are outside our control. Today the connectors parse raw JSON with `.get()` chains and `@dataclass(frozen=True)` carriers that do no validation, so a missing field silently becomes a default and a wrong type can reach storage. There is no gate.
- **Some pillars already exist and must be reused, not rebuilt.** Dedup is already a SHA256 `dedup_hash` with `UNIQUE(account_id, dedup_hash)` and `ON CONFLICT DO NOTHING`. Migrations already run through a hand written `NNNN_name.sql` runner with a `schema_version` table. Logging already exists as stdlib `logging` with a rotating file at `data/logs/app.log` (spec 0014). Lineage already has `source`, `external_ref` and `imported_at`. Spec 0014 also owns the `Money` type and the logging setup, and is in progress.
- **Security posture.** The database file is plaintext; Fernet is used only for the credential vault. Windows Credential Manager holds the vault key. The copilot already runs read only SQL behind an authorizer, and chat history already lives in memory only, never on disk.
- **Local only, single user.** No multi tenancy, no server. Every choice must survive a copied database file and a provider outage, without adding hosted infrastructure.

The cost of not deciding: provider drift corrupts the ledger silently, a database copy leaks who the owner paid, a bad migration could wipe years of history, and there is no way to see why a sync failed or where a row came from.

> ⚠️ Premise note: the brief bundles eight concerns, which is really six independently buildable decisions, so this is written as an umbrella with six child specs rather than one sprawling file. Two of the original eight concerns ("offline first" and "synthetic SLAs") collapse into one child (connector resilience and health), and "zero leak context" folds into the lineage and observability child, because each pair shares its data and code.

> ⚠️ Premise note: the brief asked for SQLCipher full database encryption. That would replace the `sqlite3` engine with a compiled variant and risk breaking `sqlite-vec`, which backs the Dutch law vector vault. For a single user local file, field level encryption of the identifiers (with OS disk encryption as the outer layer) closes the realistic exposure at far lower breakage risk. The engineer agreed.

## Options considered

### Validation: Pydantic v2 (chosen)

Typed models parsed at the connector boundary, mapping into the existing frozen `Raw*` dataclasses so the rest of the pipeline is unchanged.

**Pros**: clear per field errors, type coercion with strict mode, the de facto Python standard, one dependency, fits the raw dicts the connectors already produce.

**Cons**: one new dependency; a schema per payload must be maintained as providers change.

### Validation: Pandera

Schema validation for pandas DataFrames.

**Pros**: strong for tabular frames and statistical checks.

**Cons**: the payloads are JSON dicts, not frames; would force an early conversion and validate the wrong layer.

### Validation: stdlib dataclass checks

Guards inside the existing dataclasses.

**Pros**: no new dependency.

**Cons**: hand written, weak on coercion, no field path in errors, easy to leave a hole.

### Encryption: field level Fernet, reuse vault key (chosen)

Encrypt `counterparty_iban` and `counterparty_name` into `*_enc` columns using the existing `cryptography` Fernet key from the vault.

**Pros**: reuses a dependency and a key the app already manages; no native build; `sqlite-vec` and the data layer are untouched; amounts stay queryable.

**Cons**: encrypted fields are no longer searchable in SQL; a key loss makes those fields unreadable; needs a one time backfill.

### Encryption: SQLCipher full database

Encrypt the whole `finance.db`.

**Pros**: strongest at rest; nothing else changes conceptually.

**Cons**: needs a compiled SQLite that typically breaks `sqlite-vec` and the raw `sqlite3` connections; large blast radius for a single user local file.

### Encryption: both

**Pros**: belt and braces.

**Cons**: the most work and the highest breakage risk against the vector vault.

### Migrations: harden the existing SQL runner (chosen)

Keep the hand written runner, add checksums, a transaction per migration, an automatic backup and Python data migrations.

**Pros**: preserves the raw `sqlite3` design; small, understandable change; keeps spec 0001 and 0014 work intact.

**Cons**: not a mature framework; no automatic downgrade; correctness of each migration is still on the author.

### Migrations: Alembic

**Pros**: mature, downgrades, a known workflow.

**Cons**: needs SQLAlchemy and a rewrite of the data access layer, which the project deliberately avoids.

### Lineage depth

- **Runs, health and back links (chosen)**: `sync_run` and `connector_health` tables plus provenance, `source_file` and `sync_run_id`.
- **Back link columns only**: simpler, but no run history or health.
- **Full with raw payload replay**: strongest for debugging, but keeps raw provider payloads (with PII) on disk, which fights the privacy goal.

### Memory

- **gc plus cache caps (offered)**: rakes memory but risks recomputation churn.
- **Targeted gc only (chosen, then deferred)**: `gc.collect()` at page switches and heavy fragments, plus releasing large frame temporaries. Least risk for the real symptom (frame bloat on page switches), but deferred until resident memory is measured, because the AC-3 object count test is a weak proxy.

### Redaction

- **Redaction filter plus context purge (chosen)**: a logging filter masks amounts, IBANs and names; copilot history clears when values are hidden or on Clear chat.
- **Redaction only**: keeps chat across views but leaves context in memory longer.

## Rationale

The decision is shaped by three forces from Context. First, the project already solved several pillars (dedup, a migration runner, logging, partial lineage), so the correct move is to harden along those existing seams rather than introduce parallel machinery; this is the strangler instinct applied to a single owner local system where the only real risk is data loss. Second, `sqlite-vec` and the raw `sqlite3` data layer are load bearing, so anything that replaces the engine (SQLCipher, SQLAlchemy) is rejected on blast radius. Third, privacy for a copied file is won by encrypting the smallest high value set (counterparty identifiers) while keeping the fields the app queries (amounts, dates, descriptions, merchants) intact, which is the only version that does not break sums, search and categorization.

Pydantic v2 wins because the boundary is exactly where dicts are parsed today, so the gate slots in with the least movement and gives the clearest errors, which the quarantine and the health panel both consume. Hardening the existing runner wins because the runner already works and only lacks guardrails; an Alembic migration would drag SQLAlchemy into a stack that deliberately avoids it. The lineage and health tables are the smallest set that answers "what ran, did it match, and where did this row come from", and keeping raw payloads out of the store honors the privacy goal that the whole upgrade serves.

## Cross check resolutions

An independent model reviewed the spec and found load bearing gaps, all folded in:

- Encryption was the weak spot: a create disabled key resolver with a fingerprint, a backfill that aborts unrecorded without the key, a `None` plus `counterparty_unavailable` read fallback, `secure_delete` plus a checkpoint and a `VACUUM` to clear plaintext residue, a single writer that always writes `*_enc`, and an HMAC blind index if an equality match is needed.
- Ingestion: PSD2 amounts arrive as decimal strings, so the schema accepts a decimal string and rejects a float or non numeric; `extra="ignore"`; `hide_input_in_errors=True` so the quarantine cannot re leak a value; a `record_key` so repeat rejections upsert.
- Resilience: one run per (connector, account), status precedence, freshness from the last `ok` or `partial` run, a redacted `sync_log` dual write, an `attempts` column, `Retry-After`, a run budget, and retention.
- Durability: hash normalized line endings, adopt existing rows trust on first use, an explicit transaction (`executescript` auto commits), a functional backup with an integrity check that fails closed, a startup lock, and keeping the `schema_version` name instead of renaming it.
- Logging: redact after `getMessage()`, clear args, scrub `exc_text`, add bearer and JWT patterns, attach to the console, and pass sensitive values only through `extra=`.

Soundness changes: the runner hardening moved before the tracer, and the memory child moved to deferred until resident memory is measured. Merging the ingestion child into the resilience child was considered and declined, since the two stay readable on their own and the build plan already runs them as one tracer step.

## Evidence: current codebase inventory

Taken during the design pass (file and line references are from that pass).

**Inbound validation**: none. No pydantic, marshmallow, cerberus or jsonschema anywhere. Raw JSON parsed inline in `connectors/enable_banking_service.py` and `connectors/etoro_service.py` with `.get()` chains. `RawAccount`/`RawTransaction`/`RawHolding` in `connectors/base.py` are frozen dataclasses with no `__post_init__`.

**Dedup**: `services/normalization.py` `dedup_hash()` (SHA256 over `external_ref` or `booking_date|amount_minor|currency|clean_merchant|occurrence_idx`), computed in `services/sync_service.py`, enforced by `UNIQUE(account_id, dedup_hash)` in `db/schema.sql` with `ON CONFLICT DO NOTHING`.

**Migrations**: hand written `db/migrations/runner.py` scanning `NNNN_name.sql`, recording versions in `schema_version`. Six migrations exist. No checksums, no transaction wrapping, no backup, no down path.

**Offline first**: `services/sync_service.py` writes to SQLite in a background thread via `services/task_coordinator.py`; the UI reads independently. Failures are caught per connector and written to `sync_log` (`ok`/`error`/`needs_reauth`). No staleness signal in the UI; no retry or backoff.

**Encryption**: `finance.db` plaintext. Fernet only for `data/vault.bin` via `services/secrets_vault.py`, key in Windows Credential Manager with a `.vault_master.key` fallback.

**Zero leak**: prompts assembled in `agent/copilot.py`; model calls in `services/llm_client.py`; prompts are not logged; chat history in `st.session_state` only; no temp files.

**Memory**: no `gc.collect()`. Streamlit caches use TTLs (300s, 60s, 3600s) with no size caps; no explicit frame release on page or account switch.

**Lineage and logs**: `transactions` has `source`, `external_ref`, `imported_at`, `dedup_hash`; no `sync_run` link. Holdings have only `updated_at`. Logging is stdlib `logging` with a `RotatingFileHandler` (1 MB, 3 backups) at `data/logs/app.log` (spec 0014). eToro logs raw exception messages; `sync_service` writes `str(e)` into `sync_log.message`; no redaction.

**Related specs**: 0001 (layered architecture and migration runner), 0014 (money, logging, demo mode, in progress), 0013 (hybrid ingestion, statement parsers), 0007 (copilot read only authorizer).
