# 0004. Spending & Budgeting Streamline

**Date**: 2026-10-11
**Status**: Accepted

## Summary

This decision streamlines the spending and budgeting views to deliver accurate expense summaries and eliminate interface clutter. Dense configuration forms for category budget caps and mortgage transaction assignments move out of inline page containers into focused modal dialog popups in `ui/dialogs.py`. Calculation queries in `ui/pages/spending.py` and `services/budget_service.py` are corrected so uncategorized transactions never leak into discretionary totals and category budget hierarchies aggregate without double counting.

## Requirements

**User stories**:
- As a user, I want clear and accurate totals for my expenses across fiscal cycles so that I can track spending without double counted sums.
- As a user, I want to set and monitor category budgets with clean variance metrics so that I understand where I stand against monthly spending limits.
- As a user, I want dense entry and assignment forms tucked into modal popups so that the spending page remains clean and easy to scan.
- As a user, I want uncategorized expenses clearly isolated so that I can categorize them quickly or link them directly to a mortgage loan.

**Acceptance criteria**:
- **AC-1**: The spending view presents a top 4 KPI ribbon (Total Expenses, Fixed Expenses, Discretionary Expenses, Uncategorized Expenses) satisfying the exact mathematical identity `Total = Fixed + Discretionary + Uncategorized`, with full support for privacy mode masking via `is_hidden()`.
- **AC-2**: Spending queries and category classification logic prevent uncategorized transactions (`category_id IS NULL` or category named Uncategorized) from being classified as discretionary expenses.
- **AC-3**: Budget variance calculation in `services/budget_service.py` calculates parent category targets and child limits without double counting, rolling up child expenses to parent categories cleanly.
- **AC-4**: Category budget caps are managed through a dedicated modal popup (`@st.dialog`) in `ui/dialogs.py` launched from a header action button on the Spending page, removing dense inline input forms from the primary canvas.
- **AC-5**: Uncategorized mortgage assignment is moved into a dedicated modal popup (`@st.dialog`) in `ui/dialogs.py`, allowing users to link loan payments directly to liability schedules without cluttering the main spending review flow.
- **AC-6**: Category donut chart drilldown executes within an isolated Streamlit fragment or clean state handler, and the macro cash flow Sankey diagram is placed in a collapsible container below the primary category breakdown.
- **AC-7**: All money aggregations and comparisons enforce integer minor units (cents) through calculation routines, converting to floating point euros only at the presentation boundary.

## Decision

**Chosen option**: Option 1: Streamlined spending view with modal dialog extraction, branch rollup budgeting, and exact ledger classification.

The spending page is restructured into focused analytical sections, moving heavy forms into `@st.dialog` popups, fixing uncategorized category leakage, and supporting non overlapping branch budgeting.

## Rationale

Reasoning and options: see rationale.md.

## Feature design

**Data model sketch**:
The implementation reuses existing SQLite tables without requiring schema migrations:

| Entity | Primary Key | Foreign Keys | Key Fields | Purpose |
|---|---|---|---|---|
| `categories` | `id` | `parent_id -> categories.id` | `name`, `kind` ('fixed', 'discretionary', 'income', 'savings', 'transfer') | Category hierarchy with parent and child relationships |
| `category_budgets` | `category_id` | `category_id -> categories.id` | `monthly_limit_eur` | Monthly target spending limit per category |
| `transactions` | `id` | `account_id -> accounts.id`, `category_id -> categories.id` | `amount_eur_minor`, `booking_date`, `is_internal_transfer`, `merchant_normalized` | Ledger records in integer cents minor units |
| `liabilities` | `id` | None | `name`, `lender`, `payment_match_pattern` | Loan accounts linked to mortgage transactions |
| `liability_extra_payments` | `(liability_id, paid_date)` | `liability_id -> liabilities.id` | `amount_minor`, `recalc` | Recorded unscheduled mortgage repayments |

**Component & dialog architecture**:

```
ui/pages/spending.py (render)
├── Date Scope & Fiscal Payday Header
├── 4-KPI Ribbon (Total, Fixed, Discretionary, Uncategorized)
├── Action Header Bar: [✏️ Set Budgets] [🏠 Link Mortgage]
├── Analytics Section [@st.fragment]
│   ├── Col 1: Category Donut Chart (Drilldown)
│   └── Col 2: Top Merchants & Recurring Subscriptions
├── Category Budget Tracker & Variance [@st.fragment]
│   ├── KPI Cards (Monthly Budget, Current Spend, Budget Variance)
│   └── Hierarchical Variance Table (Rollup status, % used, badges)
├── Uncategorized Quick Triage Table (Inline category assignments)
├── Collapsible Flow Details [st.expander("Cash Flow Topology (Sankey)", expanded=False)]
└── Monthly Expense Trend & Summary Table

ui/dialogs.py
├── set_category_budget_dialog(conn) [@st.dialog]
│   └── Select category, view current limit, save updated monthly limit
└── assign_mortgage_dialog(conn, tx_id=None) [@st.dialog]
    └── Select uncategorized transaction, link to liability, configure extra payment
```

