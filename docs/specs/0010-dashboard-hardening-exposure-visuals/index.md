# 0010. Dashboard Hardening & Exposure Visuals

**Date**: 2026-10-12
**Status**: Accepted

## Summary

This update strengthens database safety across dialogs and modernizes dashboard financial charts. We eliminate SQLite cross thread crashes by configuring non checking connections and isolating dialog connections cleanly. We also replace the custom iframe cash flow diagram with a standard Plotly Sankey and an expand modal, add rounded translucent glass styling to portfolio exposure treemaps, and display account cards in alphabetical order grouped by asset class.

## Context

The personal finance dashboard currently experiences runtime instability and visual rough edges across multiple components.

First, Streamlit modal dialogs (decorated with `@st.dialog`) run on separate worker threads. When dialogs like the category budget modal or full screen chart dialogs access SQLite connections created on parent threads, Python raises `sqlite3.ProgrammingError` because `check_same_thread` is active by default. Some dialogs attempt to reuse parent connections, leading to erratic crashes during user form submissions.

Second, the interactive cash flow Sankey diagram relies on a custom bi directional iframe component (`ui/sankey_component/`). This component uses postMessage communication to synchronize node selections back to Streamlit. In practice, this bridge is fragile, flickers during rerun cycles, and causes rendering inconsistencies between the dashboard and spending pages.

Third, the investments exposure visual (Market Carpet treemap) renders standard hard edged rectangles that clash with the dark glassmorphic design system established in earlier foundation slices.

Finally, the accounts grid displays connected bank and brokerage accounts in arbitrary repository insertion order. Users cannot locate specific institutions quickly, and accounts lack distinct visual cues distinguishing liquid cash from long term investment holdings.

## Requirements

**User stories**:
- As a personal finance user, I want modal dialogs to open and save without database thread crashes so that I can configure category budgets reliably.
- As a personal finance user, I want a clean, responsive cash flow Sankey diagram with full screen view so that I can trace money flows from income to expenses without component glitches.
- As an investor, I want the portfolio Market Carpet treemap to display modern rounded glass tiles so that asset allocations feel cohesive with the dark theme.
- As an account holder, I want my accounts ordered alphabetically within clear Cash and Investments groups with distinct accent colors so that I can scan balances immediately.

**Acceptance criteria**:
- **AC-1**: SQLite connections opened via `database.connect()` support multi thread execution without `ProgrammingError`, and all dialogs manage their own dedicated connection lifecycle inside a try finally block.
- **AC-2**: The category budget dialog (`set_category_budget_dialog`) opens, submits updates, and closes cleanly without any thread collision or connection leaks.
- **AC-3**: The fragile iframe Sankey component is retired in favor of a shared, reusable Plotly `go.Sankey` chart rendered directly with `st.plotly_chart` across both dashboard and spending views.
- **AC-4**: The Expenses panel provides a clean expand button that launches a full screen modal dialog displaying the high resolution Sankey diagram.
- **AC-5**: The Portfolio Exposure Market Carpet treemap renders semi transparent RGBA tiles and applies subtle border radius styling via targeted CSS rules.
- **AC-6**: Account cards on the dashboard are grouped into Cash and Investments sections, sorted alphabetically by institution and name within each section, and styled with semantic color accents (emerald for liquid cash, indigo for investments).

## Options considered

### Option 1: Native Plotly Sankey, global thread safety, and grouped alphabetical accounts (Recommended)

Configure `check_same_thread=False` directly inside `database.connect()` and enforce that dialogs always instantiate their own connection. Replace the custom iframe component with a pure Plotly `go.Sankey` function in `ui/charts.py` shared by both dashboard and spending pages. Add an expand button launching a dedicated full screen dialog. Style the Plotly treemap with RGBA fills and CSS border radius targeting Plotly SVG rectangles. Group account cards into Cash and Investments sections, sorting alphabetically with accent borders.

**Pros**:
- Eliminates thread exceptions across all present and future Streamlit dialogs.
- Removes the fragile iframe postMessage dependency and unifies Sankey rendering into a single tested module.
- Retains native Streamlit and Plotly performance without heavy DOM hacks.
- Organizes accounts logically while maintaining rapid visual scanning.

**Cons**:
- Direct CSS styling of Plotly SVG rectangle elements requires careful class targeting to avoid affecting unrelated charts.

