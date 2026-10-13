# 0017. Copilot action layer and daily use release polish

**Date**: 2026-10-13
**Status**: In Progress

## Summary

Today the local Copilot can answer questions and draw one chart inside its sidebar, but it cannot touch the app. This round gives it an action layer: it can open any page, open a tab inside a page, and apply the date scope you asked for, so a question like "what are my expenses for the past 3 months" lands you on Spending, already filtered, with the page's own charts up, while the sidebar still answers with the numbers and a mini chart. A small deterministic fast path handles explicit phrasing instantly, and the model handles the fuzzy cases. Alongside it, this round fixes the defects that block daily use and a good screenshot: the privacy mask now hides money only (not tickers, merchant names, or percentages), the deprecated Streamlit calls are replaced before they break, and a short list of small bugs is closed. The result is an app that is pleasant to use every day and worth showing in an interview.

## Requirements

**User stories**:
- As the app owner, I want to ask a question in plain language and be taken to the right screen, already filtered, so that I do not hunt for the page and set the period by hand.
- As the app owner, I want the Copilot to open a specific tab, so that "show my rebalancing" goes straight to the Allocation and Drift tab.
- As the app owner, I want the answer in chat and the page I land on to use the same date scope, so the number and the chart never disagree.
- As the app owner, I want explicit navigation phrasing to be instant, so the demo never waits on the model.
- As the app owner, I want the Copilot to be honest when it cannot help, so that a failed turn never moves me somewhere unexpected.
- As the app owner, I want the privacy mask to hide money and nothing else, so that charts and tables still read while my balances stay hidden.
- As the app owner, I want the app to run warning free on the installed Streamlit, so a routine upgrade does not break every page.
- As a reviewer or interviewer, I want a README and screenshots that match the running app, so the project presents accurately.

**Acceptance criteria** (the contract):

