# 0019. Copilot view intelligence and daily use finish

**Date**: 2026-10-14
**Status**: In Progress

## Summary

The Copilot gains view intelligence: a question about your data does not just get an answer, it takes you to the page and tab that fits and shapes that page to match (the date scope, a category, or a focused dimension such as a technology marketcarpet), then answers with the numbers. When the answer is better shown as a chart, a small Copilot panel appears on that page with the chart and a one line headline, and the page scrolls to it. Alongside the routing, the round adds seven read tools and five confirm gated write tools, and closes the app out for daily use: the known bugs, the vault and RAG fixes, a dead code prune, a warning free click through, a green test suite, and a README and screenshots that match.

## Requirements

**User stories**:
- As the app owner, I want to ask a question about a topic and land on the right page and tab, shaped to the question, so that I never hunt for the screen or set it up by hand.
- As the app owner, I want a chart answer to appear on the page I land on and scroll into view, so that I read it in full size, not only in the sidebar.
- As the app owner, I want richer answers (compare periods, budget status, balances, forecasts, income, bills, net worth trend), so that common questions do not need a follow up.
- As the app owner, I want the Copilot to change my data only after I confirm, so that a misread request cannot silently alter my ledger.
- As the app owner, I want the Copilot to stay put when it is unsure, so that a vague question does not bounce me around.
- As a reviewer or interviewer, I want the app to run warning free with a green suite and an accurate README, so the project presents as finished.

**Acceptance criteria** (the contract):

