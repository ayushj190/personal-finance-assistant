# 0011. Spending Flow, Historical Burn Trajectory, and Transactions Select Action Workflow

**Date**: 2026-10-12
**Status**: Accepted

## Summary

This build spec unifies spending flow decluttering, historical burn trajectory forecasting, and modern transaction table bulk actions across Slice 9 and Slice 10. We replace cluttered spending header controls with a compact toolbar featuring a fiscal cycle tooltip, update the runway forecast to project cash buffers from a three month historical burn rate, and modernize the transactions view with left selection checkboxes and a bottom action bar for transfers, categorization, and deletion. All state modifications run atomically in SQLite using integer minor units (cents) to maintain strict ledger integrity.

## Requirements

**User stories**:
- As a user managing monthly finances, I want a clean spending header with clear fiscal cycle context so that I can switch view scopes without visual clutter.
- As a user evaluating financial runway, I want the projection chart to use a three month historical burn rate so that my projected cash depletion reflects realistic long term habits rather than single month noise.
- As a user reviewing imported transactions, I want standard row selection checkboxes and a bottom action bar so that I can mark internal transfers, assign categories, or delete records in batch.

**Acceptance criteria**:
- **AC-1**: The spending view header in `ui/pages/spending.py` displays a compact single row toolbar containing the View Scope selectbox with an explanatory calendar tooltip showing the active fiscal cycle range, removing duplicate filter buttons and redundant status notices.
- **AC-2**: `services/budget_service.py` provides `calculate_3_month_historical_burn_rate` computing the arithmetic mean of total, fixed, and discretionary spend across the past three completed fiscal months using integer cents, falling back gracefully to all available months when fewer than three exist.
- **AC-3**: The 12 Month Financial Trajectory chart in `ui/pages/spending.py` uses the three month historical burn rate as its baseline, rendering current burn and budgeted target curves alongside an explicit cash runway KPI badge indicating remaining months of liquidity or sustainable surplus.
- **AC-4**: The transactions table in `ui/pages/transactions.py` removes the inline internal transfer checkbox column and provides standard left row selection checkboxes driven by a `select` column, accompanied by Select All and Clear All helper controls.
- **AC-5**: A persistent bottom action bar appears below the transactions table when rows are selected, providing `Mark Transfer` (sets internal transfer flag to 1 and assigns the Transfer category), `Unmark Transfer` (reverts flag to 0), and `Delete Selected` with confirmation.
- **AC-6**: The bottom action bar includes a category picker and `Apply` button allowing one click category updates for all checked transactions, with an optional merchant category rule upsert.
- **AC-7**: All bulk database operations execute atomically within explicit SQLite transaction blocks (`with conn:`) enforcing foreign key constraints and exact integer cents summation invariants.

## Decision

**Chosen option**: Option 2: Unified workflow enhancement with shared atomic batch helpers (see `rationale.md`).

We unify the spending header decluttering, three month historical burn rate modeling, and multi row transaction action bar into a single comprehensive implementation.

## Feature design

**Data model sketch**:
No new tables or schema migrations required. The solution leverages existing SQLite tables:
- `transactions`: `id`, `account_id`, `booking_date`, `amount_eur_minor`, `merchant_normalized`, `category_id`, `category_source`, `is_internal_transfer`
- `categories`: `id`, `name`, `parent_id`, `kind` ('income', 'fixed', 'discretionary', 'savings', 'transfer')
- `merchant_category_rules`: `merchant_normalized`, `category_id`, `source`, `confidence`, `hit_count`

**API and function surface**:

| Function / Module | Signature | Key inputs | Outputs / Behavior | Key errors / Guarantees |
|---|---|---|---|---|
| `services/budget_service.py` | `calculate_3_month_historical_burn_rate(conn, reference_date=None)` | SQLite connection, optional reference ISO date string | Dictionary with `avg_burn_minor`, `avg_burn_eur`, `fixed_burn_eur`, `disc_burn_eur`, `months_count`, `month_labels` | Safe fallback if fewer than 3 months exist; excludes internal transfers and non expense categories |
| `services/budget_service.py` | `calculate_12_month_runway_forecast(...)` | liquid cash, projected income, current burn rate, budgeted burn rate, horizon months | List of monthly forecast dictionaries, plus runway months calculation | Handles zero and negative net burn without division by zero; caps lower balance at 0.0 |
| `db/database.py` | `set_transactions_internal_transfer(conn, tx_ids, is_transfer=True)` | SQLite connection, list of integer transaction IDs, boolean flag | Number of updated rows | Atomic update in `with conn:`; auto assigns Transfer category when marking true |
| `db/database.py` | `bulk_categorize_transactions(conn, tx_ids, category_id, source='user', update_rules=False)` | SQLite connection, list of integer IDs, category ID, optional source and rule flag | Number of updated rows | Atomic update; optionally updates `merchant_category_rules` for distinct merchants |

