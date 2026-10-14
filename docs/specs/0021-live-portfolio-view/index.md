# 0021. Live portfolio view for the Investments page

**Date**: 2026-10-14
**Status**: In Progress

## Summary

The top of the Investments page currently shows three charts (a treemap, a donut and a bar) that all render the same exposure numbers, and the same treemap also appears on the dashboard. This spec replaces that with one live portfolio table, refreshed about every 60 seconds while markets are open, with today's gain or loss per position and for the whole portfolio, the way eToro shows it. Two of the charts are dropped, the duplicated sections go, and a portfolio value over time chart is added so the page reads like an investment view rather than a trading screen.

## Requirements

**User stories**:

- As the account owner, I want my holdings listed with live prices and today's move per position, so that I can see how my portfolio is doing without opening eToro.
- As the account owner, I want the exposure views to stop repeating the same numbers three ways, so that the page is readable at a glance.
- As the account owner, I want to keep asking the Copilot about my portfolio and have it shape the live view, so that the page and the chat answer agree.

**Acceptance criteria** (the contract, each criterion is IDed and independently checkable):

- **AC-1**: The first block after the KPI ribbon on the Portfolio tab is a live portfolio table with one row per distinct instrument symbol, the same universe the exposure heatmap is built from, so a position held both directly and inside a copy of a trader is one row with its values summed. The columns are Name with its ticker, Quantity, Avg open, Price, Day change percent, Day P&L in EUR, Cost basis, Market value, Total P&L in EUR, Total P&L percent, Weight percent and a Sparkline.
- **AC-2**: While the Investments or Dashboard page is open, on a weekday between 09:00 and 22:00 Europe/Amsterdam time, prices refresh roughly every 60 seconds inside a Streamlit fragment, so no full page rerun fires, and a last refreshed indicator is visible.
- **AC-3**: Day change percent and Day P&L per row are computed against that ticker's own previous close from `market_quotes`, converted to EUR, and the portfolio Day P&L card equals the sum of the row Day P&L values.
- **AC-4**: Outside those hours the view freezes at the last close and shows a closed market badge naming the last price date, and no network call is made. The window is computed in `zoneinfo("Europe/Amsterdam")` so daylight saving does not shift it.
- **AC-5**: A position with no live price keeps its last known price with its age shown, its value still counts toward the totals, and the Quote Status card reports how many positions are unpriced. A failed poll, including a timeout, keeps the last cached prices and shows one quiet delayed line, never an error wall. Positions valued only from the eToro mirror figure (unresolved `ID_` symbols) are not counted as unpriced, because they are not waiting on a poll.
- **AC-6**: The exposure donut, the horizontal exposure bar, the TradingView watchlist iframe and the separate eToro Copied Traders section are removed. Copied positions carry a copy tag inside the live table, from an explicit `is_copy` column. The exposure treemap stays, below the live table, and its Sector, Region, Currency and Nature pills now drive the treemap grouping.
- **AC-7**: The KPI ribbon holds five cards: Portfolio Value, Total Cost Basis, Unrealized P&L, Day P&L (euro amount with the percent as subtext) and Quote Status (live or delayed plus the count of unpriced positions).
- **AC-8**: A compact movers strip sits directly under the KPI ribbon, showing the top three gainers and top three losers by day change percent (ties broken by market value, priced rows only), each as an offline ticker chip (generated, no image and no network call) with its signed day percent.
- **AC-9**: The page carries a portfolio equity curve: portfolio value as a line with cost basis as a stepped line, range pills for 1M, 3M, 6M, 1Y and All defaulting to 3M, reading from `portfolio_snapshots`. With no history it shows an empty state that says history builds from today rather than plotting a fabricated point.
- **AC-10**: One row per day is written to `portfolio_snapshots` from `app.py` before the page renders, at most once per day, holding market value, cost basis and day P&L in euro minor units. The row is built from the stored closes, not from the live poll, so the closed hours rule still holds. The upsert on `snapshot_date` is the once per day guard, and a daily rollover check covers a session left open across midnight. A day the app is never opened has no row.
- **AC-11**: The page carries a ranked P&L contribution chart of each holding's unrealized profit or loss in euro (priced copy rows included), and a small sector performance heatmap grid coloured by each sector's weighted day move.
- **AC-12**: The live table is a fixed height (`420px`) scrollable table with sortable columns and a search box that filters by ticker or name, defaulting to sort by market value descending. The frame stays numeric so sorting stays numeric; masking is applied to the display only (see AC-13).
- **AC-13**: With Hide values on, euro amounts and cost figures in the new view are masked while prices, quantities and percentages stay readable. Masking is applied at render time so the underlying numbers keep their type and the columns stay sortable.
- **AC-14**: Every signed figure shows its sign, so colour is never the only carrier of the meaning.
- **AC-15**: The dashboard market carpet pins to asset nature and drops its dimension pills, so it no longer repeats the Investments exposure dimension.
- **AC-16**: The dashboard ticker tape is fed by the shared live poll (the same session cache the Investments page uses, refreshed on whichever of the two pages is open) and lists every distinct consolidated asset, falling back to the stored close for anything unpriced.
- **AC-17**: Through the Copilot the owner can sort the live table by a named column, filter it by the existing exposure dimension and focus values, show only gainers or only losers, search by ticker or name, and scroll the live view into view. The valid sort columns and mover values come from published module constants, every value is checked by an explicit validation branch against those constants and the live bucket list, and an unknown value is ignored with a note instead of being applied. The Copilot tool schema and system prompt are updated to match the new keys.
- **AC-18**: `analyze_investments` answers day P&L and today's movers from the same live source the page uses, so the chat answer and the page agree.
- **AC-19**: On the Income tab the per holding dividend table collapses behind an expander, and the tax loss harvesting panel is removed.
- **AC-20**: The existing Investments tests are updated to the new surface, new tests cover the live row maths, the session gate, the snapshot writer and the Copilot view validation, and the suite passes with no new warnings.