### Option 2: Retain custom iframe component with postMessage error boundaries and thread local pooling

Keep the custom bi directional iframe component in `ui/sankey_component/`, adding timeout wrappers and retry handlers to the postMessage bridge. Introduce a thread local database connection pool helper rather than altering `database.connect()`. Keep a flat accounts grid sorted strictly by name.

**Pros**:
- Preserves the bi directional node click event mechanism in the iframe.
- Leaves `database.connect()` defaults untouched.

**Cons**:
- Retains substantial frontend JavaScript maintenance burden and iframe latency.
- Thread local pooling in Streamlit is complex and prone to memory leaks across rerun sessions.
- Flat alphabetical sorting mixes checking accounts with retirement portfolios confusingly.

## Decision

**Chosen option**: Option 1: Native Plotly Sankey, global thread safety, and grouped alphabetical accounts.

We will set `check_same_thread=False` in `database.connect()`, isolate dialog connection lifecycles, centralize the Plotly Sankey in `ui/charts.py` with an expand modal, style the Market Carpet treemap with translucent glassmorphic tiles, and order accounts alphabetically by asset class with semantic accents.

## Rationale

Thread safety in Streamlit is best solved at the connection boundary. Setting `check_same_thread=False` combined with explicit try finally connection scoping in dialogs eliminates the root cause of `ProgrammingError` without introducing complex pooling infrastructure.

The custom iframe Sankey added unnecessary complexity for cash flow visualization. Pure Plotly `go.Sankey` provides superior reliability, respects custom chart theme tokens, and works seamlessly inside standard Streamlit dialogs for full screen viewing. Sharing this implementation between `ui/pages/dashboard.py` and `ui/pages/spending.py` fulfills the single source of truth architecture rule.

Grouped alphabetical sorting offers the best usability balance. Users naturally separate day to day cash from investment portfolios. Grouping into Cash and Investments and then sorting alphabetically within each group delivers predictable card placement.

## Feature design

**Data model sketch**:
Existing schema tables (`accounts`, `categories`, `category_budgets`, `transactions`, `holdings`, `snapshots`) remain unchanged. No database migrations are required for this slice.

**API surface**:

| Function / Component | Module | Key inputs | Key outputs | Purpose | Key errors |
|---|---|---|---|---|---|
| `connect(db_path)` | `db/database.py` | `db_path: Path \| str` | `sqlite3.Connection` | Open SQLite connection with `check_same_thread=False` | `sqlite3.Error` |
| `set_category_budget_dialog()` | `ui/dialogs.py` | None | None | Modal dialog for category spending limits | Thread exceptions |
| `render_cash_flow_sankey()` | `ui/charts.py` | `conn, key_prefix, start_date, end_date, height` | None | Render pure Plotly Sankey diagram | Empty transactions |
| `open_sankey_fullscreen_dialog()` | `ui/charts.py` | `start_date, end_date` | None | Open full screen dialog for cash flow Sankey | None |
| `build_investments_market_carpet()` | `ui/charts.py` | `consolidated_df, height` | `go.Figure` | Build translucent treemap with glassmorphic styling | Empty holdings |
| `_render_accounts_grid()` | `ui/pages/dashboard.py` | `accounts, acc_balances, acc_subtexts` | None | Render grouped alphabetical account cards | Missing logo |

**Value sourcing**:

| Action | Value produced / displayed | Source |
|---|---|---|
| Dialog connection opening | Dedicated SQLite connection | Created locally via `database.connect()` in dialog function |
| Sankey cash flows | Inflow, fixed, discretionary, and savings nodes | Aggregated from `transactions` table via `prepare_cash_flow_sankey_data()` |
| Market Carpet tiles | Holdings exposure values and percentages | Aggregated from `holdings` table via `get_consolidated_holdings_df()` |
| Account card placement | Section group and sort position | Grouped by `account.asset_class` and sorted by `account.institution`, `account.name` |
| Account card accents | Border color and badge accent | Derived from asset class (`cash` -> emerald, `investment` -> indigo) |

**Key invariants**:
- Dialog functions must never accept parent database connections across thread boundaries. Every dialog must open its own connection and close it in a finally block.
- Cash flow calculations must use integer minor units internally before scaling to presentation floats.
- The iframe component directory `ui/sankey_component/` is retired and no longer imported by any page.
- Privacy mode (`hide_amounts`) must mask all numeric figures in both the standard and full screen Sankey and Market Carpet charts.

