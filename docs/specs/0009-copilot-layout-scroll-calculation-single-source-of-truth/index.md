# 0009. Copilot Layout Scroll and Calculation Single Source of Truth

**Date**: 2026-10-12
**Status**: Accepted

## Summary

This decision stabilizes the Copilot sidebar viewport layout and unifies portfolio calculations across the application into a single source of truth. We enforce strict CSS flexbox containment so that long assistant responses scroll smoothly without pushing the chat input off the screen or breaking the page boundary. We also route all Copilot portfolio queries through our shared services engine so that the assistant reports verified ledger totals, correct currency scaling, and active target allocations matching the Investments dashboard.

## Context

The personal finance copilot runs in a persistent Streamlit sidebar alongside the main dashboard. During lengthy conversational responses or when displaying multi step diagnostic traces, the sidebar chat container previously expanded beyond the viewport or suffered from broken flex scrolling, causing the user chat input to get pushed out of sight.

At the same time, portfolio analysis in `agent/tools.py` directly queried SQLite tables with independent SQL aggregations and custom heuristics. This created calculation drift between what the Copilot quoted to the user and what the Investments page rendered. In some instances, raw integer minor units (cents) were quoted without conversion to euros, or copy trade mirror holdings were omitted from allocation totals. Unifying all calculations under `services/portfolio.py` ensures that the assistant, the charts, and the tabular views share identical logic and numbers.

## Requirements

**User stories**:
- As a user, I want the Copilot chat container to scroll smoothly inside the sidebar so that lengthy explanations never push the prompt input off screen.
- As a user, I want the Copilot to report portfolio balances and percentage allocations that match my Investments page exactly so that I can trust the advice it gives.
- As a user, I want all financial figures in chat to be presented in standard euros rather than raw minor cent integers.

**Acceptance criteria**:
- **AC-1**: Viewport constrained sidebar layout. The sidebar flex container maintains a strict 100vh height limit with `overflow: hidden`, pinning the header at the top and chat input at the bottom while allowing only the chat history container to scroll vertically.
- **AC-2**: Smooth chat history scrolling. The chat history pane uses flex grow with auto scrolling (`overflow-y: auto`, `overscroll-behavior: contain`) and touch scrolling support, keeping streaming responses visible without breaking the layout.
- **AC-3**: Unified portfolio calculation engine. The Copilot tool `analyze_investments` imports and invokes `get_consolidated_holdings_df` and `calculate_drift` from `services/portfolio.py`, removing duplicate raw table aggregation queries.
- **AC-4**: Currency unit integrity. All financial metrics emitted by `analyze_investments` and related tools return balances scaled to standard float euros alongside human readable formatted strings, preventing minor unit confusion.
- **AC-5**: Detailed asset and allocation payload. `analyze_investments` provides consolidated asset class totals, individual holding positions, active profile target percentages, drift differences, and rebalancing alerts matching the Investments page.
- **AC-6**: Graceful empty state guidance. When no holdings or snapshot records exist, `analyze_investments` returns an explicit empty dataset flag with friendly instructions on how to import statement files or configure accounts.

## Options considered

### Option 1: Shared Service Engine and CSS Flexbox Pinning (Chosen)

Unify portfolio metrics by having `agent/tools.py` call the existing `services.portfolio` calculation methods (`get_consolidated_holdings_df` and `calculate_drift`). Reinforce sidebar CSS flexbox hierarchy to guarantee viewport pinning and independent chat scrolling.

**Pros**:
- Single source of truth across UI and AI assistant
- Leverages existing mirror resolution and currency conversion logic
- Clean CSS flexbox separation without relying on fragile JavaScript hacks

**Cons**:
- Requires holding calculation methods to be callable within read only database sessions

### Option 2: Custom Aggregation Queries in Copilot Tools

Keep custom SQL queries inside `agent/tools.py` and manually patch currency conversion and mirror lookups.

**Pros**:
- Isolates Copilot tool code from UI service modules

