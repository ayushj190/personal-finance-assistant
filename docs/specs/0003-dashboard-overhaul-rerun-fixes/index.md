# 0003. Dashboard Overhaul & Rerun Fixes

**Date**: 2026-10-11
**Status**: Complete

## Summary

This decision redesigns the primary personal finance dashboard to use clean design tokens and eliminates Streamlit rerun flickering. Interactive sections such as spending charts and balance adjustment controls run inside isolated fragments, so page interactions update smoothly without reloading the entire page or reloading the TradingView ticker tape. All widgets receive strict namespaced keys, preventing duplicate key warnings and keeping user interactions reliable.

## Requirements

**User stories**:
- As a user, I want a minimalist overview of my net worth, liquid cash, investments, and cash flow so that I can understand my financial health at a glance.
- As a user, I want chart interactions and balance edits to update without full page flickering or reloading external ticker widgets so that the interface feels fast and stable.
- As a user, I want clear feedback and empty states when no accounts or transactions exist so that I know what action to take next.

**Acceptance criteria**:
- **AC-1**: The dashboard renders a top KPI ribbon with Net Worth, Liquid Cash, Investments, and Monthly Cash Flow using design tokens from ui/theme, supporting hide amounts mode via `is_hidden()`.
- **AC-2**: Spending category donut drilldown and monthly cash flow comparisons execute within an `@st.fragment` boundary, so selecting points updates local state without triggering full page reruns.
- **AC-3**: Third party external widgets, including the TradingView ticker tape and eToro news feed, are isolated within static fragments so that balance adjustments or chart selections never force them to reload.
- **AC-4**: All input controls and adjustment forms use deterministic, namespaced keys formatted as `dashboard_acc_{id}_*`, preventing duplicate widget key collisions.
- **AC-5**: Accounts and balances grid displays institution logos, status badges, and popover adjustment forms with proper minor unit conversion and clean alignment across all card heights.
- **AC-6**: When zero accounts or zero transactions exist, the dashboard renders clean empty state containers with guided action prompts rather than raising exceptions or showing blank charts.

## Decision

**Chosen option**: Option 1: Fragment isolated dashboard with namespaced state and tokenized KPI cards.

The primary dashboard is refactored into distinct Streamlit fragments for interactive regions, isolating the TradingView ticker, account adjustment popovers, and spending chart drilldowns while using unified tokens for KPI cards and account rows.

## Rationale

Reasoning and options: see rationale.md.

## Feature design

**Data model sketch**:
The dashboard reads existing SQLite tables and writes manual snapshot overrides without altering schema definitions:

| Entity | Key | Key Fields | Purpose |
|---|---|---|---|
| accounts | id (PK) | institution, name, currency, asset_class, apy, is_active | Account metadata and institution identity |
| account_snapshots | id (PK) | account_id (FK), snapshot_date, balance_minor, balance_eur_minor | Historical and current balance entries in integer cents |
| transactions | id (PK) | account_id (FK), booking_date, amount_minor, amount_eur_minor, category, merchant | 30 day spending breakdown and recurring bill detection |
| liabilities | id (PK) | name, outstanding_balance_minor, interest_rate | Debt balances subtracted to compute net worth |

**Component & fragment architecture**:

```
dashboard.render() (ui/pages/dashboard.py)
├── _render_ticker_fragment() [@st.fragment] -> TradingView iframe (isolated from reruns)
├── _render_kpi_ribbon() -> Net Worth, Liquid Cash, Investments, Cash Flow cards
├── _render_accounts_grid(accounts, nw_data) [@st.fragment] -> Account cards + Popover adjustment forms
├── _render_analytics_section(conn) [@st.fragment]
│   ├── Col 1: Spending Donut drilldown chart
│   └── Col 2: Upcoming Recurring Bills table
└── _render_market_news_fragment() [@st.fragment] -> Cached eToro news feed
```

