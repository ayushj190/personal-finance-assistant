# 0012. Rationale: Investment Exposure Dimensions, TradingView Watchlist, and Realized P&L

## Context

The personal finance investments view previously offered fixed high level visualizations: a donut chart for asset class and a single horizontal bar for sectors. Investors managing diversified global assets need multidimensional risk views across geographies (regions), base currencies, and specific themes.

Additionally, while unrealized gains for active open positions are clearly calculated, the system lacked dedicated reporting for realized profit and loss resulting from past sales and closed positions. When an asset position closes, historical gains must remain accessible without requiring manual transaction ledger queries.

Finally, the live TradingView quotes widget previously expanded to an unbounded height depending on the count of direct holdings, pushing other controls off screen, while the eToro market news feed sat on the main dashboard rather than in the investment area where market research occurs.

## Options considered

### Option 1: Multi dimension switcher, persistent closed position tracking, and compact embedded watchlist (Chosen)

We add an interactive dimension switcher directly above the allocation charts, dynamically reshaping the donut and distribution bar based on the chosen lens (Sector, Region, Currency, Asset Class). Closed position proceeds and realized profit are persisted in minor units on the `holdings` table, surfaced in a dedicated Realized P&L panel. The TradingView widget is wrapped in a compact, scrollable container with a toggle to minimize. Market news moves to the investments page.

**Pros**:
- Single intuitive interface for all exposure angles without cluttered multi chart sprawl.
- High performance calculation leveraging existing `consolidated_df` data structures.
- Exact tracking of historical closed gains in integer minor units.
- Clean visual layout with height constrained quotes and properly placed news.

**Cons**:
- Requires a small schema migration to add minor unit fields for closed positions.

### Option 2: Static stacked subtabs for every dimension and separate transaction queries

Create independent subtabs for each dimension (one tab for Sector, one for Region, one for Currency), and compute realized P&L on the fly by scanning and matching historical buy and sell transactions in the `transactions` table.

**Pros**:
- No schema change to the `holdings` table.

**Cons**:
- Inflexible tab navigation that fragments portfolio analysis across multiple screens.
- Expensive and fragile transaction parsing to infer closed holding cost basis and exit prices.
- Higher risk of calculation mismatches across different broker statement formats.

## Rationale

Option 1 provides clean architectural separation and superior user experience. Storing closed position realized profit and proceeds directly in `holdings` matches the lifecycle pattern introduced in migration `0005_holdings_status_and_reconciliation.sql`. It ensures that historical performance metrics are instant to query and remain permanent even when old transaction details are purged or reclassified.

The interactive dimension switcher lets users drill down into risk concentrations without tab hopping, while the height constrained TradingView container keeps the interface neat and responsive. Moving market news from the dashboard to the investments page aligns with domain boundaries and keeps the dashboard uncluttered.
