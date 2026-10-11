# 0006. Investments & Holdings Simplification

**Date**: 2026-10-11
**Status**: Accepted

## Summary

This decision simplifies the portfolio investment interface and eliminates position desync during statement imports. The sprawling single page investment canvas is restructured into four clean top level tabs for portfolio holdings, asset allocation drift, dividend and tax optimization, and financial goals. Heavy multi mode treemaps and external iframe widgets are replaced with native allocation donuts, exposure bars, and on demand quote feeds. The database schema receives a position lifecycle status field, and broker statement imports execute atomic reconciliation so closed or sold holdings never linger as active assets.

## Context

The rationale and decision context are recorded in rationale.md.

## Requirements

**User stories**:
- As an investor, I want a clean portfolio hierarchy so that I can see total performance, asset class distribution, and individual holdings without visual clutter.
- As an investor, I want broker statement imports to update my holdings accurately so that closed or sold positions do not remain visible as phantom active assets.
- As an investor, I want noisy visual drilldowns replaced with lightweight native charts so that the page loads quickly and stays responsive.
- As an investor, I want rebalancing tools, dividend forecasts, tax loss harvesting, and FIRE projections organized into focused views so that secondary workflows do not get in the way of reviewing active holdings.

**Acceptance criteria**:
- **AC-1**: The investment page layout is organized into four top level tabs (`📊 Portfolio & Holdings`, `⚖️ Allocation & Drift`, `💰 Income & Tax Strategy`, and `🎯 Goals & Planning`), isolating active holdings from secondary rebalancing, income, and retirement planning tools.
- **AC-2**: Holdings table clearly distinguishes direct broker holdings from copy portfolio investments (`COPY:username`), formatting units, cost basis, current market price, value in euros, unrealized profit and loss in euros, and percentage return with full support for privacy masking via `is_hidden()`.
- **AC-3**: Exposure visualizer replaces the seven hundred pixel multi mode treemap with a clean asset class and sector allocation donut chart and horizontal exposure bar, using semantic colors from `ui/theme/`.
- **AC-4**: Heavy external TradingView market quote iframe widgets are replaced with lightweight native quote metrics and an on demand toggle, preventing layout shifts and unnecessary network requests.
- **AC-5**: Database migration adds `status` (TEXT NOT NULL DEFAULT 'active' CHECK in ('active', 'closed')) and `closed_at` (TEXT NULL) to the `holdings` table, and updates the `v_holdings` view to filter active positions where quantity is greater than zero and status equals 'active'.
- **AC-6**: `HoldingRepository.reconcile_account_holdings` performs atomic statement reconciliation inside a single database transaction, inserting or updating incoming statement holdings with active status and marking existing positions for that account absent from the statement as closed with zero quantity, closed status, and current closed timestamp.
- **AC-7**: Holdings with missing market quotes or unlisted tickers fall back safely to cost basis valuation with a visible quote delayed indicator, preventing portfolio values from crashing to zero.

## Options considered

Options and trade offs are evaluated in rationale.md.

## Decision

**Chosen option**: Option 1: Top level tabbed portfolio hierarchy with native visual summaries and atomic statement reconciliation.

The investment page is organized into four tabs, heavy treemaps and embeds are replaced with native charts, and broker statement imports execute atomic reconciliation with position status tracking.

## Rationale

Reasoning and options: see rationale.md.

## Feature design

**Data model sketch**:

A database migration (`db/migrations/0005_holdings_status_and_reconciliation.sql`) updates the `holdings` table and `v_holdings` view:

| Entity | Primary Key | Foreign Keys | Key Fields | Purpose |
|---|---|---|---|---|
| `accounts` | `id` | None | `name`, `institution`, `currency`, `asset_class` | Financial accounts |
| `holdings` | `id` | `account_id -> accounts.id` | `ticker`, `isin`, `name`, `asset_type`, `region`, `sector`, `quantity`, `cost_basis_minor`, `currency`, `status`, `closed_at`, `updated_at` | Investment positions with active and closed lifecycle status |
| `market_quotes` | `(ticker, quote_date)` | None | `close`, `prev_close`, `currency`, `fetched_at` | Historical and latest market price quotes |
| `v_holdings` | None (View) | Joined on `account_id` and `ticker` | `cost_basis`, `latest_close`, `value_eur`, `unrealized_pnl_eur`, `status`, `updated_at` | Computed active portfolio view filtered by `quantity > 0` and `status = 'active'` |

**State transitions**:
`holdings.status`:
- `active`: position currently held with `quantity > 0`. Initial state on statement import or manual position entry.
- `closed`: position liquidated or absent from imported broker statement. Set when `quantity = 0`, records `closed_at = datetime('now')`. Reopens to `active` if new statement contains non zero units.

**Interface surface**:

Repository and service methods:
- `HoldingRepository.reconcile_account_holdings(conn, account_id: int, statement_holdings: list[dict[str, Any]]) -> dict[str, int]`: executes in an atomic transaction; upserts statement positions as active, marks previously active holdings for this account missing from statement as closed (`quantity = 0`, `status = 'closed'`, `closed_at = now()`), returns counts dictionary (`upserted`, `closed`, `active_total`).
- `HoldingRepository.get_v_holdings_df(conn, include_closed: bool = False) -> pd.DataFrame`: returns active positions by default, or all positions when `include_closed=True`.
- `HoldingRepository.get_portfolio_kpis(conn) -> dict[str, Any]`: returns portfolio value, total cost basis, unrealized profit and loss, return percentage, and unquoted holdings count.

**Value sourcing**:

