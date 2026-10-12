# 0012. Investment Exposure Dimensions, TradingView Watchlist, and Realized P&L

**Date**: 2026-10-12
**Status**: In Progress

## Summary

This build spec upgrades the portfolio analytics and market tracking inside the investments view for Slice 11. We expand portfolio allocation visuals beyond simple asset classes to multi dimension exposures (Sector, Region, Currency, Asset Class) via an interactive dimension switcher. A minimizable, scrollable live TradingView watchlist card tracks all distinct active holdings without overwhelming vertical screen space. We introduce a dedicated Realized Profit and Loss (Realized P&L) panel and database tracking for closed positions, and move the cached market news feed exclusively to the bottom of the investments page.

## Requirements

**User stories**:
- As an investor, I want to toggle between sector, region, currency, and asset class views so that I can analyze portfolio diversification across multiple risk dimensions.
- As an active market tracker, I want a compact, minimizable TradingView watchlist of my direct holdings so that I can monitor live quotes with custom scrolling without cluttering the screen.
- As a wealth builder, I want to track realized profit and loss from closed positions alongside unrealized gains so that I can audit historical trading performance.
- As a dashboard user, I want the market news feed consolidated at the bottom of the investments page so that the primary dashboard remains focused on net worth and cash flow KPIs.

**Acceptance criteria**:
- **AC-1**: The Portfolio Allocation section in `ui/pages/investments.py` provides an interactive dimension switcher (Sector, Region, Currency, Asset Class) using segmented pills that dynamically updates the donut chart, breakdown bars, and allocation data tables.
- **AC-2**: Portfolio exposure calculations group and aggregate values across the active dimension cleanly, handling unknown or null values with friendly defaults (such as Other or Global) and respecting privacy masking via `is_hidden()`.
- **AC-3**: A minimizable live TradingView watchlist card renders direct holdings with an embedded scroll container constrained to a maximum height of 320px, preserving collapsed state across page interactions in session state.
- **AC-4**: A new database migration adds `realized_pnl_minor INTEGER DEFAULT 0` and `realized_proceeds_minor INTEGER DEFAULT 0` columns to the `holdings` table to preserve exact historical sale returns for closed positions (`status = 'closed'`).
- **AC-5**: `db/repositories/holding_repository.py` provides helper queries `get_realized_pnl_summary(conn)` and `get_closed_holdings_df(conn)` returning total realized gains, total proceeds, and closed position records with sale dates.
- **AC-6**: A dedicated Realized P&L panel displays cumulative realized profit, return percentages, and a table of closed positions with privacy masking support.
- **AC-7**: The cached eToro market news feed component is removed from `ui/pages/dashboard.py` and placed cleanly at the bottom of `ui/pages/investments.py`.

## Decision

**Chosen option**: Option 1: Multi dimension switcher, persistent closed position tracking, and compact embedded watchlist (see `rationale.md`).

We expand portfolio exposure analytics through unified client side dimension filtering, store closed position realized metrics directly on the holdings record, embed a constrained TradingView container, and relocate news to the investments view.

## Feature design

**Data model sketch**:
Database migration `0006_holdings_realized_pnl.sql`:
- `holdings`:
  - `realized_pnl_minor` INTEGER NOT NULL DEFAULT 0 (realized profit or loss in minor units / cents)
  - `realized_proceeds_minor` INTEGER NOT NULL DEFAULT 0 (total sell proceeds in minor units / cents)
  - Existing fields utilized: `status` ('active', 'closed'), `closed_at`, `cost_basis_minor`, `currency`, `quantity`, `ticker`, `name`

**API and repository surface**:

| Function / Module | Signature | Key inputs | Outputs / Behavior | Key errors / Guarantees |
|---|---|---|---|---|
| `db/repositories/holding_repository.py` | `get_realized_pnl_summary(conn) -> dict[str, Any]` | SQLite connection | Dictionary with `realized_pnl_eur`, `total_proceeds_eur`, `closed_count` | Returns zeros safely when no closed holdings exist |
| `db/repositories/holding_repository.py` | `get_closed_holdings_df(conn) -> pd.DataFrame` | SQLite connection | DataFrame of closed positions with ticker, name, cost basis, proceeds, realized pnl, closed date | Empty DataFrame when none exist |
| `services/portfolio.py` | `get_dimension_exposure_df(consolidated_df, dimension: str) -> pd.DataFrame` | Consolidated holdings DataFrame, dimension string | Aggregated DataFrame with bucket, value_eur, weight_pct | Gracefully falls back to 'Other' for missing metadata |

**Value sourcing**:

| Action | Value produced / displayed | Source |
|---|---|---|
| Exposure Dimension Switcher | Selected dimension ('sector', 'region', 'currency', 'asset_type') | User interactive pill widget state |
| Exposure Allocation Charts | Grouped values and percentage weights | Computed on demand from `consolidated_df` in `services/portfolio.py` |
| TradingView Watchlist | Unique active ticker list | Distinct direct broker tickers in `holdings_df` where status is active |
| Realized P&L Summary KPI | Total realized profit or loss | Aggregated from `holdings.realized_pnl_minor` for rows where `status = 'closed'` |
| Realized P&L Table | Closed position records | Sourced from `HoldingRepository.get_closed_holdings_df(conn)` |
| Market News Feed | Cached eToro news cards | Fetched via `connectors.etoro_service.fetch_news()` inside an isolated Streamlit fragment |

**Key invariants**:
- Privacy masking: All financial amounts and percentages across the dimension table, Realized P&L KPIs, and closed holdings table must respect `is_hidden()`.
- Thread safety: Database connections open cleanly via `database.connect()` with `check_same_thread=False` where needed and close in `finally` blocks.
- Non zero division: Return percentages and allocation weights safely guard against zero cost basis or zero total portfolio value.

**Security and privacy model**:
- All financial holdings and realized gain metrics stay strictly local in `data/finance.db`.
- External TradingView iframe widget renders only publicly traded symbol tickers, without sending user quantities, account balances, or financial values to external servers.

**Critical test scenarios**:
- Multi dimension exposure aggregation: verifies **AC-1**, **AC-2**
- TradingView minimizable card rendering and session state: verifies **AC-3**
- Realized P&L migration and repository calculations: verifies **AC-4**, **AC-5**
- Closed positions table rendering and privacy masking: verifies **AC-6**
- Market news relocation to investments page bottom: verifies **AC-7**

## Build plan

1. [x] Create migration `0006_holdings_realized_pnl.sql` adding `realized_pnl_minor` and `realized_proceeds_minor` to `holdings`, satisfies **AC-4**
2. [x] Implement `get_realized_pnl_summary` and `get_closed_holdings_df` in `HoldingRepository`, satisfies **AC-5**
3. [x] Implement `get_dimension_exposure_df` in `services/portfolio.py` supporting Sector, Region, Currency, and Asset Class aggregation, satisfies **AC-2**
4. [x] Update `ui/pages/investments.py` with dimension switcher pills and dynamic exposure charts, satisfies **AC-1**, **AC-2**
5. [x] Build minimizable scrollable TradingView card in `ui/pages/investments.py`, satisfies **AC-3**
6. [x] Implement Realized P&L panel and closed positions table in `ui/pages/investments.py` with privacy masking, satisfies **AC-6**
7. [x] Remove market news from `ui/pages/dashboard.py` and mount at the bottom of `ui/pages/investments.py`, satisfies **AC-7**
8. [x] Add automated unit test suite verifying exposure calculations, realized P&L repository logic, and privacy masking, satisfies **AC-1**, **AC-2**, **AC-4**, **AC-5**, **AC-6**

## Consequences

**Positive**:
- Deep exposure insights across sectors, regions, currencies, and asset classes in a unified interface.
- Complete auditability of historical trading performance with realized profit and loss.
- Better dashboard focus with market news moved to the dedicated investments context.
- Streamlined quote stream using compact scrollable container that prevents vertical page bloat.

**Negative**:
- Adds two minor unit integer columns to the holdings table.
- TradingView widget requires internet connectivity to load public chart frames.