- **AC-1**: A Copilot request that names a destination opens that page. One prompt per page ends with the matching page active, for the ids `dashboard`, `spending`, `investments`, `mortgage`, `transactions`, `tax`, `settings`. Aliases resolve too, including "tax analysis" to `tax` and "holdings" or "portfolio" to `investments`. Settings is a hidden page but is still reachable. This is a model behavior criterion; it is checked by the prompt set in **AC-22**.
- **AC-2**: A request that names a tab opens the page with that tab selected. Tab ids are `portfolio`, `allocation`, `income_tax`, `goals`, mapped to the four Investments labels (Portfolio and Holdings, Allocation and Drift, Income and Tax Strategy, Goals and Planning). A `tab` given for a page with no tabs is ignored with a note, not an error. Model behavior; checked by the prompt set in **AC-22**.
- **AC-3**: A date scope in the request is applied to both the answer and the opened page from one shared resolver, so the number quoted in chat and the range the page shows agree. The resolver accepts the six presets (Last 3 Months, MTD, Last Month, YTD, Last 12 Months, All Time), an explicit range, or a day window such as "past 90 days". Rules: presets resolve exactly as `ui/filters.py` computes them today; an explicit range resolves to the most recent past occurrence of the named months with the end at month end; the resolver validates `start <= end` and clamps future dates; an unknown phrase falls back to the model supplying `start` and `end`; `date_scope` wins over a tool's existing `year` or `month` argument and both together is a validation error; the month grained cashflow tool snaps a non aligned range to whole months and says so. `today` is an injectable argument so tests are deterministic. "Last month" resolves to the previous calendar month. This closes audit item 2.9.
- **AC-4**: The pages that have no date filter are `dashboard`, `investments`, `mortgage`, `tax`, `settings`. When the named page is one of those and a scope was requested, the page still opens and the chat says plainly that the page has no date scope. The filtered set is exactly `spending` and `transactions`, defined as one constant that both the note and the tests read.
- **AC-5**: The requested chart renders inline in the chat (existing behavior) and the destination page renders its own charts already filtered to the applied scope. No separate Copilot results panel is added. On Spending, a multi month range selects "All Months (Monthly Average)", a single fiscal month selects that month, and a non aligned explicit range shows a "Custom range" caption with the exact dates; the header states the applied range.
- **AC-6**: When the destination is ambiguous, the Copilot asks one short clarifying question that names the candidate screens, and moves nothing until the answer arrives. Model behavior; checked by the prompt set in **AC-22**.
- **AC-7**: If any tool in the turn fails, or Ollama is offline, the app does not navigate and the current page stays as it was. No intent is committed. The same holds for Clear Chat while a turn is running.
- **AC-8**: With Hide values on, the mask hides money only. Tickers, asset names, merchant names, categories, dates, counts, and all percentages stay readable, and chart axes stay readable. Concretely, `ui/components.py` `mask_if_hidden` keeps its currency rule (`([+\-]?)(\$|€|£|TRY\s*)[0-9,]+(\.[0-9]+)?` to `\1\2****`) and drops the percentage, `assets` count, and `quote delayed` rules; `format_money` keeps its `{sym}****` token. Chat masking is a render time pass over the streamed text (not storage), so the toggle works retroactively, and it covers `$` as well as `€` (eToro holds USD). Dataframes mask a named money column set. Chart builders tag monetary axes so only those are masked. This replaces the masking rule recorded in spec 0016 AC-10, which also masked personal percentages and blanked charts. Closes audit items 1a, 1b, 3.2.
- **AC-9**: One click navigation chips in the Copilot sidebar open the matching page and scope with no typing. Each chip writes the intent directly through `on_click`, with no model call and no thread, and is disabled while a turn is running. The chips are: Spending this month, Spending last 3 months, Investments holdings, Allocation and Drift, Transactions recent, Tax situation.
- **AC-10**: No `use_container_width` remains as a Streamlit argument and no `st.components.v1.html` remains anywhere. The project wrapper parameter in `ui/theme/charts.py` `render_chart` is renamed from `use_container_width` to `width` and its callers are migrated, so a literal grep is clean. `st.components.v1.html` becomes `st.iframe`, confirmed to execute the embedded HTML the same way. The app renders with no Streamlit deprecation warnings.
- **AC-11**: On Spending the current defect is that the period control shows the raw key `2026-09 (24 Sep to 23 Oct)`. It must show a month name (for example "September 2026") and the range shown must align to that same fiscal month. The range is derived from `get_fiscal_month_range(y, m, salary_day)`. Closes audit item 2.8.
- **AC-12**: The current defect is that the crypto ticker puts market capitalization in the price and change slots (`BTC-USD 1.68T -5,191,230,947.00`). The quote fields feeding the price, change, and change percent slots must be the instrument price and its change, not the market cap, sourced from the quote fields already returned for non crypto tickers. Closes audit item 2.7.
- **AC-13**: Because the dashboard page is registered with `default=True`, Streamlit serves it at the app root and ignores `url_path="dashboard"`, so a manual visit to `/dashboard` shows a "Page not found" toast. The dangling `url_path` is dropped so the root serves the dashboard and no not found path remains, and any internal link points at the root. Closes audit item 2.5.
- **AC-14**: Charts show a loading placeholder instead of a blank plot while the Plotly figure mounts. The mechanism is a skeleton element rendered in the chart container that is replaced when the figure is present. Closes audit item 3.5.
- **AC-15**: There is no more than 48 pixels of dead space between the last element on a page and the bottom of the content area, measured on a 1440 by 900 viewport. Closes audit item 3.7.
- **AC-16**: The README matches the running app: the test count equals the number in the live suite run, the native tool count equals the length of `COPILOT_TOOLS_SCHEMA` (which this round changes by adding `open_view`), and the Privacy Shield claim matches the masking rule in AC-8. Screenshots are captured after charts settle and after the masking fix, so no ticker or axis reads as masked.
- **AC-17**: Demo mode starts on seeded data through the existing `PFA_DEMO` switch, and the sidebar pre-fills the navigation prompt chips and the demo prompt chips suitable for screen sharing. The demo prompt chips are a different set from the AC-9 navigation chips and are listed in the build plan.
- **AC-18**: A single `open_view` tool exists in the Copilot schema with `page`, `tab`, and `date_scope` inputs. Each value is validated against a whitelist; an unknown page or tab returns a guided error and moves nothing. The tool never writes SQL.
- **AC-19**: No database change. The intent is carried on the task object and committed to Streamlit session state once, then consumed once: a rerun never re-applies it, a manual change of page or scope by the user is respected afterward, and a stale intent cannot be consumed later.
- **AC-20**: The README carries a short architecture section covering the local first privacy model and the read only SQL design.
- **AC-21**: A deterministic fast path opens a page, and a tab, when the request is explicit navigation phrasing (for example "open spending", "go to rebalancing", "show my transactions"). It runs before the model, makes no model call, and returns the same intent shape as `open_view`. The model path remains for fuzzy or combined requests.
- **AC-22**: A fake model harness emits scripted tool calls, so the tests assert intent construction, commit on completion, once only consumption, whitelist rejection, and masking without Ollama. It also drives the AC-1, AC-2, AC-3, and AC-6 prompt set, which passes at a stated threshold.