- **AC-1**: A data question routes to the page and tab that owns its topic, not only an explicit navigation phrase. One question per domain ends on the matching page (investments question lands on Investments, spending on Spending, mortgage on Mortgage, tax on Tax Analysis, transactions on Transactions, net worth or balance sheet on Dashboard). Model behavior, checked by the prompt set in **AC-14**. This extends spec 0017 **AC-1**, which only fired on explicit phrasing.
- **AC-2**: The intent also shapes the page view. Beyond the date scope (resolved by `services/date_scope.py`, spec 0017 **AC-3**), the Copilot may set a validated view parameter per page: Spending `category`; Transactions `category` and `search`; Investments `exposure_dimension` (Sector, Region, Currency, or Nature) and `focus` (a bucket of the active dimension). The Investments `tab` stays a top level argument, not a view key. On Spending the View Scope is not a view key; it is already derived from the date scope by `spending_view_for_scope`. Each value is checked against a per page whitelist and, for `focus`, against the live buckets that `get_dimension_exposure_df` returns; an unknown or invalid value is ignored with a note, never an error. The category and search values are written to the named session keys `spending_category`, `tx_category`, and `tx_search`, and the category list is sourced from the categories in the database. Two worked examples must hold: "what did I spend over the past 3 months" lands on Spending already filtered to the last 3 months; "which tech stocks and ETFs do I hold" lands on Investments with the exposure dimension on Sector and `focus` on the Technology bucket, so both the market carpet and the dimension charts are filtered to that bucket (the rest of the page is unchanged).
- **AC-3**: When the turn produced a figure, the destination page renders one dedicated Copilot panel showing that figure plus a one line headline. The headline comes from an optional `headline` field the data tool returns alongside its figure (the same number the answer text quotes), falling back to the figure title when absent. One panel is keyed by page id and rendered only by that page, replaced by the next turn, cleared on Clear Chat (which pops it together with the write token) and on any manual navigation, and never persisted across a restart. The figure is the one the turn's data tool already built; no separate chart is produced for the panel.
- **AC-4**: The page scrolls the Copilot panel into view after it renders, using `st.components.html` with a pinned container selector (plain `st.markdown` cannot run a script). If the script cannot run, the panel is placed at the top of the page so it is already visible. The user never sees an error from either path.
- **AC-5**: Routing stays quiet when it should. A weak or absent topic match answers in chat only and moves nothing. When two pages fit equally, the Copilot asks one short question naming the candidates and moves nothing until the answer arrives. A turn that navigates but produced no figure opens the page with no panel. This extends spec 0017 **AC-6**.
- **AC-6**: A deterministic topic map in `services/navigation.py` mirrors `PAGE_ALIASES` as single high signal keywords per page (investments words, spending words, mortgage, tax, transactions, net worth). It runs once after tool execution, only when no intent was captured and the model did not navigate, and sets the intent only when exactly one page matches the keywords, so a clear question lands right even if the model forgot to call `open_view`. When the match is weak or two pages tie it stays silent and the chat answer stands alone. The spec 0017 fast path is narrowed to explicit navigation verbs only (`open`, `go to`, `goto`, `navigate to`, `switch to`, `take me to`); the content verbs `show`, `show my`, `view`, and `display` are removed so a question like "show my spending over the past 3 months" reaches the model and produces an answer and a panel instead of returning instantly with nothing. Explicit navigation phrasing stays instant. When Ollama is offline the app still does not navigate (spec 0017 **AC-7** holds).
- **AC-7**: Seven read only tools exist and answer through `db.database.connect_readonly`, each returning a serializable dict with `success` and `message` and reusing a named service: `compare_periods` (the spending and cashflow tools run over two resolved ranges, plus a delta equal to range B minus range A), `get_budget_status` (`services/budget_service.py` `calculate_budget_variance` for per category budget, spent, remaining, and an over budget flag), `get_account_balances` (the accounts list and balances from the account repository), `get_spending_forecast` (`calculate_3_month_historical_burn_rate` for the euro per month burn and `calculate_12_month_runway_forecast` for the projection, with projected month end equal to the current month spent plus the burn), `get_income_summary` (transactions in income categories plus holding dividends, by period), `get_upcoming_bills` (`services/analytics.py` `detect_recurring_charges` for the recurring charges and their next due date), and `get_net_worth_history` (a monthly series rebuilt from the ledger running cash balance plus the current invested value held flat, explicitly approximate because there is no historical snapshot table).
- **AC-8**: Five write tools exist, each confirm gated: `categorize_transactions` (reuses the categorization service), `mark_as_transfer` (reuses the spec 0011 batch helper), `edit_transaction` and `delete_transaction` (reuse the transaction repository helpers), and `set_budget_cap` (reuses the budget service). The token is stateless and deterministic, a hash of the exact proposed arguments, matching the allocation delete pattern; each tool's first call returns a proposal and that token and changes nothing. The Copilot asks you to confirm, and on your yes it calls the tool again with the token to perform the write, exactly as allocation delete works. No write happens without a valid token; a token whose arguments no longer match what is proposed is refused with a note.
- **AC-9**: With Hide values on, the Copilot panel headline is masked and the panel figure is masked by one shared figure masking helper (there is no such helper today). Money axes are replaced with `****` so the panel cannot leak the number the headline hides, while tickers, asset names, counts, and percentages stay readable, exactly as spec 0017 **AC-8** defines for the rest of the app.
- **AC-10**: The named finish items are closed: the donut label crowding and the collapsed by default open banking guide (spec 0016 nits); the vault first load race (spec 0017); the RAG path embedding with a real embedding model instead of the chat model (spec 0017); the per session auto sync duplication and the stale PSD2 account references (spec 0017); and a dead code prune of orphan routines from the 0014 to 0016 rounds.
- **AC-11**: Every page renders with zero Streamlit deprecation warnings and zero console errors on a full click through.
- **AC-12**: The full suite in `run_tests.py` passes, and the test count recorded in the README equals the live suite count.
- **AC-13**: The README and screenshots match the finished app, including the architecture and local first privacy section, and the native tool count equals `len(COPILOT_TOOLS_SCHEMA)`. Screenshots are captured in demo mode (`PFA_DEMO=1`) with Hide values OFF, so the tickers, balances, charts, and tables all read; the README's masking note and its test count line are updated to match. Demo mode starts with Hide values OFF, so a fresh demo session reads without a manual toggle.
- **AC-14**: A fake model harness emits scripted tool calls, so routing, view parameter validation, panel placement, confirm tokens, and once only consumption are asserted with no Ollama, using a fixed seed for determinism. It also drives the **AC-1**, **AC-2**, and **AC-5** prompt set (one question per domain, six of six domains passing). This extends spec 0017 **AC-22**.
- **AC-15**: No database change, no new dependency, no new environment variable. The read only SQL authorizer stays in force for every query tool.

