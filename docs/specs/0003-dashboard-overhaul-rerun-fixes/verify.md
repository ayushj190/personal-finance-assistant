# Verify: Dashboard Overhaul & Rerun Fixes · spec 0003 · updated 2026-10-11
_Steps derived from spec 0003 acceptance criteria. `/check verify` runs these; `/test` locks the durable ones._

## UI / manual
- [x] Load dashboard with accounts present → top KPI ribbon displays Net Worth, Liquid Cash, Investments, and Monthly Cash Flow cards → AC-1
- [x] Toggle hide amounts mode on → all four KPI amounts and accrued values display masked placeholders (`€****`) → AC-1
- [x] Click slice on spending donut chart → chart drills down to merchants or subcategories inside isolated fragment without full page reload → AC-2
- [x] Click "← Back to Categories" button → returns to category donut without page flicker → AC-2
- [x] View TradingView ticker tape widget → widget remains stable and does not remount on local chart or form interactions → AC-3
- [x] Inspect account cards settings popover cog → widget keys strictly follow `dashboard_acc_{id}_*` without collision → AC-4
- [x] Submit new account balance in popover form → balance persists in integer cents in database and top KPI totals refresh cleanly → AC-5
- [x] Launch dashboard on clean database with 0 accounts → clean empty state container prompts to import statements or connect API → AC-6
- [x] View analytics section with 0 transactions → displays friendly guided empty state instead of blank charts or errors → AC-6

## Commands
- [x] `.\.venv\Scripts\pytest -k test_dashboard_page` → 9/9 tests pass covering KPI ribbon, fragment decoration, namespaced keys, and empty states → AC-1, AC-2, AC-3, AC-4, AC-5, AC-6
- [x] `.\.venv\Scripts\pytest` → 102/102 test suite passes clean with 0 regressions → AC-1 to AC-6

## Value sourcing
- [x] Net Worth matches `calculate_current_net_worth(conn)["net_worth"]` → AC-1
- [x] Liquid Cash matches `calculate_current_net_worth(conn)["liquid_cash"]` → AC-1
- [x] Investments matches `calculate_current_net_worth(conn)["invested"]` → AC-1
- [x] Monthly Cash Flow matches net sum of transactions in last 30 days → AC-1
- [x] Account Card displays authentic SVG logo and clean name without duplicate clutter → AC-5
- [x] Account Card accrued interest reflects `(apy / 100.0) / 365.0 * days` accrued since snapshot date → AC-5
- [x] Spending donut slices source directly from `TransactionRepository.get_recent_spending_df(conn, days=30)` → AC-2
- [x] Recurring bills table sources from `detect_recurring_charges(all_tx_rows)` → AC-2

## Acceptance-criteria coverage
- AC-1 covered by KPI ribbon render, hide amounts toggle, value sourcing checks
- AC-2 covered by donut chart drilldown, back button, recurring bills table
- AC-3 covered by TradingView ticker tape isolation, market news fragment
- AC-4 covered by pytest namespaced keys assertion, inspect account popovers
- AC-5 covered by popover balance form update, minor units persistence, accrued interest subtext
- AC-6 covered by zero accounts empty state, zero transactions empty state
