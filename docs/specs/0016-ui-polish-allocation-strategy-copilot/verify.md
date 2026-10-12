# Verify: UI polish, allocation strategy management, and copilot hardening · spec 0016 · updated 2026-10-12

_Steps derived from spec 0016 acceptance criteria. `/check verify` runs these; `/test` locks the durable ones._

## UI / manual

- [ ] Load the Dashboard on a viewport 1280px wide or wider → the vertical distance from the bottom of the top navigation bar to the top of the ticker tape is 8px or less → AC-1
- [ ] Load the Dashboard → the order is ticker tape, 4 KPI cards, the Expenses and Portfolio exposure panels, then Accounts and Balances → AC-2
- [ ] On Investments Holdings, toggle Hide values on → no KPI row changes height (every card in a row keeps one height with or without a delta) → AC-3
- [ ] Open Spending → the Spending by Category panel and the Subscription Leak Detector panel start at the same top and end at the same bottom → AC-4
- [ ] On Spending, the Top Merchants panel spans the full content width of the page → AC-5
- [ ] Each Top Merchants row shows merchant, location, category (with parent when it differs), transaction count, average per visit, total spent, share of scope, last transaction date, and the accounts used → AC-6
- [ ] Switch the Spending scope to All Months (Monthly Average) → each row's total and share use the monthly average total, and the shares sum to about 100 percent → AC-6
- [ ] On a database with no counterparty IBANs, open Spending → the Location column and the spend by location bar are absent, not empty → AC-7
- [ ] Open Investments Holdings → one row per distinct asset (grouped by ticker), quantity, cost basis, value, and unrealized profit summed across lots, copied traders still listed under their own `COPY:` key, and there is no Status column → AC-8
- [ ] Set one holding to a second currency and reopen Holdings → the average open price column header becomes `Avg Open (EUR)` → AC-8
- [ ] Open Investments → the standalone live quotes table above the watchlist is gone and `VWCE.DE` renders as the `XETR:VWCE` quote → AC-9
- [ ] With Hide values on, confirm quotes, ticker symbols, and public instrument percentages stay readable while balances, cost basis, position values, and personal percentages stay masked → AC-10
- [ ] In Settings under Target Allocations, create a strategy (drift band defaults to 5, no cash bucket, every bucket needs a percent, not auto activated), see it appear, then delete it with the confirmation → AC-11
- [ ] Repeat the create and delete from the Investments allocation panel → AC-11
- [ ] Ask the Copilot for a strategy whose targets sum to 90 percent → it names the sum, writes nothing, and a duplicate name is refused case insensitively → AC-12
- [ ] Ask the Copilot to delete the active profile, then the last remaining profile, then delete with a missing or stale token → all three are refused with the reason → AC-13
- [ ] Ask the Copilot about mortgage interest → the answer quotes euros matching the schedule, never cents → AC-15, AC-17 note below
- [ ] Ask the Copilot to get spending by category with a category → it returns that category; call a tool with an unknown argument and confirm a guided error rather than a crash → AC-16
- [ ] With Ollama running, have one Copilot turn → after the stream ends, a footer shows the total time and the model name → AC-17
- [ ] Grep `ui/theme/common.css` for a repeated rule block; confirm `ui/utils/masking.py` is gone and `ui/AGENTS.md` points at the `ui/pages/investments/` package → AC-18, AC-19

## Commands

- [ ] `.venv\Scripts\python.exe -m pytest tests/ -q` → all tests pass (230 passed) → AC-14, and the regression net for AC-6, AC-7, AC-8, AC-12, AC-13, AC-15
- [ ] `.venv\Scripts\python.exe -m pytest tests/test_prompt_fixture.py tests/test_allocation_service.py tests/test_top_merchants.py tests/test_holdings_aggregation.py -q` → 15 passed, checking the prompt fixture, the allocation token, merchant location, distinct asset aggregation, and mortgage formatting → AC-14, AC-12, AC-13, AC-7, AC-8, AC-15
- [ ] The live Copilot model run (real latency, footer time, and prompt phrasing) stays a manual step: run the eight fixture prompts against a running Ollama and record turn times → AC-14, AC-17

## Acceptance-criteria coverage

- AC-1, AC-2, AC-3 covered by the Dashboard and KPI steps
- AC-4, AC-5, AC-6, AC-7 covered by the Spending steps
- AC-8, AC-9, AC-10 covered by the Investments and privacy steps
- AC-11 covered by the Settings and Investments allocation steps
- AC-12, AC-13 covered by the Copilot create and delete steps and the allocation service command
- AC-14 covered by the prompt fixture command
- AC-15 covered by the mortgage euro step and command
- AC-16 covered by the tool argument step
- AC-17 covered by the Copilot footer step (manual live run noted)
- AC-18, AC-19 covered by the cleanup step