## Decision

**Chosen option**: Option 1: add one thin action layer (a single validated `open_view` tool, a deterministic fast path for explicit phrasing, and a one time intent committed from the task to Streamlit session state, consumed by `app.py` and forwarded to `st.switch_page` and `st.tabs(default=...)`), plus a shared date resolver and the confirmed fix in place polish.

Keep every layer where it is and add the smallest thing that closes the gap. The Copilot gains one tool and one instant fast path; the app gains one consumption point after `st.navigation`; the filters gain a persistent state dict; the Investments tabs gain a session state key with a generation counter. No new dependency, no database change, no second chart system, and no rewrite of any page.

**Implementation skills**: none used. No community skill relevant to this decision is installed in the project (root `AGENTS.md` declines `python-resource-management` and `sqlite-database-expert`).

## Feature design

**Data model sketch**: no schema change. The model is a small session state contract that carries an intent from the assistant thread to the page renderer.

| State key | Type | Set by | Read by | Notes |
|---|---|---|---|---|
| `task.ui_intent` | dict | the `open_view` tool or the fast path, on the `CopilotTask` | `ui/copilot_sidebar.py` on turn completion | Never written to `st.session_state` from the worker thread |
| `copilot_ui_intent` | dict | the sidebar, on completion, under the task lock | `app.py` | `{page, tab, date_scope, applied, note}`. Consumed once, then cleared |
| `flt_state` | dict | the filter widget `on_change`, or the intent | `ui/filters.py` and Spending | `{preset, start, end}`. Persistent, copied into the widget so a run without the widget does not wipe it |
| `investments_active_tab` | str | the intent only | `ui/pages/investments/__init__.py` | Passed to `st.tabs(default=...)`; popped with the intent |
| `investments_tabs_generation` | int | the intent only | same | Bumped so the tabs element remounts and `default` takes effect |

The existing filter widget is bound to `flt_state` so the intent can write it. Everything is session state, so it is per session, not persisted, and reverts on restart.

**State transitions**: an intent moves `created` (on the task) to `committed` (session state, on turn completion) to `consumed` (read and applied by `app.py`, `applied` flipped true). Only a completed turn commits. A failed turn, an offline turn, or Clear Chat drops the intent. A consumed intent is never re-applied; a user change of page or scope after consumption is the new truth.

**API surface** (the Copilot tool; it chooses the tool, the function validates and sets the intent):

| Tool | Kind | Key inputs | Key outputs | Safety |
|---|---|---|---|---|
| `open_view` | read (sets the task intent only) | `page` (enum), `tab` (optional), `date_scope` (optional: a preset name, or `start` and `end` dates) | success, resolved page and tab, the resolved scope, an "Applied scope: A to B" line appended in code, and a short note (for example "this page has no date scope") | values checked against a whitelist; unknown page or tab returns a guided error; never writes SQL |

