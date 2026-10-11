# Verify: Investments & Holdings Simplification · spec 0006 · updated 2026-10-11
_Steps derived from spec 0006 acceptance criteria. `/check verify` runs these; `/test` locks the durable ones._

## UI / manual
- [ ] Navigate to `/investments` page → verify 4 top level tabs render cleanly (`📊 Portfolio & Holdings`, `⚖️ Allocation & Drift`, `💰 Income & Tax Strategy`, `🎯 Goals & Planning`) → AC-1
- [ ] Inspect Top KPI ribbon in `Portfolio & Holdings` tab → verify Total Portfolio Value (€), Total Cost Basis (€), Total Unrealized P&L (€), and Active Positions count render with semantic typography → AC-1, Value sourcing
- [ ] Toggle global "Hide values" in top app bar → verify all monetary values in KPI ribbon and holdings table are masked with `€****` → AC-2
- [ ] Review exposure visualizer in `Portfolio & Holdings` tab → verify 700px multi mode treemap is eliminated, replaced by native Asset Class allocation donut and horizontal Sector exposure bar with theme colors → AC-3
- [ ] Review holdings table → verify Direct Broker Holdings vs Copy Portfolio investments (`COPY:username`) are clearly distinguished with units, cost basis, current price, value, P&L, return %, and delayed status → AC-2, AC-7
- [ ] Inspect Market Quotes section → verify native quote table renders and TradingView iframe embed does NOT load until "Show external TradingView live quote stream" toggle is activated → AC-4
- [ ] Switch to `⚖️ Allocation & Drift` tab → verify profile selector, drift bar chart, and rebalancing targets table render cleanly in isolated fragment → AC-1
- [ ] Switch to `💰 Income & Tax Strategy` tab → verify dividend projection KPI cards, monthly payout calendar, dividend assets table, and tax-loss harvesting table render → AC-1
- [ ] Switch to `🎯 Goals & Planning` tab → verify FIRE trajectory simulation sliders and savings goals progress bars render → AC-1

## Commands
- [ ] `.\.venv\Scripts\pytest -v tests/test_investments_holdings.py` → all 5 tests pass verifying lifecycle transitions, atomic statement reconciliation, cost basis fallbacks, and rendering → AC-1, AC-2, AC-5, AC-6, AC-7
- [ ] `.\.venv\Scripts\python.exe -c "from db.database import connect; conn = connect(); assert 'status' in [r[1] for r in conn.execute('PRAGMA table_info(holdings)').fetchall()]; assert 'status' in [r[1] for r in conn.execute('PRAGMA table_info(v_holdings)').fetchall()]; conn.close(); print('Schema verified')"` → prints `Schema verified` → AC-5
- [ ] `.\.venv\Scripts\pytest` → full test suite passes with 139 passed tests → AC-1, AC-2, AC-5, AC-6, AC-7

## Acceptance-criteria coverage
- AC-1: Four top level tabs and isolated fragments covered by UI tab navigation steps and `test_investments_render_smoke`
- AC-2: Holdings table formatting, copy portfolio distinction, and privacy masking covered by UI steps and `test_copy_portfolio_labeling_and_privacy_masking`
- AC-3: Native allocation donut and exposure bar replacing treemap covered by UI exposure section step
- AC-4: Native market quotes with on demand TradingView toggle covered by UI market quotes step
- AC-5: Database migration adding status, closed_at, and active v_holdings view filter covered by commands and `test_holdings_lifecycle_and_v_holdings_filtering`
- AC-6: Atomic statement reconciliation repository method covered by `test_atomic_statement_reconciliation`
- AC-7: Unquoted asset cost basis valuation fallback with delayed badge covered by UI holdings step and `test_missing_quote_cost_basis_fallback`
