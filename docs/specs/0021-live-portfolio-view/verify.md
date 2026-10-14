# Verification Plan: Live portfolio view for the Investments page

Verify each acceptance criterion in the running app before closing the feature. Note that several checks depend on the time of day, so run the in hours checks during the 09:00 to 22:00 Europe/Amsterdam weekday window and the closed market checks outside it.

- [ ] Open Investments, Portfolio tab -> verify the first block under the KPI ribbon is the live portfolio table with one row per distinct instrument symbol, including copied positions, and that the columns read Name with ticker, Quantity, Avg open, Price, Day change percent, Day P&L EUR, Cost basis, Market value, Total P&L EUR, Total P&L percent, Weight percent and Sparkline -> AC-1
- [ ] Open a fresh session (or restart the app) and watch the first render -> verify it shows stored closes and does not claim to be live until the first poll completes -> AC-5
- [ ] During market hours, watch the last refreshed indicator -> verify prices refresh about every 60 seconds and that the page does not jump or rerun outside the table -> AC-2
- [ ] Compare a row's Day change percent against the ticker tape entry for the same symbol, and add the row Day P&L values -> verify they sum to the portfolio Day P&L card, and that the card's percent equals day P&L over the previous close portfolio value -> AC-3, AC-7
- [ ] Outside market hours (or by moving the clock past 22:00 Amsterdam time, in both winter and summer time) -> verify no network call is made, prices hold at the last close, and the closed badge names the newest price date -> AC-4
- [ ] Inspect a copied position in the table -> verify it shows a copy tag, and for an unresolved `ID_` symbol that it shows the eToro mirror value with no day change and is not counted in the unpriced count -> AC-1, AC-5, AC-6
- [ ] Find a position with no live quote -> verify it keeps a price with its age in minutes (or days when the price came from the stored close), and still counts toward the totals -> AC-5
- [ ] Disconnect the network and wait for a poll, then leave it disconnected past the request timeout -> verify the table keeps its numbers and one quiet delayed line appears with no error wall, no hang and no exception in the log -> AC-5
- [ ] Scroll the Portfolio tab -> verify there is no donut, no horizontal exposure bar, no TradingView iframe and no separate Copied Traders section, that mirror rows show a copy tag, that the exposure treemap sits below the live table, and that switching its Sector, Region, Currency and Nature pills changes the treemap grouping -> AC-6
- [ ] Read the KPI ribbon -> verify five cards and that Day P&L shows a euro amount with a percent subtext, and Quote Status shows live or delayed plus an unpriced count -> AC-7
- [ ] Look directly under the KPI ribbon -> verify the movers strip shows three gainers and three losers, each with a generated ticker chip and a signed percent, and that no image is fetched -> AC-8
- [ ] Inspect the equity curve with at least two snapshot days present -> verify a value line with a stepped cost basis line, that the 1M, 3M, 6M, 1Y and All pills change the range with 3M as the default, and that the value line agrees with the investment account snapshot series -> AC-9
- [ ] Start the app twice on the same day -> verify `SELECT COUNT(*) FROM portfolio_snapshots WHERE snapshot_date = date('now','localtime')` returns 1 and the values are in integer minor units. Leave a session open across midnight and verify the next day's row is written -> AC-10
- [ ] Inspect the P&L contribution chart and the sector performance grid -> verify per holding profit and loss ranked by euro, and sectors coloured by weighted day move -> AC-11
- [ ] Use the search box, click column headers, and scroll the table body -> verify filtering by ticker and name, sorting works, the height stays fixed at 420px, and the default sort is market value descending -> AC-12
- [ ] Toggle Hide values on and click a masked money column header -> verify euro amounts and cost figures mask while prices, quantities and percentages stay readable, and that the masked column still sorts by the underlying number -> AC-12, AC-13
- [ ] Scan every signed figure in the new view -> verify each shows a sign, so colour is not the only signal -> AC-14
- [ ] Inspect the dashboard market carpet -> verify it groups by asset nature and has no dimension pills -> AC-15
- [ ] Watch the dashboard ticker tape -> verify it updates on the same poll cadence as the Investments page, lists every distinct consolidated asset, and falls back to the stored close for anything unpriced -> AC-16
- [ ] Ask the Copilot "sort my holdings by day change", then "show only my technology holdings", then "show only losers" -> verify the live table reorders and filters, that the page scrolls to the live view, and that an invented sort column, mover value or focus bucket is refused with a note instead of applied -> AC-17
- [ ] Ask the Copilot "what is my day P&L" -> verify the answer matches the Day P&L card on the page -> AC-18
- [ ] Open the Income tab -> verify the per holding dividend table is collapsed behind an expander and the tax loss harvesting panel is gone -> AC-19
- [ ] Run `python run_tests.py` -> verify the suite passes and the app starts with no new warnings -> AC-20
