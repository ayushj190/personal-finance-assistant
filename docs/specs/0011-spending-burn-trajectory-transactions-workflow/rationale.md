# 0011. Spending Flow, Historical Burn Trajectory, and Transactions Select Action Workflow · Rationale

## Context

The personal finance application presents two closely related workflows that currently carry UX friction and calculation limitations.

First, the spending overview page (`ui/pages/spending.py`) displays redundant filter and transfer controls alongside a separate fiscal payday banner. Its 12 month financial trajectory projection currently computes current burn rate using only the single most recent fiscal month. This makes the runway projection overly sensitive to short term anomalies, such as an irregular quarterly bill or vacation expense, rather than reflecting true baseline spending habits.

Second, the transactions management ledger (`ui/pages/transactions.py`) relies on an inline checkbox column for internal transfers alongside a separate delete selection column. Having two distinct checkbox mechanisms in a single tabular view confuses user interactions. Users also lack bulk categorization capabilities, forcing them to manually change categories row by row across multi item imports.

By consolidating these improvements into a cohesive update, we streamline expense analysis, establish realistic runway projections based on actual three month expenditure history, and introduce a modern multi row selection workflow with batch actions.

## Options considered

### Option 1: Fragmented implementation across two separate specs

Keep Slice 9 (Spending Flow and Burn Trajectory) and Slice 10 (Transactions Select Action Workflow) strictly separated into two distinct specs and implementation cycles.

**Pros**:
- Isolates page changes into smaller independent code commits.

**Cons**:
- Duplicates database helper additions and testing runs across adjacent financial ledger views.
- Delays user productivity gains by splitting tightly coupled expense review workflows.

### Option 2: Unified workflow enhancement with shared atomic batch helpers (Recommended)

Combine spending flow decluttering, three month burn analytics, and transaction select action tools into a single coherent spec, sharing transaction update helpers in `db/database.py`.

**Pros**:
- Solves both expense review and transaction maintenance bottlenecks simultaneously.
- Consolidates bulk database operations into reusable, tested core functions.
- Provides immediate end to end consistency between categorized transactions and historical spending projections.

**Cons**:
- Requires coordinated edits across `services/budget_service.py`, `db/database.py`, `ui/pages/spending.py`, and `ui/pages/transactions.py`.

## Rationale

Expense classification directly feeds monthly spending summaries and burn projections. When users review their spending flow and notice misclassified transactions or internal transfers leaking into discretionary totals, they navigate to the transactions table to correct them. Integrating the three month burn model with streamlined bulk actions ensures that adjustments to transfers and categories immediately reflect in accurate, stabilized runway projections.

Reusing atomic batch methods in `db/database.py` satisfies the project rule of centralized SQLite database interactions with foreign key enforcement and integer minor unit precision.