**Value sourcing**:
| Action / Element | Value produced / displayed | Source |
|---|---|---|
| Top KPI Ribbon | Total Expenses (€) | Sum of `-t.amount_eur_minor / 100.0` where `amount_eur_minor < 0`, `is_internal_transfer = 0`, and category kind not in ('savings', 'transfer', 'income') |
| Top KPI Ribbon | Fixed Expenses (€) | Sum of expense transactions where `c.kind = 'fixed'` |
| Top KPI Ribbon | Discretionary Expenses (€) | Sum of expense transactions where `c.kind = 'discretionary'` and `t.category_id IS NOT NULL` and `c.name != 'Uncategorized'` |
| Top KPI Ribbon | Uncategorized Expenses (€) | Sum of expense transactions where `t.category_id IS NULL` or `c.name = 'Uncategorized'` |
| Category Donut | Top Category Slices | Grouped sums of `amount_eur` by `parent_category` |
| Budget KPI | Monthly Budget Target (€) | Total effective budget computed across category branches without double counting |
| Budget KPI | Current Spend (€) | Total actual expense spend in the selected fiscal month |
| Budget KPI | Budget Variance (€) | Total effective budget minus total actual spend |
| Budget Table | % Used & Status Badge | `(spent / budget * 100)` mapped to On Track, Near Limit, or Over Budget |
| Dialog Form | New Budget Limit (€) | User input written to `category_budgets` via `services.budget_service.set_category_budget` |
| Dialog Form | Mortgage Assignment | Transaction updated with Mortgage category, merchant rule upserted, and extra payment recorded if selected |

**Key invariants**:
- Strict summation identity: `Total Expenses = Fixed Expenses + Discretionary Expenses + Uncategorized Expenses` must hold across all scopes and summaries.
- Uncategorized transactions must never default to discretionary classification.
- Budget branch rollup rule: if a parent category has a limit `B_parent > 0` and its children have limits `sum(B_children)`, total effective branch budget equals `B_parent` (or `sum(B_children)` when parent limit is zero). Parent and child limits are never summed together.
- All database mutations in dialog popups run within explicit SQLite transaction blocks (`with conn:`), trigger `st.rerun(scope="app")`, and cleanly close connections.
- Sensitive financial figures are masked with `€****` when `is_hidden()` is active.

**Security model**:
- Pure local execution: database remains in `data/finance.db`.
- Database operations enforce write locks safely via WAL mode.
- Read only inspection rules protect queries from unintended updates.

**Critical test scenarios**:
- Ledger sum reconciliation: verify that total expenses equal the sum of fixed, discretionary, and uncategorized expenses across multiple sample transactions, verifying **AC-1**, **AC-2**, **AC-7**.
- Budget variance branch rollup: verify that setting limits on both parent and child categories does not double count in `total_budget_eur`, verifying **AC-3**, **AC-7**.
- Category budget modal dialog: verify that saving an updated limit in `set_category_budget_dialog` persists correctly to SQLite and updates variance calculations, verifying **AC-4**.
- Mortgage assignment dialog: verify that assigning an uncategorized payment updates the transaction record, upserts the merchant category rule, and syncs the liability schedule, verifying **AC-5**.
- Visual streamlining & collapsible Sankey: verify that the spending page renders the 4 KPI ribbon, donut drilldown, and collapsible Sankey container without full page rerun flicker, verifying **AC-6**.

## Build plan

Ordered by the project Tracer Bullet approach (thin vertical thread fixing calculation models and dialog functions first, then assembling streamlined page fragments and automated tests):

1. [x] Correct transaction classification and budget variance rollup calculations in `ui/pages/spending.py` and `services/budget_service.py` to eliminate uncategorized leakage and parent child double counting, satisfies **AC-1**, **AC-2**, **AC-3**, **AC-7**.
2. [x] Implement modal dialog functions `set_category_budget_dialog` and `assign_mortgage_dialog` in `ui/dialogs.py`, satisfies **AC-4**, **AC-5**.
3. [x] Refactor `ui/pages/spending.py` layout to launch dialog modals from header action buttons, streamlines the category donut chart and merchants table inside an `@st.fragment`, satisfies **AC-4**, **AC-5**, **AC-6**.
4. [x] Convert the cash flow Sankey diagram into a collapsible container (`st.expander`) positioned beneath the category breakdown and refine the monthly trend table, satisfies **AC-1**, **AC-6**.
5. [x] Add unit test suite in `tests/test_spending_budgeting.py` covering calculation accuracy, budget branch rollups, and dialog state handlers, satisfies **AC-1**, **AC-2**, **AC-3**, **AC-7**.

## Consequences

**Positive**:
- Expense summaries accurately reflect ledger records with zero category leakage.
- Budget targets provide reliable tracking without double counted branch limits.
- Canvas clutter is eliminated by shifting dense multi field forms into clean modal dialogs.
- Interactive donut drilldowns operate without disrupting the rest of the interface.

**Negative / tradeoffs**:
- Configuring category budgets now requires clicking an action button to open a popup rather than editing inline on the page canvas.
- Viewing the cash flow Sankey diagram requires expanding a collapsible section rather than viewing it immediately upon scroll.

**Neutral**:
- Reuses existing tables in `data/finance.db`, requiring no migration scripts or data transformations.

## Follow-up

- [ ] Confirm during `/check verify` that mobile or narrow window viewports display the action button bar and modal dialogs cleanly without horizontal overflow.
