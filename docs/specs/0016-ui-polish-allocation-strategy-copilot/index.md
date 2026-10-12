# 0016. UI polish, allocation strategy management, and copilot hardening

**Date**: 2026-10-12
**Status**: In Progress

## Summary

This round fixes a set of visual problems found by clicking through the running app and adds real management of investment allocation strategies. The messy places are the dead space between the navigation bar and the ticker, the panel order on the Dashboard, the narrow Top Merchants table on Spending, the per lot holdings table on Investments, a leftover duplicate table, and KPI cards that change height when Hide values is on. Alongside that, allocation strategies become creatable and deletable from Settings, from the Investments panel, and by asking the local Copilot in plain language. The Copilot keeps its read only database rule: the model picks a validated tool, it never writes SQL. Copilot measurements taken for this spec also turned up three real bugs (raw cents leaking into mortgage answers, a spending tool that rejects its own parameters, and a position count of one thousand one hundred thirty one where the real answer is a few dozen), which the build fixes.

## Requirements

**User stories**:
- As the app owner, I want the page to start right under the navigation bar so the first screen is not wasted on empty space.
- As the app owner, I want the charts above the account cards, because the charts are the summary and the cards are the detail.
- As the app owner, I want a row of KPI cards to keep one height whether or not a card carries a percentage change, so nothing jumps when I toggle Hide values.
- As the app owner, I want the Spending panels to line up and the merchant list to use the full page width with useful columns, so merchants are readable and comparable.
- As the app owner, I want the portfolio held as distinct assets with positions summed, so the table answers "what do I own" rather than "which lot is this".
- As the app owner, I want live market data visible at all times, because it is public data and not my personal finances.
- As the app owner, I want to create and delete allocation strategies in the UI and by asking the Copilot, with a confirmation before a delete.
- As the app owner, I want the Copilot to answer correctly and quickly, and to never show a cents value as if it were euros.

**Acceptance criteria**:

- **AC-1**: On a viewport 1280 pixels wide or wider, the vertical distance from the bottom of the top navigation bar to the top of the ticker tape is 8 pixels or less (measured 36 pixels before this change).
- **AC-2**: The Dashboard renders in this order: ticker tape, 4 KPI cards, Expenses and Portfolio exposure panels, then Accounts and Balances.
- **AC-3**: In any KPI row, every card has the same rendered height whether or not it has a delta value, so toggling Hide values never resizes a panel.
- **AC-4**: On Spending, the Spending by Category panel and the Subscription Leak Detector panel start at the same top and end at the same bottom.
- **AC-5**: Top Merchants is its own panel spanning the full content width of the Spending page.
- **AC-6**: Each Top Merchants row shows merchant, location, category (with parent category when it differs), transaction count, average per visit, total spent, share of scope spending, last transaction date, and the accounts used.
- **AC-7**: The Location column and the spend by location bar render only when at least one merchant in the scope resolves to a country from a counterparty IBAN; there is no currency fallback, so on data without IBANs both are absent rather than empty.
- **AC-8**: Portfolio Holdings shows one row per distinct asset, built by grouping the `v_holdings` frame by `ticker` (that frame carries `quantity`, `cost_basis`, `cost_basis_native`, and `latest_close`), with quantity, cost basis, value, and unrealized profit summed across lots; copied trader rows keep their own `COPY:` key so they stay attributable; no Status column; the average open price is recomputed from the summed native cost and quantity when the group holds one currency, and from the EUR cost column with the header marked EUR when it does not.
- **AC-9**: The standalone live quotes table above the TradingView watchlist is gone, and the watchlist shows every distinct active asset using the same exchange prefix mapping as the Dashboard ticker (`VWCE.DE` becomes `XETR:VWCE`, `.DE` is `XETR:` in `TICKER_EXCHANGE_MAP`).
- **AC-10**: With Hide values on, every euro amount and every percentage derived from personal cost, value, or quantity is masked, while market prices, ticker symbols, and public instrument percentages stay visible.
- **AC-11**: A new allocation strategy can be created and an existing one deleted from Settings under Target Allocations and from the Investments allocation panel; the delete action asks for confirmation before it runs. The create form defaults to a drift band of 5, no cash bucket included, requires a percent for every bucket it offers, and does not auto activate the new profile.
- **AC-12**: The Copilot creates and deletes allocation strategies from plain language through deterministic tools. Create takes a name, a dimension from the allowed enum, targets as a bucket keyed map of percent values between 0 and 100 at one decimal, a drift band between 0 and 100, and an include cash flag. It validates that the name is unique case insensitively, every bucket exists in the documented vocabulary for that dimension (plus an explicit cash bucket), and the rounded targets sum to 100 within 0.1; on failure it writes nothing and names the actual sum. Names match exactly, ignoring case.
- **AC-13**: Deleting the active profile or the last remaining profile is refused with a message naming the reason and the available profiles, and a delete only proceeds when the confirmation call echoes the one time token returned by the first call.
- **AC-14**: The eight prompt evaluation set is committed as a fixture of prompt and expected tool pairs asserted with the model mocked, so the tool map, the new tools, and the argument validation are checked without depending on a live model; the live model run stays a manual step in `verify.md`.
- **AC-15**: Every tool payload is audited so no payload hands the model a value in minor units without also giving the euro formatted string (the mortgage schedule is the known offender, and the audit covers all tools, not only that one).
- **AC-16**: `get_spending_by_category` accepts an optional category filter, and a tool call carrying an unknown argument returns a guided error instead of raising an internal type error.
- **AC-17**: After the model has been used once, a Copilot turn shows its total time and the model name in the answer footer, rendered once the response stream ends, with the model name from `secrets_vault` `ollama_model` or `DEFAULT_MODEL` when unset.
- **AC-18**: `ui/utils/masking.py` no longer exists as a separate masking path; all masking goes through `ui/components.py`.
- **AC-19**: `ui/theme/common.css` contains no duplicated rule block, and `ui/AGENTS.md` points at the investments package rather than a removed single file.

