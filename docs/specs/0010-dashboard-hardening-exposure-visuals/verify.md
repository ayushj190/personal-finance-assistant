# Verify: Dashboard Hardening & Exposure Visuals · spec 0010 · updated 2026-10-12
_Steps derived from spec 0010 acceptance criteria. `/check verify` runs these; `/test` locks the durable ones._

## UI / manual
- [ ] Open Dashboard → Accounts grid displays accounts separated into Cash and Investments sections → AC-6
- [ ] In Accounts grid → Cards are ordered alphabetically by institution and name within each section, showing emerald accents for cash and indigo for investments → AC-6
- [ ] In Dashboard Expenses panel → Cash flow Sankey renders cleanly without iframe flickering or bridge warnings → AC-3
- [ ] Click `⛶ Expand` icon above Sankey → Fullscreen dialog modal opens and displays the full-resolution Sankey diagram → AC-4
- [ ] In Dashboard Portfolio exposure panel → Market Carpet treemap renders rounded translucent glassmorphic tiles with semantic RGBA coloring → AC-5
- [ ] Open Spending page → Click `⚙️ Set Budgets` → Budget configuration dialog opens, accepts updates, and saves without thread exceptions or `ProgrammingError` crashes → AC-1, AC-2

## Commands
- [ ] `.\.venv\Scripts\pytest tests/test_dashboard_hardening.py` → 8 passed (100%) → AC-1, AC-2, AC-3, AC-4, AC-5, AC-6
- [ ] `.\.venv\Scripts\pytest tests/test_dashboard_page.py` → 15 passed (100%) → AC-3, AC-6
- [ ] `.\.venv\Scripts\pytest tests/test_sankey_drilldown.py` → 9 passed (100%) → AC-3, AC-4

## Acceptance-criteria coverage
- AC-1: Covered by UI step 6 and automated tests `test_dashboard_hardening.py::test_ac1_database_connect_multi_thread_safety`, `test_ac1_dialog_database_connections_isolated`.
- AC-2: Covered by UI step 6 and `test_dashboard_hardening.py::test_ac2_set_category_budget_dialog_lifecycle`.
- AC-3: Covered by UI step 3 and `test_dashboard_hardening.py::test_ac3_render_cash_flow_sankey_pure_plotly`, `test_dashboard_page.py`.
- AC-4: Covered by UI step 4 and `test_dashboard_hardening.py::test_ac4_open_sankey_fullscreen_dialog`.
- AC-5: Covered by UI step 5 and `test_dashboard_hardening.py::test_ac5_build_investments_market_carpet_glassmorphic_styling`, `test_ac5_common_css_treemap_rounded_tiles`.
- AC-6: Covered by UI steps 1, 2 and `test_dashboard_hardening.py::test_ac6_render_accounts_grid_grouped_alphabetical_and_accents`.