## Decision

**Chosen option**: Replace the redundant exposure charts with a live portfolio table as the page hero, poll yfinance intraday inside a market hours gate, and store one portfolio value row per day for the equity curve.

The three exposure charts collapse to the treemap alone, the live table becomes the single list of positions (direct and copied), and a new daily `portfolio_snapshots` table gives the page a value over time chart that no current view can produce.

**Implementation skills**: `developing-with-streamlit` (`streamlit/agent-skills`, `.agents/skills/developing-with-streamlit/`) · `building-pydantic-ai-agents` (`pydantic/skills`, `.agents/skills/building-pydantic-ai-agents/`)

## Feature design

**Data model sketch**:

New table, one row per day, upserted:

| Column | Type | Notes |
|---|---|---|
| `snapshot_date` | TEXT | primary key, ISO local date |
| `market_value_eur_minor` | INTEGER | NOT NULL, total holdings market value in euro cents |
| `cost_basis_eur_minor` | INTEGER | NOT NULL, total cost basis in euro cents |
| `day_pnl_eur_minor` | INTEGER | nullable, that day's move in euro cents, null when unknown |
| `fetched_at` | TEXT | NOT NULL, default `datetime('now')` |

Reused unchanged: `holdings` (current positions), `market_quotes` (one row per ticker per day, `close`, `prev_close`, `currency`, now also the sparkline and previous close source), `account_snapshots` and the `v_holdings` view.

In memory only, never written: the session quote cache stays in `st.session_state` under a new `state.K` key, shaped `{ticker: {price, prev_close, currency, fetched_at, source}}` plus `last_refresh_ts` and `last_poll_failed`. It must be session state, not a module global, so it survives a fragment rerun and a failed poll.

One new repository read: `HoldingRepository.get_ticker_close_series(tickers, days)` returns the per ticker close series the sparkline needs. One new repository write: `upsert_portfolio_snapshot`.

