# 0020 · Cash flow chart salary source

**Status**: Assumed
**Date**: 2026-10-14
**Authorized by**: the engineer, during /develop

## Owed decision

Which transactions may feed the Gross Salary node of the cash flow Sankey, and how the monthly holiday allowance (vakantiegeld) enters that figure. There is no spec covering this chart, and the value has no named source anywhere in the repo.

## Assumption built on

Gross Salary is read from the Salary category only (`categories.name = 'Salary'`), the same source `services/fiscal_service.get_default_salary_day` and `db/repositories/transaction_repository.get_latest_salary_date` already use. That amount is taken as the net pay the month already carries (which is where the monthly holiday allowance payout sits), and it is scaled to gross with the effective Box 1 rate the module already derives from `tax_profile` and `calculate_box1_tax`. No separate holiday allowance is added, and a deposit in any other category (uncategorized, a refund, a savings move, an internal transfer) never feeds the node.

## Code area

`ui/charts/sankey.py` (`prepare_cash_flow_sankey_data`)

## Requirements

- Gross Salary comes from Salary category transactions inside the selected window, never from other deposits.
- The chart keeps its shape: Gross Salary to Taxes (Box 1) plus Net Income, and Net Income to the expense buckets, with the effective tax rate from `tax_profile`.
- A window with no salary payment falls back to `tax_profile.gross_annual_income`, as it did before, so the chart still renders.
- Hide values still masks the chart.
- A regression test covers the rule: adding an uncategorized deposit, a refund, and an internal transfer to the fixture leaves `gross_salary` and `net_salary` unchanged (`tests/test_sankey_drilldown.py`).

## Noted consequence

Income that is not salary (dividends, interest, other income, bonus) no longer feeds the salary node, so in a window where those arrive but salary does not, the chart shows a savings drawdown funding the spend. This follows from the decision above and is worth a look when the assumption is ratified.

## Ratify

This decision was recorded by /develop, not deliberated. Run `/architect cash flow salary source` to deliberate and ratify it. Until then it stays flagged as an owed decision; it does not block marking the feature done.
