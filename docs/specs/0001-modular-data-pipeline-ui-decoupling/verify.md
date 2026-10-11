# Verify: Modular Data Pipeline & UI Component Decoupling · spec 0001 · updated 2026-10-11
_Steps derived from spec 0001 acceptance criteria. `/check verify` runs these; `/test` locks the durable ones._

## UI / manual
- [ ] Open Dashboard page → verify all metrics, account cards, spending donut, and recurring charges render with zero raw SQL queries → AC-1
- [ ] Open Investments page → verify total value, allocation profiles, and dividend projections render via repository queries and explicit chart helper → AC-1, AC-3
- [ ] Toggle Privacy mode in app top bar → verify amounts mask to asterisks cleanly across repository powered cards without layout recalculation crashes → AC-1, AC-3
- [ ] Observe background sync execution → verify task coordinator updates background job status without detached Streamlit context errors or rerun loops → AC-4

## Commands
- [ ] `.\.venv\Scripts\python.exe -m pytest` → 74 passed with 100% success rate → AC-5
- [ ] `.\.venv\Scripts\python.exe -m pytest tests/test_repositories_and_decoupling.py` → all repository, migration, coordinator, and theme tests pass → AC-1, AC-2, AC-3, AC-4, AC-5
- [ ] `.\.venv\Scripts\python.exe -c "from db.database import connect; from db.migrations.runner import run_migrations; conn = connect(); print('Pending:', run_migrations(conn)); conn.close()"` → returns `Pending: []` (idempotent, skips unneeded DDL) → AC-2

## Acceptance-criteria coverage
- AC-1 core entity queries routed via db/repositories/ returning dataclasses · covered by repository unit tests and Dashboard/Investments UI loading
- AC-2 database migrations run versioned and idempotent via db/migrations/runner.py · covered by test_migration_runner and database tests
- AC-3 modular theme tokens, static custom.css, and explicit render_chart helper · covered by test_theme_and_charts_no_monkey_patching and charts rendering
- AC-4 thread safe TaskCoordinator isolating background workers from Streamlit context · covered by test_task_coordinator and app.py background sync
- AC-5 100% passing test suite across all 68 original tests plus 6 new repository and decoupling tests (74 total)
