# Verify: Native Top Navigation, Sidebar Privacy Toggle, and Compact Page Layout · spec 0008 · updated 2026-10-12
_Steps derived from spec 0008 acceptance criteria. `/check verify` runs these; `/test` locks the durable ones._

## UI / manual
- [ ] Open application → Top navigation renders using native Streamlit top navigation with Material icons for all 7 pages → AC-4
- [ ] Active page displays distinct tinted pill highlight with primary accent icon, bold label, and 2px primary underline → AC-5
- [ ] Navigate between pages via top navigation tabs and browser back/forward → URL route syncs cleanly and active tab updates accurately → AC-4, AC-5
- [ ] Click top-right 3-dots actions menu → Dropdown displays Settings navigation link and Hide values toggle → AC-2
- [ ] In sidebar, check brand row at top → `:material/savings: Finance Assistant` hugs the top of the sidebar with <= 12px padding → AC-1
- [ ] Desktop viewport (>= 768px) → Sidebar collapse control is hidden, keeping sidebar permanently docked → AC-3
- [ ] Open Dashboard → Ticker displays flush directly under top navigation (<= 8px gap) with deduplicated exchange-mapped symbols → AC-7, AC-8
- [ ] Open Spending → Compact toolbar displays unified row for filters, view scope, budget, and mortgage buttons with fiscal cycle caption directly below → AC-9
- [ ] Open Transactions → Filters popover, uncategorized toggle, and search input share a single compact control row → AC-9
- [ ] Open Tax Analysis → Page opens without redundant title banner, with Edit Tax Profile right-aligned on the first row → AC-9
- [ ] Open Mortgage → Configure mortgage action button sits right-aligned on the first row → AC-9
- [ ] Open Investments → Allocation profile selector is constrained to at most one-third of the row width → AC-9

## Commands
- [ ] `.\.venv\Scripts\pytest tests/test_navigation_smoke.py` → 3 passed (100%) → AC-2, AC-4, AC-5, AC-10
- [ ] `.\.venv\Scripts\pytest tests/test_dashboard_page.py -k ticker` → passed (100%) → AC-7, AC-8
- [ ] `.\.venv\Scripts\pytest tests/test_ui_theme.py` → 18 passed (100%) → AC-5, AC-6, AC-9

## Acceptance-criteria coverage
- AC-1: Covered by UI step 5 and CSS rules zeroing `[data-testid="stSidebarHeader"]` padding in `ui/theme/common.css`.
- AC-2: Covered by UI step 4 and automated test `test_navigation_smoke.py::test_privacy_toggle_persists_across_page_navigation`.
- AC-3: Covered by UI step 6 and CSS rule hiding `[data-testid="stSidebarCollapseButton"]` at >= 768px.
- AC-4: Covered by UI steps 1, 3 and automated test `test_navigation_smoke.py::test_all_seven_pages_render_without_exception`.
- AC-5: Covered by UI steps 2, 3 and `test_navigation_smoke.py::test_top_navbar_actions_and_clutter_cleanup_css`.
- AC-6: Covered by automated smoke test verifying retirement of `top_app_bar` container and associated styles.
- AC-7: Covered by UI step 7 and `test_dashboard_page.py`.
- AC-8: Covered by UI step 7 and `test_dashboard_page.py::test_tradingview_symbols_mapping_and_deduplication`.
- AC-9: Covered by UI steps 8, 9, 10, 11, 12 and `test_ui_theme.py`.
- AC-10: Covered by automated test `test_navigation_smoke.py::test_all_seven_pages_render_without_exception`.
