# 0001. Modular Data Pipeline & UI Component Decoupling

**Date**: 2026-10-11
**Status**: Accepted

## Summary

This architecture specification reorganizes the personal finance assistant into a layered monolith separating presentation, domain services, and database persistence. It replaces direct database calls and raw SQL queries inside Streamlit pages with typed repository models, splits the oversized monolithic theme into clean design tokens and static CSS, isolates background sync and Copilot inference from Streamlit execution context, and introduces an incremental schema migration runner to eliminate startup overhead.

## Requirements

**User stories**:
- As a user, I want the dashboard and portfolio pages to load instantly and predictably without erratic rerun loops or layout glitches.
- As a developer, I want a clean separation between data access, business calculations, and Streamlit presentation so that features can be modified, tested, and extended without regressions.
- As a user, I want background bank synchronization and Copilot queries to execute smoothly without freezing UI controls or conflicting with active filters.

**Acceptance criteria**:
- **AC-1**: All database reads and writes for core entities (Accounts, Transactions, Holdings, Liabilities) execute through dedicated repository classes in `db/repositories/` returning typed dataclass objects. No raw SQL queries remain inside `ui/pages/`.
- **AC-2**: Database schema migrations execute strictly via an incremental versioned migration runner in `db/migrations/`, checking a persistent `schema_version` table and executing pending changes only once.
- **AC-3**: The styling system is modularized into `ui/theme/palette.py` (design tokens), `ui/theme/custom.css` (static stylesheet loaded cleanly), and `ui/theme/charts.py` (standardized Plotly helpers), eliminating runtime monkey patching of `st.plotly_chart`.
- **AC-4**: Background tasks communicate with the Streamlit UI via a thread safe state coordinator, preventing detached thread context exceptions and eliminating rerun queue collisions.
- **AC-5**: All existing unit and integration tests (68 tests) continue to pass without regressions, augmented by unit tests covering the new repository classes.

## Decision

**Chosen option**: Option 1: Full Layered Monolith with Typed Repositories & Worker Coordination.

We adopt a clean layered monolith pattern separating the application into presentation (`ui/`), business services (`services/`), repository access (`db/repositories/`), and data storage (`db/`).

## Proposed stack

| Layer | Choice | Reason |
|---|---|---|
| Domain Models | Python Standard Library Dataclasses | Zero external dependencies, fast instantiation, and compile time type hints across codebase |
| Data Access | SQLite3 Repository Pattern in `db/repositories/` | Centralizes query logic, isolates schema changes, and enforces WAL transaction safety |
| Migration Runner | Versioned SQL Runner (`db/migrations/*.sql`) | Idempotent migration execution with schema version tracking, eliminating startup lag |
| UI Styling | Modular CSS (`ui/theme/`) + Explicit Chart Wrapper | Replaces monkey patching with deterministic `render_chart` helper and external static CSS |
| Async Coordination | Thread Safe Task Coordinator (`services/task_coordinator.py`) | Bridges background threads and Streamlit fragments cleanly without detached context errors |

## Build plan

- [x] 1. Create domain entity dataclasses (`Account`, `Transaction`, `Holding`, `Liability`, `TaxProfile`) in `db/models.py`, satisfying **AC-1**.
- [x] 2. Implement repository classes (`AccountRepository`, `TransactionRepository`, `HoldingRepository`, `LiabilityRepository`) in `db/repositories/` wrapping database queries, satisfying **AC-1**.
- [x] 3. Create the versioned schema migration runner in `db/migrations/` and update `db/database.py` to run migrations only when `schema_version` is behind, satisfying **AC-2**.
- [x] 4. Modularize `ui/theme.py` into `ui/theme/tokens.py`, `ui/theme/styles.css`, and `ui/theme/charts.py`, removing monkey patching of `st.plotly_chart` in favor of an explicit chart helper, satisfying **AC-3**.
- [x] 5. Implement `services/task_coordinator.py` to isolate background worker threads from direct Streamlit session state access, satisfying **AC-4**.
- [x] 6. Refactor `ui/pages/dashboard.py` and `ui/pages/investments.py` to source data strictly through domain repositories and services, satisfying **AC-1** and **AC-3**.
- [x] 7. Run and update test suite to verify 100% test pass rate with new repository mocks and integration checks, satisfying **AC-5**.

## Consequences

**Positive**:
- UI pages become concise, readable, and focused solely on layout and user interaction.
- Domain logic and database queries can be tested independently of Streamlit runtime.
- Background tasks no longer trigger sporadic script context exceptions.
- Application startup becomes noticeably faster by avoiding redundant schema table analysis.

**Negative / tradeoffs**:
- Requires touching data access points across all page files during the migration.
- Developers must define new dataclass fields when extending database schema columns.

**Neutral**:
- Preserves the existing SQLite WAL database format and file structure without breaking existing user data in `data/finance.db`.

## Critical test scenarios

- Happy path: Opening Dashboard, Investments, Spending, and Settings pages retrieves all metrics via repository classes with clean formatting, verifying **AC-1** and **AC-3**.
- Migration runner: Starting application on an existing database verifies current schema version without executing completed migrations, verifying **AC-2**.
- Background synchronization: Triggering background bank sync or Copilot inference updates coordinator state without raising detached thread context exceptions, verifying **AC-4**.
- Privacy toggle: Toggling privacy mode obfuscates values across all repository supplied metrics without layout recalculation crashes, verifying **AC-1** and **AC-3**.

## Follow-up

- [ ] Apply repository patterns across remaining secondary pages (`ui/pages/spending.py`, `ui/pages/tax.py`, `ui/pages/mortgage.py`).
- [ ] Migrate ad hoc scripts in `scratch/` to structured tests or administrative commands.