**Security model**:
- All operations execute against local SQLite database `data/finance.db`.
- Database write operations in dialogs use parameterized queries preventing SQL injection.
- No cloud calls or external telemetry are introduced.

**Critical test scenarios**:
- Multi thread dialog execution: Open `set_category_budget_dialog` and save budget updates concurrently across simulated threads without raising `ProgrammingError`, verifies **AC-1**, **AC-2**.
- Shared Sankey rendering: Render `render_cash_flow_sankey` on dashboard and spending views using identical data without iframe bridge warnings, verifies **AC-3**.
- Full screen Sankey dialog: Trigger the expand button in the Expenses panel and verify that the full screen modal renders the complete cash flow diagram, verifies **AC-4**.
- Glassmorphic treemap styling: Generate Market Carpet figure and verify RGBA opacity values and custom CSS rules apply to Plotly rectangles, verifies **AC-5**.
- Grouped alphabetical account cards: Supply unsorted accounts across cash and investment types and verify output groups cards into Cash and Investments sections sorted alphabetically with distinct accents, verifies **AC-6**.

## Migration plan

**Strategy**: Direct replacement of custom component with native Plotly chart.
**Phases**:
1. Update `database.connect()` with `check_same_thread=False` and audit all dialogs in `ui/dialogs.py` to ensure local connection ownership.
2. Centralize pure Plotly Sankey and full screen dialog helper in `ui/charts.py`.
3. Update `ui/pages/dashboard.py` and `ui/pages/spending.py` to use the standardized Sankey and remove all imports of `ui.sankey_component`.
4. Enhance `build_investments_market_carpet` in `ui/charts.py` and CSS in `ui/theme/common.css` for rounded glass tiles.
5. Refactor accounts grid in `ui/pages/dashboard.py` into Cash and Investments groups with alphabetical sorting and semantic color accents.
6. Remove unused files in `ui/sankey_component/`.
**Rollback**: Revert git commits to restore previous dialog wrappers and iframe component if needed.
**Risks**: Low risk since schema is untouched and changes are isolated to UI presentation and connection configuration.

## Build plan

1. [x] Add `check_same_thread=False` to `database.connect()` in `db/database.py` and enforce isolated connection lifecycles across all dialogs in `ui/dialogs.py`, satisfies **AC-1**, **AC-2**.
2. [x] Refactor `render_cash_flow_sankey` in `ui/charts.py` to use pure `go.Sankey` with `st.plotly_chart` and provide `open_sankey_fullscreen_dialog`, satisfies **AC-3**, **AC-4**.
3. [x] Replace all remaining invocations of `ui.sankey_component` in `ui/pages/dashboard.py` and `ui/pages/spending.py` with the shared chart helper and remove deprecated iframe files, satisfies **AC-3**.
4. [x] Update `build_investments_market_carpet` in `ui/charts.py` with translucent RGBA palette and add CSS rules for rounded SVG treemap tiles in `ui/theme/common.css`, satisfies **AC-5**.
5. [x] Update `_render_accounts_grid` in `ui/pages/dashboard.py` to group accounts into Cash and Investments, sort cards alphabetically within each group, and apply semantic border accents, satisfies **AC-6**.
6. [x] Implement comprehensive unit tests verifying thread safety, shared Sankey rendering, and account sorting order, satisfies **AC-1**, **AC-2**, **AC-3**, **AC-5**, **AC-6**.

## Consequences

**Positive**:
- Eliminates recurring SQLite thread crashes in Streamlit modal dialogs.
- Eliminates brittle iframe component postMessage communications.
- Unifies cash flow visualization into a single maintainable Plotly implementation across pages.
- Improves visual aesthetics of portfolio exposure with modern rounded translucent tiles.
- Makes account cards easier to locate with grouped alphabetical organization and clear visual accents.

**Negative**:
- Interactive click to drill down on individual Sankey nodes inside the dashboard is simplified to full screen dialog expansion and tab level inspection.

## Follow-up

- [ ] Audit Copilot and background sync workers to ensure all thread contexts continue using isolated database connections cleanly.
- [ ] Ensure future investment exposure dimensions (Slice 11) reuse the refined treemap glassmorphic styling tokens.