## Decision

**Chosen option**: Option 1: Fix in place, one narrow change per complaint, plus a deterministic tool layer for allocation management (basis: enhancement mode, fix in place first).

Keep every layer where it is and change the smallest thing that removes the defect: CSS and render order for layout, a shared service function for holder aggregation, the existing repository for allocation writes, and new deterministic Copilot tools for the natural language path. No new tables, no new dependencies, no rewrite of a page.

**Implementation skills**: none used. No community skill relevant to this decision is installed in the project (root `AGENTS.md` declines `python-resource-management` and `sqlite-database-expert`).

## Feature design

**Data model sketch**: no schema change. Existing tables carry the whole feature:

| Table | Fields used | Notes |
|---|---|---|
| `allocation_profiles` | `id` pk, `name` (unique, case sensitive in SQLite so uniqueness is checked with `LOWER`), `dimension` (check: `asset_class`, `asset_type`, `region`, `sector`, `currency`, `ticker`), `include_cash`, `drift_band_pct`, `is_active` | One row may be active; the app already tolerates zero |
| `allocation_targets` | `profile_id` fk to `allocation_profiles` on delete cascade, `bucket`, `target_pct` (check 0 to 100) | Primary key (`profile_id`, `bucket`) |
| `transactions` | `merchant_normalized`, `counterparty_name`, `counterparty_iban`, `booking_date`, `amount_eur_minor`, `account_id` | Source for every merchant column and for location |
| `holdings` / `v_holdings` | `ticker`, `quantity`, `cost_basis_minor`, `currency` | Source for the distinct asset aggregation |

**State transitions**:
- Allocation profile: `created` to `active` (set active) to `deleted`. Deleting a non active profile is allowed. Deleting the active profile is refused while it is the only profile and refused outright without confirmation.