The deterministic fast path returns the same intent shape without the model. The existing data tools (`get_spending_by_category`, `get_recent_transactions`, `get_monthly_cashflow`) gain the same optional `date_scope` input, resolved through the same resolver, and the first tool call that resolves a scope stores it on the task so a later call in the same turn inherits it (a 7B model may omit it on the second call).

**Value sourcing** (every value a criterion needs names its source):

| Action | Value produced / displayed | Source |
|---|---|---|
| Navigate | Destination page | `open_view` or the fast path `page` argument, checked against the whitelist built from the `st.Page` list in `app.py` |
| Navigate | Destination tab | `tab` argument, checked against the `TAB_MAP` of ids (`portfolio`, `allocation`, `income_tax`, `goals`) to the labels in `ui/pages/investments/__init__.py` |
| Apply scope | Resolved start and end date | `services/date_scope.py` `resolve_date_scope(date_scope, today=date.today())`, the single resolver |
| Answer and page agree | The range the page shows | `flt_state` written from the same resolved value the answer used |
| Spending headline | Which View Scope is selected | the resolver's month count and alignment rule (AC-5) |
| Honest note | "no date scope" line | membership in the unfiltered page set constant (AC-4) |
| Clarify | Candidate screens | the page whitelist |
| Masking | Money vs identifiers | `ui/components.py` `mask_if_hidden` currency rule; chat pass on the streamed text; a money column set; money tagged chart axes |
| Sidebar chips | Page and scope per chip | the static chip table in `ui/copilot_sidebar.py` |
| README stats | Test count and tool count | the live test run and `len(COPILOT_TOOLS_SCHEMA)` |

**Key invariants**:
- The model may choose a tool and turn a sentence into named arguments; it may never emit SQL and may never set a page or tab outside the whitelist.
- The intent crosses the thread boundary on the task object, never through a direct `st.session_state` write from the worker.
- One shared resolver feeds both the answer and the page, so the two cannot disagree; a scope resolved in a turn is inherited by later calls in the same turn.
- An intent is applied exactly once; a manual page or scope change afterward is respected.
- With Hide values on, money is masked at every display boundary including chat and chart axes, and identifiers and percentages are never masked.
- The read only SQL authorizer stays in force for every query tool.

**Security model**: single local user, no authentication surface. The trust boundary that matters is the model: it may set a page, a tab, and a date scope, and nothing else. The action surface is a whitelist, so a malformed call cannot reach a value the app does not already offer. Remaining risk is a wrong but valid destination on a poorly worded request, which AC-6 mitigates by asking before moving when the destination is unclear.

**Configuration required**: none.

**Critical test scenarios** (each maps to an acceptance criterion):
- Happy path, navigate: the AC-22 prompt set, one prompt per page, verifies **AC-1**.
- Happy path, tab: prompt each Investments tab and confirm selection, verifies **AC-2**.
- Happy path, scope: "what did I spend last month" lands on Spending with the matching scope and a chat number that agrees with the page range; repeat for past 3 months, this year, and an explicit range; unit test the resolver including the year rule, `start <= end`, and future clamping, verifies **AC-3**.
- Boundary, no scope: "show my investments for last month" opens Investments and says the page has no date scope, verifies **AC-4**.
- Happy path, charts: the asked for chart shows inline and the page's charts render filtered; on Spending a multi month range shows the monthly average scope, verifies **AC-5**.
- Ambiguity: a request like "show me the last thing" prompts a clarifying question and moves nothing, verifies **AC-6**.
- Failure case: with Ollama stopped, or with a failing data tool, no intent commits and the page does not change; Clear Chat drops a pending intent, verifies **AC-7**.
- Privacy: with Hide values on, chat replies, tables, and monetary chart axes mask euro and dollar amounts while percentages, counts, tickers, and merchant names stay readable, verifies **AC-8**.
- Chips: each sidebar chip opens the matching page and scope with no model call and is disabled while busy, verifies **AC-9**.
- Cleanup: grep for `use_container_width` and `st.components.v1.html` returns nothing and the app renders warning free, verifies **AC-10**.
- Bug checks: Spending shows "September 2026" with the aligned range; the crypto ticker shows price and change; the app root loads the Dashboard with no toast and `/dashboard` no longer exists, verifies **AC-11**, **AC-12**, **AC-13**.
- Polish: a chart shows a placeholder before it mounts, and no page shows more than 48 pixels of dead space, verifies **AC-14**, **AC-15**.
- Showcase: README stats match the suite and the schema, screenshots show readable charts, demo mode starts on seeded data, verifies **AC-16**, **AC-17**, **AC-20**.
- Tool validation: `open_view` with an unknown page or tab returns a guided error and moves nothing, verifies **AC-18**.
- Intent once: after a navigate, manually change the page and confirm the intent does not replay; a stale intent is not consumed, verifies **AC-19**.
- Fast path: an explicit navigation phrase opens the target with no model call, verifies **AC-21**.
- Harness: the fake model harness drives the prompt set and the intent tests with no Ollama, verifies **AC-22**.