## Decision

**Chosen option**: Option 1, extend the spec 0017 action layer rather than replace it.

The model leads routing and view shaping through an extended `open_view` tool (it gains validated view parameters), with a deterministic topic map as a fallback when the model omits the call and the fast path narrowed to explicit navigation verbs. The page panel reuses the figure the turn already built and the data tool's `headline`, rendered by one shared UI module keyed by page id and scrolled into view with `st.components.html` and a top placement fallback. New tools are added to the same schema and dispatch map, writes go through a stateless args hash confirmation token, and the finish items are closed in one pass.

**Implementation skills**: none used. No community skill relevant to this decision is installed for this area. The Streamlit skill (`developing-with-streamlit`) is installed but its conventions are already reflected in `ui/AGENTS.md`; it did not change this decision.

## Feature design

**Data model sketch**: no schema change. The model is a session state contract that carries intent from the assistant thread to the page renderer, at two levels.

| State key | Type | Set by | Read by | Notes |
|---|---|---|---|---|
| `task.ui_intent` | dict | the `open_view` tool, the fast path, or the topic map, on the `CopilotTask` | `ui/copilot_sidebar.py` on turn completion | Never written to `st.session_state` from the worker thread |
| `copilot_ui_intent` | dict | the sidebar, on completion, under the task lock | `app.py` | `{page, tab, date_scope, view, panel, source}`. Consumed once, then cleared (spec 0017 **AC-19**) |
| `copilot_page_panel` | dict | the sidebar, on completion | the shared page panel renderer | `{page, figure, headline}` keyed by page id. Not persisted; cleared on Clear Chat and on manual navigation |

`view` carries only the keys the destination page whitelists, so a wrong key never reaches a page:

| Page | Whitelisted `view` keys |
|---|---|
| `spending` | `category` |
| `transactions` | `category`, `search` |
| `investments` | `exposure_dimension` (Sector, Region, Currency, Nature), `focus` (a live bucket of the active dimension, from `get_dimension_exposure_df`) |
| `dashboard`, `mortgage`, `tax`, `settings` | none |

The Investments `tab` stays a top level intent argument (spec 0017 **AC-2**), not a view key. Spending View Scope is derived from the date scope by `spending_view_for_scope`, so it is not a view key either.

**State transitions**: an intent moves `created` (on the task) to `committed` (session state, on turn completion) to `consumed` (read and applied, spec 0017 **AC-19**). A panel moves `set` to `rendered` to `replaced` on the next turn or `cleared` on Clear Chat or a manual navigation. A write token is stateless: it is a hash of the exact proposed args, so it is `valid` while the proposed args match and `refused` when they do not.

**API surface** (the Copilot tool surface; the model chooses the tool, each function validates and acts):

| Tool | Kind | Key inputs | Key outputs | Safety |
|---|---|---|---|---|
| `open_view` (extended) | read (sets the task intent only) | `page`, `tab`, `date_scope`, `view` (object) | success, resolved page, tab, scope, and view; a note for an ignored value | page, tab, and every `view` key checked against the whitelist; unknown key or value ignored with a note; never writes SQL |
| `compare_periods` | read | `range_a`, `range_b` (each a `date_scope`) | both totals plus the delta | read only |
| `get_budget_status` | read | `date_scope` (optional) | per category budget, spent, remaining, over flag | read only |
| `get_account_balances` | read | none | account list with balances | read only |
| `get_spending_forecast` | read | none | burn rate, projected month end | read only |
| `get_income_summary` | read | `date_scope` (optional) | salary and dividend income by period | read only |
| `get_upcoming_bills` | read | none | recurring charges and next due dates | read only |
| `get_net_worth_history` | read | `date_scope` (optional) | net worth series | read only |
| `categorize_transactions` | write | `category`, `transaction_ids` or a filter; `confirm_token` on the second call | proposal plus token, then result | confirm gated (stateless args hash token); writes through named helpers only |
| `mark_as_transfer` | write | `transaction_ids`; `confirm_token` | proposal plus token, then result | confirm gated; reuses the spec 0011 batch helper |
| `edit_transaction` | write | `transaction_id`, `category` or `description`; `confirm_token` | proposal plus token, then result | confirm gated; reuses the transaction repository |
| `set_budget_cap` | write | `category`, `cap_eur`; `confirm_token` | proposal plus token, then result | confirm gated; reuses the budget service |
| `delete_transaction` | write | `transaction_id`; `confirm_token` | proposal plus token, then result | confirm gated; destructive; reuses the transaction repository |