**Value sourcing**:
| Action / Element | Value produced / displayed | Source |
|---|---|---|
| Top KPI Ribbon | Net Worth (€) | `calculate_current_net_worth(conn)["net_worth"]` |
| Top KPI Ribbon | Liquid Cash (€) | `calculate_current_net_worth(conn)["liquid_cash"]` |
| Top KPI Ribbon | Investments (€) | `calculate_current_net_worth(conn)["invested"]` |
| Top KPI Ribbon | Monthly Cash Flow (€) | Sum of income minus expenses from `TransactionRepository.get_v_transactions` over last 30 days |
| Account Card | Institution Logo & Name | `get_institution_logo_svg` + `clean_account_name` |
| Account Card | Current Balance | `nw_data["acc_balances"][acc.id]` |
| Account Card | Accrued Interest Subtext | Calculated from `acc.apy` and days since snapshot date |
| Balance Adjustment | Persisted Minor Units | Form input multiplied by 100 passed to `database.upsert_snapshots` |
| Spending Donut | Categories & Slices | `TransactionRepository.get_recent_spending_df(conn, days=30)` |
| Recurring Bills | Subscriptions & Cadence | `detect_recurring_charges(all_tx_rows)` |

**Key invariants**:
- All financial balances are fetched in integer cents and converted to euros only at presentation boundaries.
- When `is_hidden()` returns true, all sensitive financial figures display masked placeholders (`****`).
- Updating an account balance in a popover form calls `st.rerun(scope="app")` so that the top KPI ribbon updates its totals, while spending chart drilldowns execute locally within the fragment without reloading the page.
- Every interactive widget key follows the pattern `dashboard_{component}_{id}_{action}` to prevent collisions.

**Security model**:
- Pure local execution: data stays in `data/finance.db`, credentials remain in Windows Credential Manager.
- No sensitive user balance data is passed into external iframes or third party query parameters.

**Critical test scenarios**:
- Happy path: Opening dashboard with active accounts and transactions renders all four KPI cards, accounts grid, spending donut, and bills table cleanly, verifies **AC-1**, **AC-5**.
- Fragment isolation: Clicking on a donut slice or submitting a balance adjustment updates the local section without refreshing or flickering the TradingView widget, verifies **AC-2**, **AC-3**.
- State namespace safety: Navigating between multiple accounts and adjusting balances triggers zero Streamlit `DuplicateWidgetID` warnings, verifies **AC-4**.
- Empty state: Initializing with an empty database renders friendly onboarding empty states without exceptions, verifies **AC-6**.

## Build plan

Ordered by the project Tracer Bullet approach (thin end to end thread through layout and fragments first, then refining cards, charts, and edge cases):

- [x] 1. Refactor `ui/pages/dashboard.py` into modular Streamlit fragment functions (`_render_ticker_fragment`, `_render_accounts_grid`, `_render_analytics_section`, `_render_market_news_fragment`), satisfies **AC-2**, **AC-3**.
- [x] 2. Implement the updated 4 KPI ribbon with Net Worth, Liquid Cash, Investments, and Monthly Cash Flow utilizing design tokens and respecting `is_hidden()`, satisfies **AC-1**.
- [x] 3. Overhaul the accounts grid card layout with strict key namespacing (`dashboard_acc_{id}_*`) and seamless popover forms for manual balance adjustments, satisfies **AC-4**, **AC-5**.
- [x] 4. Modernize the spending donut chart and cash flow comparison within the isolated analytics fragment, satisfies **AC-2**.
- [x] 5. Add empty state handling for accounts and transactions, satisfies **AC-6**.
- [x] 6. Implement comprehensive unit and fragment render tests for dashboard components, satisfies **AC-1**, **AC-2**, **AC-4**, **AC-6**.

## Consequences

**Positive**:
- Eliminates page flicker and unwanted reloads of third party iframes on user interactions.
- Prevents duplicate widget key collisions across accounts.
- Restores clean visual hierarchy and consistent card alignment using ui/theme tokens.

**Negative / tradeoffs**:
- Streamlit fragments require Streamlit 1.37+ and careful scoping of session state to ensure inter fragment synchronization when balances update.

**Neutral**:
- No SQLite schema migrations are required; all changes reside in the UI presentation layer.

## Follow-up

- [ ] Verify that Streamlit session state keys updated inside `_render_accounts_grid` propagate properly to `_render_kpi_ribbon` if a top level rerun is needed on balance change.