Added to the consolidated frame so downstream code does not have to re-derive it: an explicit `is_copy` boolean (the `COPY:` prefix is consumed when the frame is built, so it cannot be the tag source).

Derived, no storage: day change percent, day P&L per row, weight percent, total P&L percent, sector performance, the movers ranking and the per row sparkline.

**State transitions** (the quote feed, per render):

`cold` (no cache in this session yet, so nothing may claim to be live) → `fresh` (a price fetched inside the market hours window) → `stale` (the poll failed, timed out, or the ticker did not price; the last known price is kept with its age) → `closed` (outside the window, frozen at the last close with the date named). One successful poll moves any state back to `fresh`.

**Surface** (this is a Streamlit app, so the surface is Python functions and Copilot view keys, not HTTP endpoints):

| Surface | Kind | Key inputs | Key outputs | Auth | Key errors |
|---|---|---|---|---|---|
| `services/live_quotes.py::market_session_state` | pure function | now (`zoneinfo("Europe/Amsterdam")`) | `open` or `closed` | local | none, never raises |
| `services/live_quotes.py::refresh_live_quotes` | function | ticker list, now, session cache | updated cache dict | local | request timeout, returns the previous cache |
| `services/live_quotes.py::cached_quotes` | guarded accessor | none | the cache plus the last refresh time | local | safe to call off the script thread, falls back to stored closes |
| `services/live_quotes.py::market_clock` | pure helper | now | session window bounds, last price date | local | none |
| `services/portfolio.py::build_live_rows` | function | consolidated frame, per ticker aggregated holdings frame, mirror cache, quote cache, fx rate | one row per distinct instrument symbol with the agreed columns | local | empty frame on empty input |
| `HoldingRepository::upsert_portfolio_snapshot` | repository | date, market value, cost basis, day P&L (minor units) | row id, once per day by primary key | local | `IntegrityError` absorbed by upsert |
| `HoldingRepository::get_portfolio_snapshots` | repository | start date, end date | date ordered rows for the curve | local | empty list |
| `HoldingRepository::get_ticker_close_series` | repository | ticker list, day count | per ticker ordered closes for the sparkline | local | empty series for unknown tickers |
| `ui/pages/investments/live.py::render_live_portfolio_view` | render | live rows, quote state | the table, controls and status line | local | empty state on no holdings |
| `ui/charts/portfolio.py::build_investments_market_carpet` | render | consolidated frame, `group_col`, height | treemap figure | local | empty figure on empty input |
| `ui/charts/portfolio.py::build_equity_curve` | render | snapshot rows, range | Plotly figure | local | empty figure when no history |
| `ui/charts/portfolio.py::build_sector_performance_heat` | render | live rows | Plotly figure | local | empty figure |
| `ui/page_panel.py::scroll_selector_into_view` | helper | a container selector | scrolled view | local | no-op when the element is absent |
| `open_view(view={sort, exposure_dimension, focus, movers, search})` | Copilot tool | validated view keys | session keys written | local | unknown values ignored with a note |
| `tool_analyze_investments` | Copilot tool | none | adds `day_pnl_eur` and `movers` to its payload | local | `day_pnl_eur: null` with a last close note when closed |

**Value sourcing** (every value each action produces, computes or displays names where it comes from):