**Value sourcing** (every value a criterion needs names its source):

| Action | Value produced / displayed | Source |
|---|---|---|
| Route | Destination page | `open_view` `page` argument or the topic map, checked against `PAGE_IDS` in `services/navigation.py` |
| Route | Destination tab | `tab` argument, checked against `TAB_MAP` |
| Shape view | Date scope | `services/date_scope.py` `resolve_date_scope` (single resolver, spec 0017 **AC-3**) |
| Shape view | Spending `category` | `view` argument, checked against the Spending whitelist, written to `spending_category`; view scope derived from the date scope by `spending_view_for_scope` |
| Shape view | Transactions `category`, `search` | `view` argument, checked against the Transactions whitelist, written to `tx_category` and `tx_search` |
| Shape view | Investments `exposure_dimension`, `focus` | `view` argument, dimension checked against Sector / Region / Currency / Nature and `focus` against the live buckets from `get_dimension_exposure_df`; both filter the market carpet and the dimension charts |
| Panel | Chart figure | the turn's captured figure (`agent/copilot.py`), already produced by the data tool; none when no tool produced one |
| Panel | Headline line | the data tool's optional `headline` field captured alongside the figure, else the figure title |
| Panel | Scroll target element | the pinned container selector of the shared panel renderer, scrolled by `st.components.html` |
| Budget status | Budget, spent, remaining | `services/budget_service.py` `calculate_budget_variance` |
| Forecast | Burn rate, projected month end | `services/budget_service.py` `calculate_3_month_historical_burn_rate`, `calculate_12_month_runway_forecast` |
| Upcoming bills | Recurring charges, next due | `services/analytics.py` `detect_recurring_charges` |
| Account balances | Account list, balances | `db/` account repository via `connect_readonly` |
| Net worth history | Series | a monthly series rebuilt from the ledger running cash balance (`account_snapshots` where present, else the transaction sum) plus the current invested value held flat; approximate, no schema change |
| Income summary | Salary and dividend income | transactions in income categories, plus holding dividends |
| Compare periods | Two totals, delta | the existing spending and cashflow tools run over two resolved ranges; delta is B minus A |
| Write confirm | Confirmation token | a deterministic hash of the exact proposed args, computed in the write tool (stateless, the allocation delete pattern) |
| README stats | Test count, tool count | the live `run_tests.py` run and `len(COPILOT_TOOLS_SCHEMA)` |

**Key invariants**:
- The model may set a page, a tab, a date scope, and whitelisted view parameters; it may never emit SQL, and it may never set a value outside the whitelist.
- A chart reaches the panel only from the turn's captured figure, and the headline only from the data tool's `headline` field; the panel never builds its own query.
- An intent is applied exactly once; a manual page or view change afterward is the new truth.
- A write happens only with a valid confirmation token, which is a hash of the exact proposed args; a query tool stays read only under the enforced authorizer.
- With Hide values on, money is masked at every display boundary including the panel headline and masked money axes; identifiers and percentages are never masked.
- The panel is keyed by page id and ephemeral; it is cleared on Clear Chat and on manual navigation and never persisted.

**Security model**: single local user, no authentication surface. The trust boundary that matters is the model, and the action surface is a whitelist at two levels (page and tab, and per page view parameters), so a malformed call cannot reach a value the app does not already offer. Writes are the only mutations and are doubly gated: a named tool plus a confirmation token that only matches the exact proposed args, so the write runs only after you say yes in chat and the model calls back with the token, the same model mediated pattern as allocation delete. Unknown destinations or values are ignored with a note rather than raising.

