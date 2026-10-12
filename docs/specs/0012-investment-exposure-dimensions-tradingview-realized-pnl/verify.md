# Verification Plan: Investment Exposure Dimensions, TradingView Watchlist, and Realized P&L

Verify each acceptance criterion before closing Slice 11:

- [ ] Inspect Portfolio Allocation in `ui/pages/investments.py` -> verify dimension switcher toggles between Sector, Region, Currency, and Asset Class, updating both chart visuals and breakdown percentages -> AC-1, AC-2
- [ ] Test privacy toggle -> verify that toggling hide values masks all exposure euro amounts and percentages across charts and tables -> AC-2
- [ ] Inspect TradingView live quotes widget -> verify it renders in a compact container with max height 320px and internal vertical scroll, and verify minimizing collapses the widget cleanly -> AC-3
- [ ] Verify migration `0006_holdings_realized_pnl.sql` applies without errors and creates `realized_pnl_minor` and `realized_proceeds_minor` -> AC-4
- [ ] Query `HoldingRepository.get_realized_pnl_summary` and `get_closed_holdings_df` -> verify accurate aggregation of closed position records -> AC-5
- [ ] Inspect Realized P&L panel in investments view -> verify summary KPIs (Total Realized Gains, Net Return %) and closed position records table render with clean formatting -> AC-6
- [ ] Inspect Dashboard -> verify Market News is removed -> AC-7
- [ ] Inspect Investments page bottom -> verify Market News fragment renders cleanly -> AC-7
- [ ] Run test suite -> verify all unit tests pass -> AC-1 through AC-7
