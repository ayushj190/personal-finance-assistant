# Verify: Spending & Budgeting Streamline · spec 0004 · updated 2026-10-11
_Steps derived from spec 0004 acceptance criteria. `/check verify` runs these; `/test` locks the durable ones._

## UI / manual
- [ ] Open Spending page -> inspect top 4-KPI ribbon -> verify Total = Fixed + Discretionary + Uncategorized exact identity -> AC-1, AC-2
- [ ] Toggle Privacy mode in header -> verify KPI ribbon, budget cards, and table numbers mask to `€****` -> AC-1
- [ ] Click "✏️ Set Budgets" in action bar -> verify modal dialog opens -> set monthly spending limit on category -> verify budget KPIs and variance table update cleanly without full page rerun flicker -> AC-4
- [ ] Click "🏠 Link Mortgage" in action bar (or inline top item) -> select uncategorized transaction and mortgage loan -> confirm assignment -> verify transaction updates to Mortgage, category rule saves, and schedule updates -> AC-5
- [ ] Click category slice in Analytics donut chart -> verify category drilldown renders locally within the fragment without reloading outer containers -> AC-6
- [ ] Expand "🌊 Cash Flow Topology (Sankey)" container -> verify collapsible layout renders cash flow topology without pushing main views down when collapsed -> AC-6

## Commands
- [ ] `.\.venv\Scripts\pytest tests/test_spending_budgeting.py` -> 7 unit tests pass validating minor unit summation identity, branch rollup logic without double counting, uncategorized isolation, and fragment/dialog decorations -> AC-1, AC-2, AC-3, AC-7
- [ ] `.\.venv\Scripts\pytest` -> all 109 test suite tests pass cleanly with zero regressions -> AC-1, AC-2, AC-3, AC-7

## Acceptance-criteria coverage
- AC-1: Top 4 KPI ribbon exact summation identity and privacy masking covered by UI manual check and `test_strict_summation_identity_and_uncategorized_isolation`, `test_kpi_ribbon_privacy_mode`.
- AC-2: Uncategorized isolation from discretionary expenses covered by UI manual check and `test_strict_summation_identity_and_uncategorized_isolation`.
- AC-3: Branch budget variance rollup without parent-child double counting covered by `test_branch_budget_rollup_no_double_counting` and `test_branch_spend_aggregation_and_status`.
- AC-4: Category budget modal dialog (`@st.dialog`) in `ui/dialogs.py` covered by UI manual check, `test_dialog_functions_decorated`, and `test_branch_budget_rollup_no_double_counting`.
- AC-5: Mortgage assignment modal dialog (`@st.dialog`) in `ui/dialogs.py` covered by UI manual check, `test_dialog_functions_decorated`, and `test_mortgage_assignment_flow`.
- AC-6: Category donut drilldown fragment isolation and collapsible Sankey container covered by UI manual check and `test_fragments_decorated`.
- AC-7: Integer minor units (cents) enforcement through calculation routines covered by `test_strict_summation_identity_and_uncategorized_isolation` and `test_branch_budget_rollup_no_double_counting`.