| Action or Element | Value produced or displayed | Source |
|---|---|---|
| Top KPI Ribbon | Total Portfolio Value (€) | Sum of `value_eur` across active holdings in `v_holdings`, falling back to cost basis for unquoted tickers |
| Top KPI Ribbon | Total Cost Basis (€) | Sum of `cost_basis` in `v_holdings` |
| Top KPI Ribbon | Total Unrealized P&L (€) | `Total Portfolio Value - Total Cost Basis` |
| Top KPI Ribbon | Return Percentage (%) | `(Total Unrealized P&L / Total Cost Basis) * 100` |
| Exposure Donut | Allocation by Asset Class or Sector | Grouped sum of `value_eur` in active `v_holdings` by `asset_type` or `sector` |
| Exposure Bar | Sector Weight Percentage (%) | `(sector_value / total_portfolio_value) * 100` |
| Holdings Table | Asset Class Badge | `h.asset_type` (mapped to ETF, Stock, Crypto, Commodity, Bond) |
| Holdings Table | Position Type Badge | 'Direct Holding' vs `Copy: {username}` derived from ticker prefix `COPY:` |
| Statement Import | Reconciled Active Positions | Fresh parsed positions from uploaded broker export |
| Statement Import | Closed Positions | Set of existing active tickers for account minus incoming statement tickers |

**Key invariants**:
- Active portfolio view invariant: `v_holdings` includes only positions where `quantity > 0` and `status = 'active'`. Closed positions remain in `holdings` for audit and tax reporting but never appear in active portfolio totals.
- Valuation continuity invariant: if a ticker lacks an active market quote or foreign exchange rate, position value defaults to `cost_basis` and displays a `Quote delayed` badge rather than dropping to zero.
- Currency representation invariant: monetary amounts in `holdings` are stored as integer minor units (cents) in `cost_basis_minor` and converted to floating point euros only at the presentation boundary.
- Atomic reconciliation invariant: statement reconciliation runs inside a single database transaction (`with conn:`), ensuring an import never leaves the database partially updated.

**Security model**:
- Local first architecture: all portfolio records reside in local SQLite database `data/finance.db`.
- No cloud credentials or remote portfolio telemetry.
- Privacy mode masking via `is_hidden()` covers all four tabs (masks numerical balances with `€****`).

**Critical test scenarios**:
- Position lifecycle and reconciliation: importing an updated broker statement marks missing positions as closed, updates present positions, and leaves historical tax records intact, verifying **AC-5**, **AC-6**.
- Active holdings view filtering: query against `v_holdings` returns only active positions with positive quantities, verifying **AC-2**, **AC-5**.
- Missing quote fallback: position without quote data displays cost basis with delayed quote indicator, verifying **AC-7**.
- Tabbed layout navigation: page renders all four tabs without key collisions or unexpected reruns, verifying **AC-1**, **AC-3**, **AC-4**.

## Build plan

Ordered by the project Tracer Bullet approach (standing up thin vertical schema and reconciliation logic first, then building the streamlined tabbed UI, and concluding with verification tests):

- [x] 1. Create migration `db/migrations/0005_holdings_status_and_reconciliation.sql` adding `status` and `closed_at` columns to `holdings` and updating `v_holdings` view with active position filter, satisfies **AC-5**.
- [x] 2. Implement `HoldingRepository.reconcile_account_holdings` and wire into `ui/pages/import_files.py`, satisfies **AC-5**, **AC-6**.
- [x] 3. Refactor `ui/pages/investments.py` into four top level tabs (`Portfolio & Holdings`, `Allocation & Drift`, `Income & Tax Strategy`, `Goals & Planning`), satisfies **AC-1**.
- [x] 4. Rebuild the `Portfolio & Holdings` tab with four KPI ribbon, clean allocation donut, horizontal exposure bar, copy portfolio distinction, unquoted asset fallback, and on demand quote toggles, satisfies **AC-2**, **AC-3**, **AC-4**, **AC-7**.
- [x] 5. Relocate allocation rebalancing, dividend forecasting, and savings goals into tabs two, three, and four within isolated Streamlit fragments, satisfies **AC-1**.
- [x] 6. Implement automated test suite in `tests/test_investments_holdings.py` covering lifecycle transitions, statement reconciliation, and presentation fallbacks, satisfies **AC-1**, **AC-2**, **AC-5**, **AC-6**, **AC-7**.

## Consequences

**Positive**:
- Eliminates phantom active holdings after selling positions via automated statement reconciliation.
- Removes excessive visual noise and vertical scrolling on the investments page.
- Drastically reduces page weight and network overhead by replacing heavy iframe embeds with native metrics.
- Isolates secondary tools (rebalancing, dividend forecasts, FIRE goals) into dedicated tabs without rerun interference.

**Negative / tradeoffs**:
- Viewing allocation drift or dividend forecasts requires switching tabs rather than scrolling down a single continuous page.
- Live market charts from TradingView require clicking an on demand view toggle rather than loading automatically on page start.

**Neutral**:
- Preserves existing allocation profile tables and dividend projection calculation routines without changes to external API contracts.

## Migration plan

**Strategy**: Strangler schema migration with backwards compatible defaults.
**Phases**:
1. Run migration `0005_holdings_status_and_reconciliation.sql` adding `status` default 'active' and recreating `v_holdings`.
2. Existing holdings default to 'active', preserving current portfolio totals without data loss.
3. Subsequent statement imports apply `reconcile_account_holdings` to maintain synchronization automatically.
**Rollback**: If migration fails, revert `v_holdings` view definition to query without status filter; columns `status` and `closed_at` remain nullable without breaking existing queries.
**Risks**: Broker statements with mismatched ticker formats could mistakenly mark a position closed. Mitigated by matching on ticker and ISIN where available.

## Follow-up

- [ ] Verify that importing an eToro statement correctly updates both direct positions and copy portfolio parent holdings during `/check verify`.