**Value sourcing**:

| Action | Value produced / displayed | Source |
|---|---|---|
| Spending View Scope Toolbar | Fiscal cycle tooltip text | Formatted dynamically from `fiscal_service.get_fiscal_salary_day(conn)` |
| 12 Month Trajectory Chart | Baseline monthly burn rate | Arithmetic mean of total spending across last 3 completed fiscal months from `calculate_3_month_historical_burn_rate` |
| Trajectory KPI Badge | Cash runway in months | Derived from `liquid_cash / max(1.0, current_burn - projected_income)` when net burn > 0 |
| Transactions Table | Multi row selection states | Streamlit `data_editor` `select` checkbox column state, initialized and toggled via `st.session_state` keys for Select All and Clear All |
| Action Bar Transfer Toggle | `is_internal_transfer` column | Updated in SQLite via `set_transactions_internal_transfer` |
| Action Bar Category Apply | `category_id` and `category_source` | Updated in SQLite via `bulk_categorize_transactions` |
| Action Bar Delete Trigger | Deletion confirmation modal | Streamlit modal dialog or popover confirming deletion of count checked rows before calling `delete_transactions` |

**Key invariants**:
- Total expense sums equal fixed plus discretionary plus uncategorized expenses in exact integer cents.
- Internal transfers are excluded from spending totals, category variance rollups, and burn rate calculations.
- Bulk database updates run inside atomic transactions ensuring all or nothing execution.

**Security model**:
Local first single user desktop deployment. All database operations execute on local SQLite `finance.db` with read write access managed through `db/database.py`.

**Critical test scenarios**:
- Three month burn calculation correctly computes arithmetic mean over completed fiscal months and handles accounts with one or two months of history, verifies **AC-2**.
- Runway forecast handles surplus scenarios (infinite runway) and burn depletion scenarios without division errors, verifies **AC-3**.
- Marking transactions as internal transfers updates the database flag and assigns the Transfer category, verifies **AC-5**, **AC-7**.
- Bulk category assignment updates multiple transaction rows and optionally upserts merchant category rules, verifies **AC-6**, **AC-7**.
- Spending header renders cleanly without duplicate filter controls, verifies **AC-1**.

## Build plan

Order follows the Tracer Bullet approach, establishing end to end functionality through persistence, service analytics, and UI components.

1. [x] Add atomic batch transaction mutation functions `set_transactions_internal_transfer` and `bulk_categorize_transactions` to `db/database.py`, satisfies **AC-5**, **AC-6**, **AC-7**
2. [x] Implement `calculate_3_month_historical_burn_rate` and updated runway metrics in `services/budget_service.py`, satisfies **AC-2**, **AC-3**
3. [x] Refactor spending header toolbar, fiscal cycle tooltip, and trajectory chart in `ui/pages/spending.py`, satisfies **AC-1**, **AC-3**
4. [x] Modernize transactions table with row selection checkboxes, select helper buttons, and bottom action bar in `ui/pages/transactions.py`, satisfies **AC-4**, **AC-5**, **AC-6**
5. [x] Add comprehensive unit tests covering batch operations, 3 month burn calculations, and UI helper logic, satisfies **AC-1**, **AC-2**, **AC-3**, **AC-4**, **AC-5**, **AC-6**, **AC-7**

## Consequences

**Positive**:
- Eliminates UI clutter in the spending view, making scope and fiscal cycle immediately understandable.
- Stabilizes financial runway forecasts against single month spending spikes.
- Dramatically accelerates transaction review and cleanup with multi row actions.
- Reusable batch helpers strengthen the database service layer for future import workflows.

**Negative / tradeoffs**:
- A three month moving average takes longer to reflect deliberate lifestyle spending cuts than a single month snapshot.
- Bulk categorization applies across all selected rows without individual preview, requiring users to pay attention to checked rows before applying.

**Neutral**:
- No schema migrations required; existing database structure accommodates all features.

## Follow-up

- [ ] Connect bulk categorization to ML classification confidence feedback in future Copilot upgrades.
- [ ] Allow customizable burn horizon (such as 6 month or 12 month average) in application settings.