| Action | Value produced / displayed | Source |
|---|---|---|
| Live price per row | current price | yfinance 1 minute batch (session cache), fallback `market_quotes.close` |
| Live price currency | currency of the price | the live quote's own currency field, falling back to `v_holdings.currency` |
| Day change percent, day P&L | previous close | `market_quotes.prev_close` for that ticker (copy constituent symbols are included in the daily download so they have one) |
| Price and P&L in EUR | USD to EUR rate | `market_quotes` `EURUSD=X` latest close, existing `usd_to_eur` fallback |
| Quantity, Cost basis, Total P&L | direct position maths | per ticker aggregate of `v_holdings` (via `aggregate_distinct_holdings`), summed by ticker |
| Quantity, invested value for copy legs | mirror position maths | `etoro_mirrors_cache.json` position `units` and `amount_usd` plus `pnl_usd` |
| Avg open | per share break even | native cost over quantity, with the existing `(EUR)` fallback label when native cost is unavailable |
| Weight percent | share of portfolio | row market value over total market value |
| Sparkline | per row price series | `get_ticker_close_series` over `market_quotes`; empty or single point rows render without a line |
| Copy tag | whether a row is a mirror | the new `is_copy` column on the consolidated frame |
| Quote Status card | live or delayed, unpriced count | session cache `fetched_at` and rows with no live price; mirror valued rows are excluded |
| Quote age on a row | how old the price is | session cache `fetched_at` in minutes, falling back to `market_quotes.quote_date` in days when the price came from the stored close |
| Closed market badge | last price date | `market_session_state` plus the newest `quote_date` across the portfolio's tickers |
| Day P&L percent subtext | the portfolio day percent | day P&L euros over the previous close portfolio market value |
| Equity curve and cost line | daily value and cost | `portfolio_snapshots` rows, reconciling with the investment account `account_snapshots` series |
| Sector heat | weighted day move per sector | live rows (day change percent times weight) grouped by `sector`, priced rows only |
| Movers strip | top three gainers and losers | live rows sorted by day change percent, priced rows only, ties by market value |
| Ticker chip | generated label | ticker text, no image source and no network |
| Copilot sort values | valid column ids | the `SORT_COLUMNS` constant published next to the live table |
| Copilot mover values | valid mover keys | the `MOVERS = ("gainers", "losers")` constant |
| Copilot focus bucket list | valid filter values | `get_dimension_exposure_df` live buckets, the existing helper in `agent/tools/navigation.py` |

**Key invariants**:

- `portfolio_snapshots` has at most one row per `snapshot_date`, enforced by the primary key upsert, and a session left open across midnight still writes the new day's row.
- Day P&L sums to the portfolio Day P&L card over priced rows; an unpriced or mirror valued row contributes nothing to that sum rather than a fabricated zero.
- The live table frame stays numeric. Masking happens at display time only, so sorting and the sparkline keep working with Hide values on.
- Money is stored and summed in integer minor units, converted to float only for display.
- The poll never writes to the database; only the once per day snapshot write does.
- The snapshot value series reconciles with the investment account `account_snapshots` series, so there are not two disagreeing portfolio value histories.
- A Copilot view value that is not listed in the page whitelist, the sort constants or the live bucket list never reaches a page session key.
- Prices and symbols are public and stay readable when Hide values is on; quantities are not masked, matching the repo rule that masking covers money only.
- The quote cache and the last refresh time live in `st.session_state`, never in a module global, and the Copilot reads them through the guarded accessor only.

**Security model**:

Single local user, no roles and no tenancy. No new network destination is introduced: the intraday call uses the same yfinance market data path already in `connectors/market_data_service.py`, with an explicit request timeout so a hung call cannot stall the page. No credentials are added and no telemetry is emitted. The only read path added for the Copilot is validation against live buckets, on a read only connection, and the Copilot thread reaches the live cache only through the guarded accessor that falls back to stored closes, so it never touches `st.session_state` off the script thread. Money masking follows the existing shared helpers, so the page and the chat mask the same values.

**Configuration required**: none. The poll interval (60 seconds) and the market window (09:00 to 22:00 Europe/Amsterdam, weekdays) are module constants, not environment variables.