## Build plan

Order follows the project's Tracer Bullet approach: the thinnest end to end thread first (one prompt, or one fast path phrase, drives one page change with one scope), then thicken. Tasks 1 to 5 are the thread, tasks 6 to 9 widen it, and tasks 10 to 15 are the polish, presentation, and the regression net.

1. **Intent transport and consumption thread**: store the intent on `CopilotTask`, commit it to `copilot_ui_intent` on completion under the lock, consume it in `app.py` after `st.navigation` and before `active_page.run()`, popping it and writing the scope and tab keys before `st.switch_page`, and define the already on this page case. Satisfies **AC-19**.
2. **Shared date resolver**: add `services/date_scope.py` with `resolve_date_scope(date_scope, today)`, the preset table, the explicit range rules (most recent past occurrence, month end, `start <= end`, future clamp), the day window handling, and the fiscal month mapping for Spending. Satisfies **AC-3**.
3. **Persistent filter state**: replace the filter widget defaults with `flt_state` written by `on_change`, drop `index=`, add a Custom range option, and clear the override when a preset is chosen. Satisfies **AC-3**.
4. **Writable tab**: read `investments_active_tab` into `st.tabs(default=...)` with `investments_tabs_generation` in the tabs `key` so the element remounts; pop the tab key with the intent. Satisfies **AC-2**.
5. **open_view tool**: add the function, its schema, the tool map entry, and the system prompt line; validate page and tab against the whitelist; resolve `date_scope` through the resolver; set the task intent and append the "Applied scope" line. Satisfies **AC-1**, **AC-18**.
6. **Fast path router**: a deterministic matcher for explicit navigation phrasing that sets the same intent with no model call and no thread. Satisfies **AC-21**.
7. **Data tool scope sharing**: add the optional `date_scope` input to the spending, transactions, and cashflow tools, resolve through the shared resolver, inherit the turn scope on later calls, and add the month snapping and precedence rules. Satisfies **AC-3**.
8. **Honesty and safety**: the "no date scope" note from the unfiltered page set constant, the clarifying question path, the no commit on tool failure or an offline turn, and dropping a pending intent on Clear Chat. Satisfies **AC-4**, **AC-6**, **AC-7**.
9. **On page charts and Spending scope mapping**: confirm the destination page's charts render filtered and keep the inline chart; implement the All Months, single fiscal month, and Custom range caption rules and the header range line. Satisfies **AC-5**.
10. **Sidebar chips**: add the six navigation chips from the static table, each writing the intent through `on_click`, disabled while busy, plus the demo prompt chips. Satisfies **AC-9**, **AC-17**.
11. **Masking rule change**: narrow `mask_if_hidden` to the currency rule, apply it to chat render including streaming chunks, use a money column set for dataframes, tag monetary chart axes, and keep percentages, counts, and identifiers readable. Satisfies **AC-8**.
12. **Deprecated API migration**: replace every Streamlit `use_container_width` argument with `width="stretch"`, rename the `render_chart` wrapper parameter to `width` and migrate its callers, and replace `st.components.v1.html` with `st.iframe`. Satisfies **AC-10**.
13. **Small bugs**: Spending month label and aligned fiscal range, crypto ticker field mapping, and dropping the dangling dashboard `url_path`. Satisfies **AC-11**, **AC-12**, **AC-13**.
14. **Perceived polish**: chart loading placeholders and the bottom spacing pass to the 48 pixel cap. Satisfies **AC-14**, **AC-15**.
15. **Presentation and regression net**: README refresh with corrected stats and an architecture section, re-shot screenshots, the fake model harness, the prompt set, and unit tests for the resolver, the whitelist, intent commit and once only semantics, the fast path, and the masking rule. Satisfies **AC-16**, **AC-18**, **AC-19**, **AC-20**, **AC-22**.

