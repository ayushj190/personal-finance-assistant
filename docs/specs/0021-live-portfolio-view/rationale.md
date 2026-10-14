# 0021 rationale. Live portfolio view for the Investments page

Decision record. The build spec is in `index.md`, this file is the reasoning behind it and is not needed to build.

## Context

The Investments page grew by adding a view each time a question came up, and the result is three charts that render the same exposure numbers: `build_investments_market_carpet` (a treemap), a donut from `px.pie` and a horizontal bar from `px.bar`, all fed by the same `get_dimension_exposure_df` call in `ui/pages/investments/exposure.py`. The treemap is also rendered on the dashboard by `ui/pages/dashboard.py`, so the same picture appears on two pages. Reading the page, there is no answer to the question an investor actually asks first: how are my positions doing today.

The holdings data is rich enough for that answer, but the delivery is not. `v_holdings` already carries quantity, cost basis, latest close and unrealized P&L, and `market_quotes` already stores a `close` and a `prev_close` per ticker per day, which is exactly what a day change needs. What is missing is a price that moves during the day, and any record of what the portfolio was worth on a previous day.

Two constraints shape the choice. The first is the local first rule in `AGENTS.md`: financial ledgers stay on the machine, and no cloud telemetry, so a hosted market data service is out unless the engineer accepts the privacy tradeoff. The second is yfinance itself: its intraday data is delayed by roughly 15 minutes and its 1 minute history only reaches back a few days, so a genuinely real time tick stream is not available from the current provider. The page can feel live by polling, but it cannot be live in the trading sense.

The consequence of not deciding is a page that keeps its redundancy, a dashboard that repeats the investments page, and no way to see the portfolio change over time at all, since `holdings` only ever holds the current state and nothing records what it was worth yesterday.

## Options considered

### Option 1: Replace the redundant charts with a live portfolio table, poll intraday inside a market hours gate, store one daily value row

The live table becomes the hero of the Portfolio tab, one row per distinct instrument symbol (the same universe the exposure heatmap is built from). Prices come from a batched 1 minute yfinance call inside the existing market data service, held in a session cache, refreshed every 60 seconds while markets are open. Day change is measured against each ticker's stored previous close. A new `portfolio_snapshots` table records total market value, cost basis and day P&L once per day, which gives the page a value over time chart. The exposure treemap survives as a supporting chart with its dimension pills, now driving the treemap grouping.

**Pros**:
- Answers the first question an investor asks, per position and for the whole portfolio.
- Reuses the existing yfinance path, the existing previous close column, and the existing theme, so no new dependency, no new provider and no new egress destination.
- The daily snapshot is small and additive, and it is the only thing that can give the portfolio a history, because positions are stored as current state only.
- Removing the iframe and two charts from the page reduces both load and surface.

**Cons**:
- The numbers are delayed by roughly 15 minutes, so calling it real time sets an expectation the data cannot meet.
- Polling runs whenever the page is open, because Streamlit cannot detect a hidden tab, so the market hours gate is the only brake.
- A wider table (12 columns) needs horizontal room.

### Option 2: Fix in place, keep the charts and add live prices to the existing holdings table

Keep the treemap, donut and bar, and add day change and day P&L columns to the existing `render_holdings_table`, with the same poll behind it.

**Pros**:
- Smallest change, least risk, and the exposure views stay exactly as the engineer knows them.
- Delivers the live numbers, which is the core of the request.

**Cons**:
- Leaves the redundancy the engineer is complaining about, so the readability problem stays.
- Still no portfolio history, so no value over time chart.
- The holdings table is per lot while the exposure charts are per asset, so the page keeps two contradictory groupings.

### Option 3: A hosted market data provider with real time quotes

Replace yfinance with a hosted feed that gives true real time prices and intraday history.

**Pros**:
- Genuinely live prices, which is what eToro actually feels like.
- Intraday history would allow intraday charts.

**Cons**:
- Sends the full list of held symbols to a third party on a schedule, which conflicts with the local first rule in `AGENTS.md`.
- Adds a paid dependency, credentials to manage, and a new failure mode, for a personal finance app used by one person.
- The gain over a 60 second poll of fairly slow moving long term holdings is small.

## Rationale

The engineer's request, an eToro style live view for an investor rather than a trader, is best served by the table, not by more charts, and the redundancy they flagged is a symptom of the page having grown by addition. Option 1 takes the request literally: the positions become the page, the exposure view becomes the supporting context it should always have been, and the two duplicate surfaces (the donut and bar which repeat the treemap, and the TradingView iframe and the copied traders section which repeat the positions list) come out.

Option 2 was rejected because it fixes the numbers while leaving the readability problem, and because it cannot produce a value over time chart at all, since nothing stores portfolio value by day. That chart is the one genuinely investment minded view the request implies, and it only exists if the daily row exists.

Option 3 was rejected on the local first rule. The engineer's own `AGENTS.md` puts the ledger on the machine and forbids cloud telemetry, and holding symbols are as sensitive as the ledger. A 60 second poll of a delayed feed is enough for long term holdings, and the tradeoff is stated in the spec rather than hidden.

The recommendations were settled with two supporting calls. First, the daily snapshot is written at app start rather than on a page or a sync, because the engineer wanted one row per day they use the app, and app start is the only hook that fires however they use it. Second, live intraday prices are held in the session cache and never written, so the 60 second poll adds no disk churn and keeps `market_quotes` at one row per ticker per day, which keeps the daily close series and the previous close column intact for the day maths.

Two engineer choices were deliberately overridden in the assembled design, and are recorded here as they were raised at the time. The donut was first dropped as redundant with the treemap and then re picked in the chart list, so it was confirmed as dropped. The portfolio value sparkline block and the equity curve were both selected although both plot value over time, so the block was dropped in favour of the curve.

One structural question the spec had to settle, and did, is which of the two existing holdings frames the table's rows come from. `get_consolidated_holdings_df` (the frame the exposure heatmap and the Copilot already use) knows the instrument universe, its sector, region and nature, but carries no quantity or cost, and it expands a copy of a trader into one row per underlying instrument. The per lot `v_holdings` frame knows quantity and cost but has no sector, region or nature, and keys a copy as a single `COPY:` row. Neither alone can fill the table. The row key is therefore the consolidated instrument symbol, the same universe the heatmap uses, with quantity and cost for direct legs taken from the per ticker aggregate of `v_holdings` and for copy legs from the mirror cache. A symbol held both directly and inside a copy is one row with its values summed, which also keeps the table consistent with the heatmap and the Copilot. This is also why the copy constituent symbols had to be added to the daily download: without it, those rows would have no previous close and no price series at all, and the day change, the sparkline, the movers and the sector heat would all be undefined for them.

## References

No references were requested for this spec. The reasoning above stands on the repo's own conventions and the market data behaviour of the existing stack.
