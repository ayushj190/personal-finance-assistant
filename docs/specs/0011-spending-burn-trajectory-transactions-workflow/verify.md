# Verify: Transactions Select Action Workflow · spec 0011 · updated 2026-10-12
_Steps derived from spec 0011 acceptance criteria. `/check verify` runs these; `/test` locks the durable ones._

## UI / manual
- [ ] Open Transactions view (`Transactions` page) → Table displays left `Select` row checkbox column and no inline internal transfer checkbox column → AC-4
- [ ] Click `Select All` button → All transaction row checkboxes become checked → AC-4
- [ ] Click `Clear All` button → All transaction row checkboxes become unchecked → AC-4
- [ ] Check one or more transaction rows → Persistent bottom action bar appears showing selection count and batch controls → AC-5, AC-6
- [ ] In action bar, click `🔄 Mark Transfer` → Selected rows are saved with `is_internal_transfer = 1` and assigned Transfer category → AC-5, AC-7
- [ ] In action bar, click `↩️ Unmark Transfer` → Selected rows are reverted to `is_internal_transfer = 0` → AC-5, AC-7
- [ ] In action bar, pick category from `Bulk Category` dropdown and click `Apply` → All selected transactions update to chosen category (and merchant rules upsert if toggle is on) → AC-6, AC-7
- [ ] In action bar, click `🗑️ Delete (N)` → Confirmation dialog opens; confirm deletion → Transactions are permanently removed from database → AC-5, AC-7

## Commands
- [ ] `.\.venv\Scripts\pytest tests/test_transactions_workflow.py` → 5 passed (100%) → AC-4, AC-5, AC-6, AC-7
- [ ] `.\.venv\Scripts\pytest tests/test_database.py` → 6 passed (100%) → AC-5, AC-6, AC-7

## Acceptance-criteria coverage
- AC-1: Covered in Slice 9 verify step for spending view toolbar and fiscal cycle tooltip.
- AC-2: Covered in Slice 9 verify step for `calculate_3_month_historical_burn_rate`.
- AC-3: Covered in Slice 9 verify step for 12-month trajectory chart and runway KPI badge.
- AC-4: Covered by UI step 1, 2, 3 and command step `test_transactions_workflow.py::test_ac4_transactions_page_renders_with_select_and_no_inline_transfer_col`.
- AC-5: Covered by UI step 4, 5, 6, 8 and command step `test_transactions_workflow.py::test_ac5_mark_and_unmark_transfer_atomic`, `test_ac5_delete_selected_confirmation_dialog_decorated`.
- AC-6: Covered by UI step 4, 7 and command step `test_transactions_workflow.py::test_ac6_bulk_categorize_with_and_without_rules`.
- AC-7: Covered by UI step 5, 6, 7, 8 and command step `test_transactions_workflow.py::test_ac7_delete_transactions_atomic`, `test_database.py::test_set_transactions_internal_transfer`, `test_database.py::test_bulk_categorize_transactions`.