**Cons**:
- High maintenance overhead and risk of calculation drift between UI and Copilot
- Violates DRY (don't repeat yourself) principle

## Decision

**Chosen option**: Option 1: Shared Service Engine and CSS Flexbox Pinning.

We unify all portfolio and allocation calculations under `services/portfolio.py` and enforce strict flexbox viewport constraints in `ui/theme/common.css`.

## Rationale

Using `services/portfolio.py` as the canonical source ensures that changes to asset classification, FX conversions, and drift calculations instantly apply to both the visual dashboards and the conversational assistant. Constraining the sidebar viewport via CSS rules avoids race conditions during streaming reruns in Streamlit.

## Feature design

**Data model sketch**:

No new database tables are added. Existing SQLite views (`v_holdings`) and tables (`allocation_profiles`, `allocation_targets`, `account_snapshots`) remain the storage layer.

**API surface**:

| Function / Tool | Module | Inputs | Outputs | Description |
|---|---|---|---|---|
| `tool_analyze_investments` | `agent/tools.py` | none | `dict[str, Any]` | Returns unified portfolio metrics, holdings, and drift |
| `get_consolidated_holdings_df` | `services/portfolio.py` | `conn: sqlite3.Connection` | `pd.DataFrame` | Builds resolved holdings DataFrame with mirror trades |
| `calculate_drift` | `services/portfolio.py` | `current_values`, `targets`, `drift_band_pct` | `list[dict[str, Any]]` | Calculates bucket drift and rebalance alerts |

**Value sourcing**:

| Action | Value produced / displayed | Source |
|---|---|---|
| Query investments | Total portfolio value in EUR | Sum of `value_eur` from `services.portfolio.get_consolidated_holdings_df` |
| Query investments | Cash balance in EUR | `AccountRepository.get_total_cash_balance` scaled from minor units |
| Query investments | Allocation bucket values | Aggregated `value_eur` grouped by active profile's `dimension` (`asset_type`, `sector`, `region`) from consolidated holdings, plus cash if `include_cash = 1` |
| Query investments | Allocation drift percentages | `services.portfolio.calculate_drift` comparing bucket values to target percentages |
| Query investments | Active target profile name | `allocation_profiles.name` where `is_active = 1` |
| Chat view | Chat scroll position | Native browser scrolling inside `.st-key-copilot_chat_history` |

**Key invariants**:
- Copilot tools must never perform writes or schema alterations.
- All monetary outputs presented in LLM responses must be expressed in euros, never raw minor units.
- The chat input widget must remain visible and accessible at all times regardless of chat history length.

**Security model**:
- Database queries executed by Copilot tools must use `database.connect_readonly` to enforce read only authorizer protection.

**Critical test scenarios**:
- Happy path: User asks Copilot to analyze investments; assistant calls `analyze_investments` and quotes euro balances and drift matching the Investments page, verifies **AC-3**, **AC-4**, **AC-5**.
- Viewport scrolling: Multiple long responses stream into chat history; the history container scrolls smoothly and the input box stays pinned to the bottom, verifies **AC-1**, **AC-2**.
- Empty state: Copilot runs on a database with no imported statements; tool returns structured guidance and empty dataset flag, verifies **AC-6**.

## Build plan

1. Standardize and harden sidebar flex container rules in `ui/theme/common.css` so chat history scrolls cleanly without pushing chat input off screen on both desktop and mobile drawer viewports, satisfies **AC-1**, **AC-2**
2. Refactor `tool_analyze_investments` in `agent/tools.py` to use `services.portfolio.get_consolidated_holdings_df`, respect active profile dimension mapping, and compute drift via `calculate_drift`, satisfies **AC-3**, **AC-5**
3. Add robust euro currency formatting and empty dataset handling in `tool_analyze_investments`, satisfies **AC-4**, **AC-6**
4. Add unit and integration tests verifying portfolio calculations and Copilot tool payload consistency, satisfies **AC-3**, **AC-4**, **AC-5**

## Consequences

**Positive**:
- Consistent financial numbers across all app pages and Copilot turns.
- Smooth chat scrolling experience during long generations.
- Reusable portfolio calculation pipeline.

**Negative / tradeoffs**:
- Generating consolidated holdings dataframe on the fly adds a minor runtime cost during tool execution.

## Migration plan

**Strategy**: no migration needed.
Changes are purely structural in CSS, service integration, and tool output schema.
