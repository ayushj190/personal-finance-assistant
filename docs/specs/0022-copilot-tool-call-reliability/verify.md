# Verify: Copilot tool call reliability and grounded answers · spec 0022 · updated 2026-10-14
_Steps derived from spec 0022 acceptance criteria. `/check verify` runs these; `/test` locks the durable ones._

## UI / manual
- [ ] Ask "Show my spending for the past 3 months." → the answer quotes a burn rate and projected month end, the Spending page opens scoped to that window, and its chart panel is up → AC-1, AC-4
- [ ] Ask a period question whose answer tool does not accept a period (for example "what is my net worth this month") → the tool still runs, the turn is not marked failed, and the sidebar diagnostics expander shows a `DroppedArgument` warning → AC-3
- [ ] Ask a topic question where only navigation runs (for example "what is my portfolio allocation" with no data tool result) → the page opens and the chat answer states no money amount or percentage (replaced by the deterministic fallback) → AC-5, AC-4
- [ ] Ask "how has my net worth changed" → the answer says the trend is approximate (ledger cash plus the current invested value), excludes home equity and opening balances, and points to the true current figure → AC-6

## Commands
- [ ] `.\.venv\Scripts\python.exe run_tests.py tests/test_copilot_tool_reliability.py -q` → 17 passed → AC-1, AC-2, AC-3, AC-4, AC-5, AC-6, AC-7
- [ ] `.\.venv\Scripts\python.exe run_tests.py -q` → 328 passed → AC-7

## Value sourcing checks
- [ ] Ask the spending forecast with no period, then with "last month" → the two answers report different windows (`over the last 3 months` versus the resolved range) and different `months_count`, proving the window comes from `services/date_scope.py` and the fallback from the trailing three months → AC-1
- [ ] Pass a period to a tool that does not declare one (net worth), then pass a different unknown argument → the first is dropped and the tool runs; the second still returns the guided `UnknownArgumentError` → AC-3
- [ ] A grounded turn (a data tool succeeded) whose answer states a figure keeps the figure; an ungrounded turn whose answer states a figure is replaced → AC-5
- [ ] Explicit navigation phrasing ("open spending"), a content question ("what did I spend"), and a model `open_view` each land the page; a failing data tool still lands the page; an invalid scope ("whenever") attaches no scope → AC-4

## Acceptance-criteria coverage
- AC-1 … covered by the forecast window command and the value sourcing check · AC-2 … covered by the prompt test and the reliability suite · AC-3 … covered by the dropped argument manual step and command · AC-4 … covered by the navigation steps · AC-5 … covered by the grounding manual step · AC-6 … covered by the net worth manual step · AC-7 … covered by the full-suite command
