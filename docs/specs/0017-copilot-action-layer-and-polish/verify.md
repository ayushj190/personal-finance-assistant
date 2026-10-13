# Verify: copilot action layer & daily use release polish · spec 0017 · updated 2026-10-13

_Steps derived from spec 0017 acceptance criteria. `/check verify` runs these; `/test` locks the durable ones._

## UI / manual
- [ ] Ask "open spending" → landing on Spending with no model wait → AC-21
- [ ] Ask one prompt per page (dashboard, spending, investments, mortgage, transactions, tax, "settings") → the matching page ends active → AC-1
- [ ] Ask "go to rebalancing" → Investments with the Allocation and Drift tab selected → AC-2
- [ ] Ask "what did I spend last month" → Spending opens already filtered to the previous calendar month and the chat number matches the page range → AC-3
- [ ] Ask "show my investments for last month" → Investments opens and the chat says the page has no date scope → AC-4
- [ ] Ask "show my spending for the past 3 months" → the inline chart shows and Spending selects "All Months (Monthly Average)" → AC-5
- [ ] Ask "show me the last thing" → the Copilot asks which screen and nothing moves → AC-6
- [ ] Stop Ollama, then ask a question → the current page does not change; Clear Chat while a turn runs drops any pending move → AC-7
- [ ] Turn Hide values on → money reads `€****`, while tickers, merchant names, categories, percentages, counts, and chart axes stay readable; the same holds in chat and in tables → AC-8
- [ ] Click each of the six sidebar navigation chips → the page and scope open with no model call; the chips are disabled while a turn runs → AC-9
- [ ] In demo mode (`PFA_DEMO=1`) → the app starts on seeded data and the demo prompt chips show and run → AC-17
- [ ] Open a page with charts → a skeleton shows before the plot mounts → AC-14
- [ ] Scroll to the bottom of any page → no more than 48 px of dead space → AC-15
- [ ] Ask the Copilot to open an unknown page, or a hand written tool call with a bad page → a guided error and no move → AC-18
- [ ] After a navigate, change the page by hand, then rerun → the move does not replay → AC-19
- [ ] On Spending, a previous month shows a month name (for example "September 2026") with a range aligned to that fiscal month → AC-11
- [ ] The crypto ticker shows the instrument price and change, not market cap → AC-12
- [ ] Visit `/dashboard` → no "Page not found"; the app root serves the Dashboard → AC-13

## Commands
- [ ] `.\.venv\Scripts\pytest.exe` → 260 passed → AC-22
- [ ] `python run_tests.py` → the same suite passes → AC-22
- [ ] Import and run the app: `.\.venv\Scripts\streamlit.exe run app.py` → renders with no Streamlit deprecation warning → AC-10
- [ ] `git grep -n "use_container_width"` and `git grep -n "st.components.v1.html"` → no matches → AC-10
- [ ] `.\.venv\Scripts\python.exe -c "from agent.tool_schemas import COPILOT_TOOLS_SCHEMA as S; print(len(S))"` → 28 → AC-16

## Acceptance-criteria coverage
- AC-1 covered by the per page prompt step · AC-2 by the tab prompt step · AC-3 by the scope step and the resolver unit tests · AC-4 by the no scope step · AC-5 by the chart step · AC-6 by the ambiguity step · AC-7 by the offline and Clear Chat step · AC-8 by the masking step · AC-9 by the chip step · AC-10 by the commands · AC-11 to AC-13 by the bug steps · AC-14 and AC-15 by the polish steps · AC-16 by the command and the README review · AC-17 by the demo step · AC-18 to AC-19 by the intent steps and `tests/test_copilot_action_layer.py` · AC-20 by the README architecture section · AC-21 by the fast path step · AC-22 by the harness in `tests/test_copilot_action_layer.py`.
