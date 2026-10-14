# Verify: Copilot view intelligence and daily use finish · spec 0019 · updated 2026-10-14

_Steps derived from spec 0019 acceptance criteria. `/check verify` runs these; `/test` locks the durable ones._

_Build state: all ten build plan tasks have landed. The finish pass is complete (the vault, RAG, sync, stale PSD2 reference, donut label and open banking guide items landed earlier; the dead code prune removes `db/repository.py` and eight orphan routines). The full click through renders with no Streamlit warning and no console error, `run_tests.py` is green at 298, the README counts and the seven screenshots are refreshed in demo mode with Hide values off, and two layout defects were fixed along the way (content cropped at the bottom of a scrolled page, and page controls sitting too close to the top navigation bar). Nothing in the build is outstanding; `/check verify` and `/test` have not run yet._

## UI / manual

- [ ] Ask "what did I spend over the past 3 months" → lands on Spending filtered to the last 3 months, with one Copilot panel showing the chart and a headline, scrolled into view → AC-2, AC-3, AC-4
- [ ] Ask "which tech stocks and ETFs do I hold" → lands on Investments with the exposure dimension on Sector and focus on the Technology bucket, so the market carpet and the dimension charts are filtered to that bucket → AC-2
- [ ] Ask "open spending" → opens instantly with no model call → AC-6
- [ ] Ask "show me my spending for last month" → reaches the model, answers with numbers, and shows a panel (not an instant "Opening ...") → AC-6
- [ ] Ask a vague question ("hello") → answers in chat and moves nothing → AC-5
- [ ] With Hide values on → the panel headline and the panel chart mask euro amounts, while tickers, asset names, counts, and percentages stay readable → AC-9
- [ ] Ask "compare this month to last month" → returns a compare figure and a panel, and the delta equals range B minus range A → AC-7
- [ ] Ask "categorize my uncategorized transactions as Groceries" → proposes and returns a confirmation token, changes nothing until you confirm, then applies; asking again with a changed argument and the old token is refused → AC-8
- [ ] Open Tax Analysis → the law vault lists statutes on first load (greater than zero) → AC-10
- [ ] Navigate away from a page that has a panel → the panel is cleared → AC-3
- [ ] Open Settings → the Open Banking credentials setup guide is collapsed by default → AC-10
- [ ] On any long page (Spending, Tax, Investments), scroll to the very bottom → the last panel or table is fully visible with a small gap below it, nothing cut off → AC-11
- [ ] Open Spending and Transactions → the filter and category control row sits a small gap below the top navigation bar, not jammed against it → AC-11
- [ ] Read the README screenshots → every amount, ticker, and table value reads (captured in demo mode with Hide values off), and the masking note matches → AC-13

## Commands

- [ ] `.\.venv\Scripts\python.exe -m pytest tests/ -q` → 298 passed → AC-12, AC-14
- [ ] `.\.venv\Scripts\python.exe -c "from agent.tool_schemas import COPILOT_TOOLS_SCHEMA as S; print(len(S))"` → 40, equal to every tool count in the README → AC-13
- [ ] `git diff db/database.py` → the read only authorizer path is unchanged and every query tool still opens `connect_readonly` → AC-15
- [ ] `.\.venv\Scripts\python.exe -m vulture agent services db ui connectors app.py --min-confidence 100 --exclude "tests,.venv"` → only the two required authorizer callback parameters are reported → AC-10
- [ ] `PFA_DEMO=1` then a full click through of all seven pages → no Streamlit deprecation warning in the server log and no console error in the browser → AC-11

## Acceptance-criteria coverage

- AC-1 … covered by the topic map and routing steps (see the content prompt set) · AC-2 … the two worked examples · AC-3 … the panel step and the panel cleared step · AC-4 … the scroll step · AC-5 … the vague question step · AC-6 … the fast path and the "show me" step · AC-7 … the compare step · AC-8 … the confirm step · AC-9 … the Hide values step · AC-10 … the vault step, the open banking guide step, and the vulture command · AC-11 … the bottom scroll step, the top spacing step, and the click through command · AC-12 … the suite command · AC-13 … the tool count command and the screenshots step · AC-14 … the suite command · AC-15 … the authorizer command