**Critical test scenarios** (each maps to an acceptance criterion in ## Requirements):

- Happy path: with the app open inside the market window, the table shows every distinct asset with a live price, day change and day P&L, and the portfolio Day P&L equals the sum of the priced rows, verifies **AC-1**, **AC-2**, **AC-3**.
- Failure case: yfinance raises, returns nothing, or times out, so the table keeps the last cached prices, one delayed line shows, and no exception escapes, verifies **AC-5**.
- Closed market: with a timestamp on a Saturday, and one on a weekday outside the window in both winter and summer time, no network call is made, prices freeze at the last close, and the closed badge names the last price date, verifies **AC-4**.
- Copy rows: a copied position with a resolvable constituent symbol shows a priced row with a copy tag, and one with an unresolved `ID_` symbol shows a mirror value, no day change, and is not counted as unpriced, verifies **AC-1**, **AC-5**, **AC-6**.
- Snapshot writer: run app start twice on the same date and `portfolio_snapshots` holds exactly one row for that date, in minor units, and a simulated midnight rollover writes the next day, verifies **AC-10**.
- Equity curve empty: with no snapshot rows the chart renders the empty state text and plots nothing, verifies **AC-9**.
- Masking with sorting: with Hide values on, cost and value cells are masked while price, quantity and percent cells are readable, and clicking a masked column still sorts by the underlying number, verifies **AC-12**, **AC-13**.
- Copilot validation: `open_view` with an unknown sort column, an unknown mover value and an unknown focus bucket is rejected with a note, while the whitelisted values land in the page session keys and the live view scrolls into view, verifies **AC-17**.
- Redundancy: the investments page renders no donut, no exposure bar, no TradingView iframe and no copied traders section, the dashboard carpet groups by nature with no pills, and the investments pills change the treemap grouping, verifies **AC-6**, **AC-15**.

## Build plan

Ordered as a Tracer Bullet: first a thin end to end thread (a stored daily value row, live prices, one real table with day P&L, the poll and the KPI ribbon) so the risky part, the live feed, is proven before the page is dressed. Everything else thickens that thread.

1. Create migration `0008_portfolio_snapshots`, the repository upsert (primary key on `snapshot_date`), the read for the curve, and `get_ticker_close_series`, satisfies **AC-10**, **AC-1**
2. Add `services/live_quotes.py`: the `zoneinfo` market session gate, the batched 1 minute yfinance call with an explicit timeout, the `st.session_state` cache with `last_refresh_ts` and `last_poll_failed`, and the guarded accessor with a stored close fallback, satisfies **AC-2**, **AC-4**, **AC-5**
3. Write the daily snapshot from the stored closes in `app.py` before the page renders, with the midnight rollover check, satisfies **AC-10**
4. Add `is_copy` to the consolidated frame, and the `group_col` parameter to the carpet builder, satisfies **AC-6**, **AC-15**
5. Add `build_live_rows`: one row per distinct instrument symbol joining the consolidated frame, the per ticker aggregated holdings, the mirror cache and the quote cache, with day change against previous close, EUR conversion, day P&L, weight and total P&L percent, satisfies **AC-1**, **AC-3**
6. Render the live table with `st.column_config` (number formats, `LineChartColumn` sparkline, `420px` fixed height, sortable columns, search box, default sort by market value), keeping the frame numeric, satisfies **AC-1**, **AC-12**
7. Wire the 60 second poll inside the portfolio fragment body (the frames are computed outside it, so the fetch and the row rebuild must run inside), with the last refreshed indicator and the closed badge, satisfies **AC-2**, **AC-4**
8. Rebuild the KPI ribbon as five cards including Day P&L (euro with the percent over the previous close value as subtext) and Quote Status (live or delayed plus unpriced count, mirror valued rows excluded), satisfies **AC-7**, **AC-5**
9. Widen the daily download in `update_quotes` from 5 days to 1 month and include copy constituent symbols, so every priced row has a previous close and a sparkline series, satisfies **AC-1**, **AC-3**
10. Add the movers strip with generated offline ticker chips, top three each side, priced rows only, satisfies **AC-8**
11. Add the equity curve with the stepped cost line, range pills and the empty state, and confirm it reconciles with the investment account snapshot series, satisfies **AC-9**
12. Add the P&L contribution chart and the sector performance heat grid, satisfies **AC-11**
13. Remove the donut, the exposure bar, the TradingView iframe and the copied traders section, show the copy tag in the live table, and point the surviving pills at the treemap grouping, satisfies **AC-6**
14. Apply money masking at display time and the always signed convention across the new view, satisfies **AC-12**, **AC-13**, **AC-14**
15. Pin the dashboard market carpet to nature, drop its pills, and parameterize the shared scroll helper, satisfies **AC-15**, **AC-17**
16. Feed the dashboard ticker tape from the shared poll cache with a stored close fallback and every distinct consolidated asset, satisfies **AC-16**
17. Add the `SORT_COLUMNS` and `MOVERS` constants, the `state.K` keys, the session key map entries, the explicit `_clean_view` validation branches, and the Copilot tool schema and prompt updates, satisfies **AC-17**
18. Extend `tool_analyze_investments` with day P&L and today's movers through the guarded accessor, returning `null` with a last close note when closed, satisfies **AC-18**
19. Collapse the per holding dividend table and remove the tax loss harvesting panel, satisfies **AC-19**
20. Update the existing Investments tests and add coverage for the live row maths, the session gate, the timeout path, the price series, the snapshot writer and rollover, and the view validation, satisfies **AC-20**

## Consequences

**Positive**:

- The page stops showing the same numbers three ways, and the two screens stop showing the same carpet.
- Today's move is visible per position and for the whole portfolio, which no current view provides.
- The equity curve gives the portfolio a history for the first time, without changing how positions are stored.
- The TradingView iframe goes, which removes a third party embed from the page.

**Negative / tradeoffs**:

- The intraday feed is delayed by roughly 15 minutes and, on yfinance, 1 minute history reaches back only a few days, so this is a polling view, not a live tick stream. A genuinely real time view would need a different provider.
- The poll runs while either the Investments or the Dashboard page is open, because Streamlit cannot see a hidden browser tab and `st.tabs` renders every tab. Market hours are the only low cost brake available.
- The daily snapshot leaves gaps on days the app is not opened, so the curve shows missing days rather than an estimate.
- The market badge is based on the clock, not on an exchange calendar, so a public holiday or a half day will show as open and the poll will return nothing until it is treated as stale.
- A fresh session starts with a cold cache, so the first render shows stored closes and must not claim to be live until the first poll completes.
- Twelve columns is wider than one screen, so the table needs horizontal room and its sparkline column earns less space on a narrow window.
- The Copilot sort and filter keys are only as stable as the published `SORT_COLUMNS` constant and the exposure bucket list, so a future column rename must update both.

**Neutral**:

- One additive migration, a new table, no data transform and no change to existing rows. Reverting the commit is enough, and leaving the table in place is harmless.
- A new module, `services/live_quotes.py`, becomes the single source for live prices, used by the investments page, the dashboard tape and the Copilot tool.
- The market window is a module constant. If the app is ever used outside the Netherlands it becomes a setting, which is its own small decision.
- The snapshot value series and the existing investment account snapshot series both describe portfolio value, so they must reconcile rather than drift into two disagreeing histories.
- `update_quotes` gets an explicit request timeout, which is close to the timeout convention `connectors/AGENTS.md` already asks for.

## Follow-up

- [ ] The 1 minute feed is roughly 15 minutes behind and shallow. If a truly real time view is wanted later, it is its own decision (a websocket provider such as a broker feed or a paid market data API), with cost and privacy consequences.
- [ ] If the gap on unopened days proves annoying, backfilling missed days from stored closes times current quantities is a separate decision, and those points must be marked as estimates.
- [ ] The market hours window is a module constant. If the app is ever used outside the Netherlands, it becomes a setting, which is its own small decision.
- [ ] The market badge is clock based, so public holidays and half days look open. Exchange calendar awareness is a separate small decision if the false live badge proves annoying.
- [ ] The equity curve value line and the investment account snapshot series overlap. If they ever disagree, the decision is which becomes the single source for portfolio value.

## Rationale

Reasoning, the options that were weighed and the rejected paths: see `rationale.md`.