**Configuration required**: none.

**Critical test scenarios** (each maps to an acceptance criterion):
- Happy path, routing: the **AC-14** prompt set, one question per domain, ends on the matching page, verifies **AC-1**.
- Happy path, view: "past 3 months spending" lands on Spending filtered to 3 months; "tech stocks and ETFs" lands on Investments focused on the Technology bucket, verifies **AC-2**.
- Happy path, panel: a chart producing question shows one panel with the figure and headline on the destination page and scrolls to it, verifies **AC-3**, **AC-4**.
- Fallback: with the script blocked the panel still appears at the top, verifies **AC-4**.
- Quiet cases: a vague question answers with no move; two tied pages asks one question; a navigate with no figure opens the page with no panel, verifies **AC-5**.
- Fallback routing: the model omits `open_view` on a clear question and the topic map still routes; a "show my ..." content question reaches the model (not the fast path) and produces an answer and a panel; explicit "open spending" stays instant; offline does not navigate, verifies **AC-6**.
- Read tools: each of the seven returns a success dict on seeded data, with the named source, verifies **AC-7**.
- Write tools: a first call proposes and changes nothing; the second with the token applies; a token whose args no longer match is refused, verifies **AC-8**.
- Privacy: with Hide values on, the panel headline and chart mask euro and dollar amounts while tickers, names, counts, and percentages stay readable, verifies **AC-9**.
- Finish: the named bugs are gone, the vault lists statutes on first load, the RAG path embeds with the embedding model, sync does not duplicate per session, stale references are handled, verifies **AC-10**.
- Clean render: a full click through shows no warnings and no console errors, verifies **AC-11**.
- Suite and docs: `run_tests.py` passes and the README count matches; screenshots and tool count match the app, verifies **AC-12**, **AC-13**.
- Harness: the fake model harness drives routing, view validation, panel placement, and confirm tokens with no Ollama, verifies **AC-14**.
- Constraint: no schema change, no new dependency; a literal grep of the authorizer path is unchanged, verifies **AC-15**.

## Build plan

Order follows the project's Tracer Bullet approach: one thin end to end thread first (a single topic question routes to one page, shapes one view, and lands one panel), then thicken across pages, then the tools, then the finish pass and the regression net.

1. **Intent and whitelist extension**: extend `open_view` (schema and function) with `view`; add the per page view parameter whitelist, the single high signal keyword topic map, and the narrowed fast path verbs (`open`, `go to`, `goto`, `navigate to`, `switch to`, `take me to`) to `services/navigation.py`; validate every key and ignore unknowns with a note; run the topic map after execution only when no intent was captured. Satisfies **AC-1**, **AC-2**, **AC-6**.
2. **Shared page panel and scroll**: one `ui/` module renders the Copilot panel (figure plus the data tool `headline`, masked) as the first element of a page when `copilot_page_panel` matches that page id, and scrolls to it with `st.components.html` and a pinned selector, with a top placement fallback; add the shared figure masking helper; commit the panel in the sidebar on completion under the lock and clear it on Clear Chat and manual navigation. Satisfies **AC-3**, **AC-4**, **AC-9**.
3. **Wire the view into the pages**: Spending consumes `category` (view scope stays derived from the date scope); Transactions consumes `category` and `search`; Investments consumes `exposure_dimension` and `focus`, filtering the market carpet and the dimension charts to the focused bucket. Satisfies **AC-2**.
4. **Model behavior**: relax the system prompt so a topic question calls `open_view` with the view, keep the ambiguous case asking one question, and route through the deterministic topic map when the model omits the call. Satisfies **AC-1**, **AC-5**, **AC-6**.
5. **Seven read tools**: add each function and schema with its named source (budget variance, burn rate and runway, recurring charges, account repository, income and dividends, ledger net worth series, two range comparison) and map them in the dispatch table. Satisfies **AC-7**.
6. **Five write tools**: add each with the stateless args hash confirmation token, reusing the categorization service, the spec 0011 batch helper for transfers, the transaction repository for edit and delete, and the budget service for caps. Satisfies **AC-8**.
7. **Finish pass, code**: donut label crowding, the collapsed by default open banking guide, the vault first load race, the RAG embedding model, sync dedupe and stale reference handling, and the dead code prune. Satisfies **AC-10**.
8. **Warning free and suite**: clear every Streamlit warning and console error, and get `run_tests.py` green. Satisfies **AC-11**, **AC-12**.
9. **Presentation**: refresh the README (architecture and privacy section, corrected test and tool counts, and the masking note to match Hide values OFF in demo mode), make demo mode start with Hide values OFF, and re-shoot the screenshots in demo mode with Hide values OFF. Satisfies **AC-12**, **AC-13**.
10. **Regression net**: extend the fake model harness, add the routing and view prompt set, and unit test the whitelist, the topic map, the panel placement, the confirm tokens, and the read tools. Satisfies **AC-7**, **AC-8**, **AC-14**, **AC-15**.

