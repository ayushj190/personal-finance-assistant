# Verify: Copilot Layout Scroll and Calculation Single Source of Truth · spec 0009 · updated 2026-10-12
_Steps derived from spec 0009 acceptance criteria. `/check verify` runs these; `/test` locks the durable ones._

## UI / manual
- [ ] Open Copilot sidebar → Viewport height is constrained to 100vh with chat input pinned to bottom → AC-1
- [ ] Send lengthy queries generating multiline responses or diagnostic traces → Chat history scrolls smoothly inside `.st-key-copilot_chat_history` without pushing input widget off screen or causing page container jumpiness → AC-2
- [ ] Run quick action or ask Copilot "Review my investments" → Assistant executes `tool_analyze_investments` and reports total portfolio values and cash balances in formatted euros matching Investments dashboard → AC-3, AC-4
- [ ] Inspect Copilot portfolio analysis payload → Bucket allocations, individual holding positions, active profile targets, and drift alerts match calculation output from `services/portfolio.py` → AC-5
- [ ] On an empty database without imported statements → Copilot returns structured empty dataset guidance advising account setup and statement ingestion → AC-6

## Commands
- [ ] `.\.venv\Scripts\pytest tests/test_copilot_sidebar.py` → 5 passed (100%) → AC-1, AC-2
- [ ] `.\.venv\Scripts\pytest tests/test_copilot_tools.py -k test_portfolio_summary_and_drift_single_source` → 1 passed (100%) → AC-3, AC-4, AC-5
- [ ] `.\.venv\Scripts\pytest tests/test_copilot_tools.py -k test_analyze_investments_empty_state_guidance` → 1 passed (100%) → AC-6

## Acceptance-criteria coverage
- AC-1: Covered by UI step 1 and CSS rules for `.stSidebar` flexbox layout in `ui/theme/common.css`.
- AC-2: Covered by UI step 2 and automated test `test_copilot_sidebar.py::test_chat_container_scrolling_css`.
- AC-3: Covered by UI steps 3, 4 and automated test `test_copilot_tools.py::test_portfolio_summary_and_drift_single_source`.
- AC-4: Covered by UI step 3 and automated test `test_copilot_tools.py::test_portfolio_summary_and_drift_single_source`.
- AC-5: Covered by UI step 4 and automated test `test_copilot_tools.py::test_portfolio_summary_and_drift_single_source`.
- AC-6: Covered by UI step 5 and automated test `test_copilot_tools.py::test_analyze_investments_empty_state_guidance`.
