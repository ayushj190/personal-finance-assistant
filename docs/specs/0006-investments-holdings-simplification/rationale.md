# 0006. Investments & Holdings Simplification (Rationale)

## Context

The investment tracking view currently serves as an all in one dashboard containing eight dense sections on a single scrolling canvas. It includes portfolio totals, a seven hundred pixel treemap with five separate viewing modes, copy trader positions with embedded TradingView market widgets, direct holdings tables, second embedded TradingView quote feeds, allocation drift rebalancing tables, forward dividend cash flow projections, tax loss harvesting assistants, and long term financial independence projections with interactive savings goal forms.

This layout creates two major operational and experiential challenges:

First, the visual density and page weight cause substantial interface clutter and performance degradation. External TradingView widget scripts and iframes load repeatedly, causing layout shifts, visual noise, and latency whenever portfolio state refreshes. The multi mode treemap occupies excessive vertical space while providing little actionable insight beyond basic sector breakdowns. Secondary tasks like retirement planning and savings goals are pushed hundreds of pixels below the fold, where they distract from routine portfolio check ins.

Second, the statement import pipeline suffers from position desync. When users upload broker export files, such as eToro CSV statements, the existing database logic executes an upsert query that only touches positions currently listed in the file. If an investor sells or closes a holding, that position is omitted from subsequent broker statements. Because the database never marks absent positions as liquidated or removes them, closed holdings linger indefinitely with stale quantities and cost bases. Over time, active portfolio records diverge significantly from broker reality, inflating net worth calculations and distorting asset allocation recommendations.

Resolving these issues requires introducing position lifecycle tracking in the database, implementing atomic statement reconciliation, and reorganizing the user interface into structured, task focused views.

## Options considered

### Option 1: Top level tabbed portfolio hierarchy with native visual summaries and atomic statement reconciliation

Reorganize the investments page into four clean top level tabs (`Portfolio & Holdings`, `Allocation & Drift`, `Income & Tax Strategy`, `Goals & Planning`). Replace the multi mode treemap with a clean allocation donut and exposure summary bar. Replace heavy external TradingView embeds with native Streamlit quote cards and an on demand modal or toggle. Add `status` and `closed_at` columns to `holdings`, update `v_holdings` to filter active positions, and implement `reconcile_account_holdings` in `HoldingRepository` to automatically mark omitted positions as closed on statement import.

**Pros**:
- Solves position desync completely by reconciling account holdings during broker imports.
- Eliminates page clutter by separating core holdings review from secondary rebalancing, income, and planning workflows.
- Eliminates iframe flicker, heavy network transfers, and layout shifts.
- Retains full historical transaction and closed position records for tax calculations and audits.

**Cons**:
- Navigating between active holdings and rebalancing tools requires clicking across tabs rather than continuous scrolling.

### Option 2: Single scrolling page with accordion expanders and manual position cleanup

Retain all eight sections on a single scrolling page canvas, but wrap secondary tools (rebalancing, dividends, tax loss, goals) inside collapsed expander containers. Address desync by providing a manual cleanup button that allows users to delete or zero out individual stale holdings.

**Pros**:
- Preserves the single page mental model without tab switching.
- Minimizes changes to navigation structure.

**Cons**:
- Expander containers still clutter the document object model and create long vertical pages.
- Manual position cleanup forces the user to identify and fix desynced holdings by hand, which is error prone and tedious.
- Fails to address repeated iframe reload overhead when expanders open.

### Option 3: Separate investment sub pages in Streamlit sidebar navigation

Split the investments module into two or three distinct page entries in the Streamlit application sidebar (for example, `Portfolio Holdings`, `Portfolio Rebalancing`, and `Financial Goals`).

**Pros**:
- Isolates each workflow into a completely independent page file.

**Cons**:
- Clutters the global application navigation sidebar with too many granular sub pages.
- Fragments the unified investment mental model, making routine portfolio review feel disjointed.

## Rationale

Option 1 is selected because it provides the optimal balance of workflow clarity, performance, and automation. By dividing the investments view into four logical tabs, users can focus on active performance without getting bogged down in complex rebalancing tables or long term retirement models. Replacing bulky treemaps and external iframe widgets with native Plotly donuts and Streamlit metric components delivers immediate visual polish and snappy page rendering.

Crucially, implementing atomic reconciliation in `HoldingRepository.reconcile_account_holdings` solves the root cause of statement desync. Rather than requiring manual intervention, the system automatically detects when previously held assets are no longer present in an imported statement, setting their active quantity to zero and updating position lifecycle timestamps inside a single database transaction. This keeps active views in `v_holdings` perfectly synchronized with broker statements while preserving full historical records for tax and performance reporting.