**Copilot tool surface** (the model's interface; it picks the tool, the function validates and writes):

| Tool | Kind | Key inputs | Key outputs | Safety |
|---|---|---|---|---|
| `get_allocation_profiles` | read | none | profiles with name, dimension, targets, active flag | read only connection |
| `create_allocation_profile` | write | name, dimension, targets (bucket keyed map, percent 0 to 100 at one decimal), drift_band_pct (0 to 100, default 5), include_cash (default false) | success, message, created profile | full validation before write |
| `delete_allocation_profile` | write | name, confirm_token (empty on the first call) | first call: requires_confirmation, confirm_token, and a summary; with the matching token: deleted | refuses the active or last profile, unknown name reports not found |
| `set_active_allocation_profile` | write | profile_name | success, message | already exists, keep |
| `get_spending_by_category` | read | year, month, category (new, optional) | category totals | filter applied in SQL, not in the model |
| `analyze_mortgage` | read | none | schedule rows with euro formatted payment, interest, principal, balance | drop raw minor fields or pair each with a formatted euro field |
| `analyze_investments` | read | none | distinct position count and distinct positions | recount after the aggregation fix; its message names drift alerts explicitly |

**Value sourcing** (each displayed or computed value names its source):

| Action | Value produced / displayed | Source |
|---|---|---|
| Dashboard ticker placement | Gap between nav and ticker | CSS: `stMainBlockContainer` padding-top and the leading zero height rows in the main vertical block |
| KPI row height | Card height | `kpi_card` and the `st.metric` container it renders, given a shared min height token (delta slot reserved, measured 104 against 118 pixels before the fix) |
| Top Merchants row | Merchant | `display_df` column `merchant` (from `transactions.merchant_normalized`) |
| Top Merchants row | Location | `transactions.counterparty_iban` first two characters mapped to a country name through a country code table in the service module, fetched with a dedicated query over `transactions` because the spending frame does not carry the IBAN; no currency fallback |
| Top Merchants row | Transactions | count of rows for that merchant within the selected scope |
| Top Merchants row | Average per visit | merchant total divided by that count |
| Top Merchants row | Total spent | sum of `-amount_eur_minor` for that merchant, converted to major units |
| Top Merchants row | Share of scope spending | merchant total divided by the scope total already computed for the KPI ribbon; for the monthly average scope, the average monthly total |
| Top Merchants row | Last transaction | maximum `booking_date` for that merchant in scope |
| Top Merchants row | Category and parent | `v_transactions.category` and `parent_category`, taken as the most frequent by count, ties broken alphabetically, shown as Mixed when no category exceeds half the merchant's transactions, parent taken from that same category |
| Top Merchants row | Accounts | distinct account names from `v_transactions` for that merchant |
| Spend by location bar | Total per location | sum of merchant totals grouped by the resolved IBAN country |
| Distinct asset row | Quantity, cost basis, value, unrealized profit | sums over `get_v_holdings_df` rows grouped by `ticker`, copy rows kept under their own `COPY:` key |
| Distinct asset row | Average open price | summed `cost_basis_native` divided by summed `quantity` when the group holds one currency, else summed `cost_basis` (EUR) divided by quantity with the column marked EUR |
| Watchlist symbol | TradingView symbol | shared exchange map moved out of `ui/pages/dashboard.py` (`TICKER_EXCHANGE_MAP`), which maps `.DE` to `XETR:` |
| Allocation create | Valid bucket list | documented per dimension vocabulary held in the allocation service module (stocks, ETF, crypto, commodity, bond, other for asset type; cash and investment for asset class; the values present in current holdings for region, sector and currency), plus an explicit cash bucket |
| Allocation delete | Confirmation token | generated on the first call from the profile id and a hash of its name, required unchanged on the confirm call |
| Copilot footer | Turn time and model | wall clock around the turn, rendered after the stream ends; model from `secrets_vault` `ollama_model`, else `DEFAULT_MODEL` |

**Key invariants**:
- Targets of a profile sum to 100 percent within 0.1 after rounding to one decimal, checked before any write, with the actual sum named in the failure message.
- Profile names are unique case insensitively (SQLite `UNIQUE` is case sensitive, so the case insensitive check is the only guard).
- At most one profile has `is_active = 1`; deleting the active profile is refused, and so is deleting the last remaining profile.
- Every bucket in a create request exists in the documented vocabulary for that dimension, otherwise the tool returns the valid buckets and writes nothing.
- A delete only proceeds when the confirm call returns the token issued by the first call; an unknown name reports not found.
- No money value reaches the model or the screen as minor units without a paired euro formatted string.
- Masking follows one rule: mask every euro amount and every percent derived from personal cost, value, or quantity; keep market prices, symbols, and public instrument percentages.
- The read only SQL authorizer stays in force for every query tool; writes happen only inside named tool functions with explicit parameters.

**Security model**: single local user, no authentication surface. The trust boundary that matters is the model: it may choose a tool and turn a sentence into named arguments, it may never emit SQL and may never reach a connection outside the tool functions. Two guards sit on the write path, since the model makes both the request and the follow up call: a one time confirmation token issued by the first delete call and required back on the confirm call, and a refusal for the active or last profile regardless of the token. The stale line in `agent/AGENTS.md` (all Copilot database tools go through `connect_readonly()`) is corrected as part of the build so the documented rule matches the code, which stays "read only SQL, writes through named validated tools". Money and identifiers stay in the local database; the only external calls remain the market data widgets already in use.

**Configuration required**: none.

**Critical test scenarios** (each maps to an acceptance criterion):
- Happy path, dashboard: load the Dashboard at 1440 pixels wide and measure nav to ticker distance and panel order, verifies **AC-1** and **AC-2**.
- Happy path, KPI parity: toggle Hide values on the Investments Holdings tab and confirm no KPI row changes height, verifies **AC-3**.
- Happy path, spending: open Spending, confirm the two top panels share top and bottom edges, the merchants table spans the page, and the location bar appears only with IBAN locatable merchants; on a database with no IBANs both the column and the bar are absent, verifies **AC-4**, **AC-5**, **AC-6**, **AC-7**.
- Happy path, holdings: open Investments Holdings and confirm one row per ticker with summed values, copied traders still listed under their own name, and no Status column, verifies **AC-8**.
- Happy path, watchlist: confirm the duplicate table is gone and `VWCE.DE` renders as the `XETR:VWCE` quote, verifies **AC-9**.
- Privacy: with Hide values on, confirm quotes, symbols, and public percentages stay readable while balances, cost basis, position values, and personal percentages stay masked, verifies **AC-10**.
- Happy path, allocation management: create a strategy from Settings, see it in Investments, delete it with confirmation, verifies **AC-11**.
- Failure case, invalid create: ask the Copilot for a strategy whose targets sum to 90 percent, and confirm it returns the validation message naming the sum and writes nothing, verifies **AC-12**.
- Failure case, protected delete: request deletion of the active profile, of the last profile, and a delete with a stale or missing token, confirm all three are refused with the reason, verifies **AC-13**.
- Copilot accuracy: run the committed prompt fixture with the model mocked and confirm each prompt maps to its expected tool and that the new tools are registered, verifies **AC-14**.
- Failure case, money scaling: ask about mortgage interest and confirm the answer quotes euros matching the schedule, verifies **AC-15**.
- Failure case, tool arguments: call `get_spending_by_category` with a category and with an unknown key, confirm a useful result and a guided error, verifies **AC-16**.
- Cleanup: grep `ui/theme/common.css` for repeated blocks and confirm `ui/utils/masking.py` is gone and `ui/AGENTS.md` points at the package, verifies **AC-18** and **AC-19**.

## Build plan

Order follows the project's Tracer Bullet approach: the thinnest end to end thread through each area first, then the detail. Items 1 to 3 are the thread (layout and tables that a person sees immediately), items 4 to 8 thicken it (allocation management end to end, then Copilot), items 9 and 10 are the cleanup and the regression net.

1. **Layout thread**: collapse the leading zero height rows in the main block and the options wrapper (make the options wrapper not participate in the flex gap), reduce `stMainBlockContainer` padding-top, and give `kpi_card` and the metric it renders a shared min height with a reserved delta slot. Satisfies **AC-1**, **AC-3**.
2. **Dashboard order**: reorder `ui/pages/dashboard.py` `render()` to ticker, KPI ribbon, analytics section, accounts grid. Satisfies **AC-2**.
3. **Spending restructure**: move the two top panels into matched height containers, lift Top Merchants into a full width panel, and add the expanded merchant columns. Location comes from a new service helper that queries `transactions.counterparty_iban` and maps the country code, with the mode and tie break rules from the value table, no currency fallback. Satisfies **AC-4**, **AC-5**, **AC-6**, **AC-7**.
4. **Holdings aggregation**: add a distinct holdings aggregation over `get_v_holdings_df` grouped by ticker (summing quantity, cost basis, value, profit, and recomputing average open price per currency rule) to `services/portfolio.py`, use it in `render_holdings_table`, remove the Status column, and delete the duplicate quotes table in `ui/pages/investments/watchlist.py`. Satisfies **AC-8**.
5. **Shared symbol map**: move the exchange mapping out of `ui/pages/dashboard.py` into a shared module and use it for both the ticker and the watchlist, confirming the market quotes widget accepts a prefixed symbol name; drop the blur overlay from the watchlist and apply the one masking rule. Satisfies **AC-9**, **AC-10**.
6. **Allocation write layer**: add validated create, delete, and list functions against `allocation_profiles` and `allocation_targets`, with the argument contract, the bucket vocabulary, the confirmation token, and the refusal rules from **AC-12** and **AC-13**, reusing the existing repository where it already has these methods. Correct the stale rule line in `agent/AGENTS.md`. Satisfies **AC-12**, **AC-13**.
7. **Allocation UI**: create form and confirmed delete in Settings under Target Allocations, and the same two actions in the Investments allocation panel, both calling the write layer from task 6 with the create form defaults from **AC-11**. Satisfies **AC-11**.
8. **Copilot tools and correctness**: add the three allocation tools and their schemas, add the optional category filter to `get_spending_by_category`, stop passing arguments a tool function does not declare, and audit every tool payload for a minor unit value without a formatted twin (mortgage first). Satisfies **AC-12**, **AC-15**, **AC-16**.
9. **Copilot tuning and footer**: trim the schema set only where it is safe (merge the two overlapping knowledge base tools and drop tools no sidebar quick action, existing test, or prompt set reaches, keeping every quick action tool), shorten the system prompt to the accuracy rules that matter, set Ollama `keep_alive` and a summary token cap, compact the investments payload to distinct positions and name drift alerts in its message, and render the time and model footer after the stream. Satisfies **AC-14**, **AC-17**.
10. **Cleanup and regression**: dedupe `ui/theme/common.css`, reconcile `ui/utils/masking.py` into `ui/components.py`, fix the stale path in `ui/AGENTS.md`, commit the eight prompt and expected tool fixture with the model mocked, and add tests for the aggregation, allocation validation and token, merchant location, and mortgage formatting. Satisfies **AC-18**, **AC-19**.

## Consequences

**Positive**:
- The first thing a visitor sees is content, not empty space, and the Dashboard reads summary first, detail second.
- Investment tables answer the question a person actually asks, which asset do I hold and how much, and the Copilot gives the same number (one aggregation, two consumers).
- Allocation strategies become manageable without editing the database, in the UI or by asking, which is the point of shipping a local assistant.
- Three real correctness bugs are closed: cents quoted as euros on mortgage answers, a spending tool that rejects its own schema, and an inflated position count.

**Negative / tradeoffs**:
- The layout fix depends on Streamlit's generated class names and the two leading rows; a Streamlit major version bump can reintroduce the gap. The fix is small and documented in one place.
- Fixed height panels on Spending clip content if the leak detector ever needs to show many more rows. The row cap already exists in code, so the ceiling is known.
- Location resolves only from an IBAN, so on the current real database the column and the location bar simply do not appear. That is honest rather than broken, but it means the feature looks finished only on data that carries IBANs.
- Copied trader rows carry a value and a cost but not the per lot detail the aggregation needs, so their average open price falls back to the EUR cost column rather than a true average open price.
- Deterministic allocation tools widen what the Copilot can change. The model still cannot write SQL, but a mistaken call with a valid argument set is now possible, hence the confirmation token on delete.
- Trimming the Copilot tool set trades capability for selection accuracy; a question that used a removed tool stops working, which is why the trim keeps every tool a quick action or test reaches.

**Neutral**:
- No schema change, no migration, no new dependency, no new environment variable.
- `ui/utils/masking.py` is currently untracked, so folding it into `ui/components.py` removes a file rather than changing a shipped one.

## Follow-up

- [ ] Enroll this round as a scope feature in `docs/scope/scope.md` (no row links this spec yet, so its status is not feature mirrored). Recommended before `/develop`, and `/scope` owns that file.
- [ ] Re-run the Copilot prompt evaluation after the tuning lands and record the new latencies; if a first turn is still above roughly 30 seconds, revisit the default model (a larger tool calling model, or two stage tool routing).
- [ ] The Copilot writes look like a parser for a machine, so add a phrasing test set (for example "make my portfolio 70 30", "drop the Global One Fund target") to see how a 7B model maps wording to tool arguments before trusting it unattended.
- [ ] Watch for a Streamlit upgrade; the navigation and options selectors this round relies on are generated class names and DOM structure, not a stable API.
- [ ] Memo to `/sync`: `ui/AGENTS.md` key file table and the `ui/pages/investments.py` path are stale after the package split (task 10 fixes the path; the wider doc pass is yours).

## Rationale

Reasoning, the options weighed, the live measurements, and the Copilot evaluation results are recorded in [rationale.md](rationale.md).