## Consequences

**Positive**:
- The Copilot stops being a chat box and becomes a control surface, which is the single most demoable behavior change in the app.
- One shared resolver fixes the "last month" misread at its root and keeps the answer and the page in agreement by construction.
- The deterministic fast path makes the headline interactions instant and reliable, which removes the biggest demo risk from a 7B model.
- The privacy mask becomes usable: charts read, tables read, and only money hides, so screen sharing and screenshots work.
- Removing the deprecated Streamlit calls turns a future breaking upgrade into a non event.
- The README and screenshots finally match the app, which is what a reviewer sees first.

**Negative / tradeoffs**:
- The action layer depends on `st.switch_page`, `st.tabs(default=...)`, and the tab remount workaround; a future major Streamlit change could break tab selection, though these are public APIs.
- AC-1, AC-2, and AC-6 remain model behavior; the harness and the prompt set measure them but cannot make a 7B model perfect.
- One more tool plus the fast path is a little more surface to test and to keep in sync.
- Masking at the chart level means touching chart tick formatting and tagging axes, which is easy to get subtly wrong; the regression test guards it.
- Committing the intent on turn completion only means navigation waits for the turn to finish, which is correct for AC-7 but means a slow turn delays the move.
- The polish tasks are individually small but numerous, so this round is broad. The scope stays honest by listing each item with its audit reference.

**Neutral**:
- No database change, no migration, no new dependency, no new environment variable.
- This round revises a rule from spec 0016 (AC-10 masking). Since 0016 is still in progress and unverified, no supersede is needed, but `/sync` should note the new rule.
- The intent crosses the thread boundary on the task object, following the existing `figure` and `form_request` pattern, so no new concurrency model is introduced.
- Vault first load race and the RAG embedding model are real but heavier, and are left as follow-up rather than folded in here.

## Follow-up

- [ ] Enroll this round as a scope feature in `docs/scope/scope.md` so its status becomes feature mirrored and the build plan lands in the scope row. Recommended before `/develop`; `/scope` owns that file.
- [ ] Vault and RAG: fix the first load race and embed with a real embedding model (audit 2.1, 2.2). Deliberately deferred from this round.
- [ ] Auto sync per session duplication and stale PSD2 account refs (audit 2.3, 2.4). Deferred.
- [ ] Copilot latency: on CPU a 7B turn runs 30 to 60 seconds. The fast path covers navigation; a larger tool calling model or two stage routing for the remaining questions is a separate decision, already noted in spec 0016.
- [ ] Do a short spike on `st.tabs(default=...)` and the generation counter before relying on tab remount, since tab selection is frontend state.
- [ ] Continue non monetary polish: donut label crowding (audit 3.3) and the collapsed open banking guide by default (audit 3.6).
- [ ] Memo to `/sync`: spec 0016 AC-10's masking rule is replaced by this spec's AC-8; `ui/AGENTS.md` and `agent/AGENTS.md` gain the action layer (the `open_view` tool, the fast path, and the intent contract).

## Rationale

Reasoning, the options weighed, and the audit evidence are recorded in [rationale.md](rationale.md).