## Consequences

**Positive**:
- The Copilot becomes a true control surface: it takes you to the exact view that answers the question, which is the single most demoable behavior and the biggest daily use win.
- Reusing the turn's figure for the panel means a chart answer costs no extra query and cannot disagree with the chat answer.
- The read tools close the common follow up gaps (compare, budget, balances, forecast, income, bills, trend) so most questions end in one turn.
- The confirm gated writes let the Copilot help maintain the ledger without risking a silent change.
- The finish pass turns a strong prototype into something that runs clean and shows accurately.

**Negative / tradeoffs**:
- Routing and view shaping stay model behavior for the fuzzy cases; the harness and the prompt set measure them but cannot make a 7B model perfect.
- Content routing is more assertive than spec 0017's explicit only behavior, so a poorly worded question can occasionally land on a page you did not want; the ask when tied rule and the no move when weak rule limit this.
- The scroll uses `st.components.html` and a pinned selector, which can be blocked or break on a Streamlit change; the top placement fallback keeps the panel usable.
- Per page view parameters are more surface to keep valid and tested as pages change.
- The finish items (vault, RAG, sync) are independent of the routing decision and add breadth to one round; they are small but not trivial.

**Neutral**:
- No database change, no migration, no new dependency, no new environment variable.
- This round builds on spec 0017, which is built but not yet verified; verifying this feature exercises the 0017 behavior it extends, so 0017 should be verified in the same pass.
- The panel is a new session state key, per session, reverting on restart, like the spec 0017 intent; the write token is stateless, so it adds no state.
- Runtime verify of spec 0017 (2026-10-14) confirmed the failure this round exists to fix: the deterministic fast path matched content verbs and short circuited questions meant for the model, and the model did not open the page for a scope question. Tasks 1 (narrow the fast path) and 4 (content routing) close both.

## Follow-up

- [ ] Enroll this round as a scope feature (`docs/scope/scope.md`), the next slice after spec 0017, so its status becomes feature mirrored and the build plan lands in the scope row. `/scope` owns that file.
- [x] Verify spec 0017 in the same pass. Runtime verify (demo mode, Hide values off) on 2026-10-14 returned FAIL: the fast path hijacked content questions (AC-4 and AC-5 prompts returned "Opening ..." with no note and no inline chart), the model answered a scope question with the right numbers but did not open the page (AC-3), and the ambiguity prompt answered instead of asking (AC-6). Met: AC-2, AC-10, AC-11, AC-12, AC-17, AC-21, AC-22, and AC-13 in substance. Tasks 1 and 4 of this spec fix exactly the routing failures; the 0017 scope Verify box stays unticked.
- [ ] Memo to `/sync`: `ui/AGENTS.md` and `agent/AGENTS.md` gain the view intelligence (the extended `open_view`, the topic map, the page panel, and the write token), and the tool count in `agent/AGENTS.md` moves.
- [ ] Deferred and still open: Copilot turn latency on CPU (30 to 60 seconds for a 7B model); a larger tool calling model or two stage routing remains a separate decision (specs 0016 and 0017).
- [ ] Deferred: memory recycling on heavy pages (spec 0018), until resident memory is measured.

## Rationale

Reasoning, the options weighed, and the flow this builds on are recorded in [rationale.md](rationale.md).
