# Scope: Personal Finance Assistant UX Overhaul

Streamlined visual layout, bug fixes, and decluttering pass for the personal finance dashboard.

**Build approach:** Tracer Bullet (vertical slices through each core area end to end).
**Workflow:** Beta (after develop, check verify then test). The project default level of rigor. /architect is the recommended first stop for a feature with a real decision, but skippable when you already know the build. Any feature can carry its own tag to do more or less.

_These are recommendations to keep your build orderly, not requirements. Skip anything that does not fit: if you already know how to build a feature, use /develop and skip /architect. You decide when a feature is done._

## At a glance

| # | Feature | Phase | Status |
|---|---------|-------|--------|
| A | Data Persistence & Repositories | Context | existing |
| B | Secrets Vault & Keyring | Context | existing |
| C | Banking Connectors & Statement Parsers | Context | existing |
| D | Italian Tax & Mortgage Engines | Context | existing |
| E | Local Copilot Core | Context | in-progress |
| 1 | UI Theme & Layout Token Foundation | Foundation | done |
| 2 | Dashboard Overhaul & Rerun Fixes | Slice 1 | done |
| 3 | Spending & Budgeting Streamline | Slice 2 | done |
| 4 | Investments & Holdings Simplification | Slice 3 | done |
| 5 | Copilot Calming & Tool Hardening | Slice 4 | done |
| 6 | Dutch Financial Law Vector Vault | Slice 5 | done |
| 7 | Navigation Elevation & Compact Layout Foundation | Slice 6 | done |
| 8 | Dashboard Hardening & Exposure Visuals | Slice 7 | done |
| 9 | Copilot Layout Scroll & Calculation Single Source of Truth | Slice 8 | done |
| 10 | Spending Flow & Historical Burn Trajectory | Slice 9 | done |
| 11 | Transactions Select Action Workflow | Slice 10 | done |
| 12 | Investment Exposure Dimensions, TradingView Panel & Realized P&L | Slice 11 | done |
| 13 | Multi Bank Manual Accounts & Hybrid Statement Ingestion | Slice 12 | done |
| 14 | System Cleanup, Architecture Hardening & Regression Suite | Slice 13 | in-progress |
| 15 | UI Polish, Allocation Strategy Management & Copilot Hardening | Slice 14 | in-progress |

## Brownfield context

### A. Data Persistence & Repositories · existing
SQLite schema migrations and typed dataclass repositories for accounts, transactions, and holdings. code in `db/`

### B. Secrets Vault & Keyring · existing
Local credential encryption backed by Windows Credential Manager. code in `services/secrets_vault.py`

### C. Banking Connectors & Statement Parsers · existing
Open banking API integration and PDF or CSV bank statement parsers. code in `connectors/` and `services/file_import_service.py`

### D. Italian Tax & Mortgage Engines · existing
Capital gains calculators for Italian tax filings and mortgage amortization schedules. code in `services/fiscal_service.py` and `services/mortgage_service.py`

### E. Local Copilot Core · in-progress
Local Ollama assistant with read only SQL authorizer and database inspection tools. code in `agent/` and `ui/copilot_sidebar.py`

## Foundations

### 1. UI Theme & Layout Token Foundation · done
Standardize design tokens, typography, card spacing, and responsive layout primitives in CSS to eliminate misaligned elements across pages.
**Done when:** shared styles in `ui/theme/` provide clean card wrappers and spacing variables, and custom styling applies without misaligned elements.
spec docs/specs/0002-ui-theme-layout-token-foundation/index.md · code in ui/theme/
- [x] Design it (spec): `/architect ui theme & layout token foundation`
- [x] Build it: /develop ui theme & layout token foundation
  - [x] Standardize design tokens in Python and CSS
  - [x] Implement card container & layout wrapper styles
  - [x] Align Plotly charts to semantic color palette
  - [x] Add theme and token unit test coverage

## Slice 1: Dashboard Overhaul & Rerun Fixes

### 2. Dashboard Overhaul & Rerun Fixes · done
Redesign the primary dashboard with minimalist KPI cards and clean charts while fixing Streamlit rerun flickers and widget key collisions.
**Done when:** net worth and cash flow cards render with clear typography and whitespace, and page interactions trigger zero erratic reruns or key warnings.
spec [0003](../specs/0003-dashboard-overhaul-rerun-fixes/index.md) · code in ui/pages/dashboard.py
- [x] Design it (spec): `/architect dashboard overhaul & rerun fixes`
- [x] Build it: /develop dashboard overhaul & rerun fixes
  - [x] Modular Streamlit fragments for ticker, accounts, analytics, and news (satisfies AC-2, AC-3)
  - [x] 4-KPI ribbon for Net Worth, Liquid Cash, Investments, and Cash Flow (satisfies AC-1)
  - [x] Tokenized accounts grid with namespaced keys and popover adjustment forms (satisfies AC-4, AC-5)
  - [x] Analytics category donut chart and cash flow comparison (satisfies AC-2)
  - [x] Empty state handling and comprehensive unit tests (satisfies AC-6)
- [x] Verify it: /check verify dashboard overhaul & rerun fixes
- [x] Test it: /test dashboard overhaul & rerun fixes

## Slice 2: Spending & Budgeting Streamline

### 3. Spending & Budgeting Streamline · done
Clean up expense category breakdowns, move dense manual forms into dialog modals, and fix calculation inaccuracies in transaction sums.
**Done when:** expense views present simplified spending metrics, manual entry forms open cleanly in popups, and ledger sums calculate accurately.
spec [0004](../specs/0004-spending-budgeting-streamline/index.md) · code in ui/pages/spending.py
- [x] Design it (spec): `/architect spending & budgeting streamline`
- [x] Build it: /develop spending & budgeting streamline
  - [x] Fix ledger sums and branch budget variance rollup calculations (satisfies AC-1, AC-2, AC-3, AC-7)
  - [x] Implement modal dialogs for category budgets and mortgage assignment (satisfies AC-4, AC-5)
  - [x] Streamline spending layout with action triggers, fragments, and collapsible Sankey (satisfies AC-4, AC-5, AC-6)
  - [x] Add unit test suite for calculation accuracy, rollup logic, and dialog interactions (satisfies AC-1, AC-2, AC-3, AC-7)
- [x] Verify it: /check verify spending & budgeting streamline
- [x] Test it: /test spending & budgeting streamline

## Slice 3: Investments & Holdings Simplification

### 4. Investments & Holdings Simplification · done
Organize portfolio holdings into a clean hierarchy, tame noisy visual drilldowns, and resolve statement import desync glitches.
**Done when:** holdings display clear performance numbers without visual clutter, and statement imports update portfolio records without desync.
spec [0006](../specs/0006-investments-holdings-simplification/index.md) · code in ui/pages/investments.py
- [x] Design it (spec): `/architect investments & holdings simplification`
- [x] Build it: /develop investments & holdings simplification
  - [x] Add holdings position status migration and v_holdings view filter (satisfies AC-5)
  - [x] Implement atomic statement reconciliation repository method (satisfies AC-5, AC-6)
  - [x] Rebuild portfolio tab with clean allocation donut and exposure bar (satisfies AC-2, AC-3, AC-4, AC-7)
  - [x] Distribute rebalancing, income, and goals into isolated tabs (satisfies AC-1)
  - [x] Add automated unit tests for lifecycle, reconciliation, and fallbacks (satisfies AC-1, AC-2, AC-5, AC-6, AC-7)
- [x] Verify it: /check verify investments & holdings simplification
- [x] Test it: /test investments & holdings simplification

## Slice 4: Copilot Calming & Tool Hardening

### 5. Copilot Calming & Tool Hardening · done
Tame the copilot sidebar into an on demand assistant without unprompted background runs, and make query tool errors recover gracefully.
**Done when:** copilot runs only on user request, background automation stays quiet, and failed tool queries display friendly troubleshooting notices.
spec [0007](../specs/0007-copilot-calming-tool-hardening/index.md) · code in agent/ and ui/copilot_sidebar.py
- [x] Design it (spec): `/architect copilot calming & tool hardening`
- [x] Build it: /develop copilot calming & tool hardening
  - [x] Implement read only SQLite connection with engine authorizer (satisfies AC-3)
  - [x] Upfront Ollama health check and transparent quick action logging (satisfies AC-2, AC-6)
  - [x] Structured tool exception recovery and informative empty dataset guidance (satisfies AC-4, AC-5, AC-7)
  - [x] Isolate background sync to ensure quiet on demand copilot operation (satisfies AC-1)
  - [x] Add comprehensive automated test suite for authorizer, error recovery, and calming (satisfies AC-1, AC-2, AC-3, AC-4, AC-5, AC-6, AC-7)
- [x] Verify it: /check verify copilot calming & tool hardening
- [x] Test it: /test copilot calming & tool hardening

## Slice 5: Dutch Financial Law Vector Vault

### 6. Dutch Financial Law Vector Vault · done
Upgrade the financial law knowledge vault into a local SQLite vector database with hybrid search, dual embeddings, and statutory article citations.
**Done when:** legal vault returns hybrid vector and keyword search results in single-digit milliseconds, copilot tools surface verified Dutch legal articles, and chat responses include expandable citation cards.
spec [0005](../specs/0005-dutch-financial-law-vector-vault/index.md) · code in services/legal_vault_service.py
- [x] Design it (spec): `/architect dutch financial law vector vault`
- [x] Build it: /develop dutch financial law vector vault
  - [x] Add sqlite-vec and fastembed dependencies with database schema migrations (satisfies AC-1, AC-2)
  - [x] Dual embedding provider with Ollama and FastEmbed 384-dim CPU fallback (satisfies AC-3, AC-7)
  - [x] Ingest curated Dutch financial legal corpus across six life domains (satisfies AC-1)
  - [x] Hybrid search with Reciprocal Rank Fusion and copilot tool integration (satisfies AC-4, AC-5)
  - [x] Interactive law explorer UI and copilot citation chip components (satisfies AC-6)
- [x] Verify it: /check verify dutch financial law vector vault
- [x] Test it: /test dutch financial law vector vault

## Slice 6: Navigation Elevation & Compact Layout Foundation

### 7. Navigation Elevation & Compact Layout Foundation · done
Eliminate excess top whitespace above the title, enlarge tab icons and labels with sticky highlighting, anchor the hide toggle to the right, position the ticker snugly below tabs with distinct assets, and pack page controls side by side.
**Done when:** sidebar title hugs the top with no dead whitespace, tab bar shows enlarged flowing thematic icons with active page highlighting and a right anchored hide values toggle, ticker displays distinct assets below the tabs, and compact side by side controls increase usable height across all screens.
spec [0008](../specs/0008-navigation-elevation-compact-layout/index.md)
- [x] Design it (spec): `/architect navigation elevation & compact layout foundation`
- [x] Build it: /develop navigation elevation & compact layout foundation
  - [x] Native top navigation with Material icons and active pill styling (satisfies AC-4, AC-5, AC-6)
  - [x] Sidebar brand row with privacy toggle and non collapsible sidebar (satisfies AC-1, AC-2, AC-3)
  - [x] Ticker exchange mapping, dedupe, and flush placement (satisfies AC-7, AC-8)
  - [x] Global density pass and per page compact control rows (satisfies AC-9)
  - [x] Ticker unit tests and all pages AppTest smoke (satisfies AC-2, AC-8, AC-10)
  code in `app.py`, `ui/theme/common.css`, `ui/components.py`, `ui/copilot_sidebar.py`, `ui/pages/`
- [x] Verify it: /check verify navigation elevation & compact layout foundation
- [x] Test it: /test navigation elevation & compact layout foundation

## Slice 7: Dashboard Hardening & Exposure Visuals

### 8. Dashboard Hardening & Exposure Visuals · done
Fix SQLite cross thread exceptions in dialogs, replace the fragile interactive flow Sankey with standard fullscreen inside an Expenses panel, style Marketcarpet with rounded corners and translucent glassmorphic tiles inside a Portfolio exposure panel, and accent account panels in alphabetical order.
**Done when:** category budget dialog opens without thread crashes, Expenses panel hosts the Sankey with clean native fullscreen, Portfolio exposure panel renders Marketcarpet with rounded glassmorphic tiles, and bank plus investment accounts show accent styling ordered alphabetically.
spec [0010](../specs/0010-dashboard-hardening-exposure-visuals/index.md) · code in ui/pages/dashboard.py, ui/charts.py, ui/dialogs.py
- [x] Design it (spec): `/architect dashboard hardening & exposure visuals`
- [x] Build it: /develop dashboard hardening & exposure visuals
  - [x] Add check_same_thread=False and isolate modal dialog connection lifecycles (satisfies AC-1, AC-2)
  - [x] Centralize pure Plotly Sankey with fullscreen expand modal and retire iframe component (satisfies AC-3, AC-4)
  - [x] Style Market Carpet treemap with rounded glassmorphic tiles and RGBA palette (satisfies AC-5)
  - [x] Group and sort accounts alphabetically by asset class with semantic accents (satisfies AC-6)
  - [x] Unit tests for multi thread safety, shared Sankey, and account sorting (satisfies AC-1, AC-2, AC-3, AC-5, AC-6)
- [x] Verify it: /check verify dashboard hardening & exposure visuals
- [x] Test it: /test dashboard hardening & exposure visuals

## Slice 8: Copilot Layout Scroll & Calculation Single Source of Truth

### 9. Copilot Layout Scroll & Calculation Single Source of Truth · done
Constrain copilot chat flex containers to restore smooth vertical scrolling for lengthy responses, and unify portfolio calculations into a single source of truth so the assistant quotes verified ledger balances and percentages instead of unscaled cents or hallucinated metrics.
**Done when:** copilot chat pane stays within the sidebar boundary and scrolls smoothly during long answers, and portfolio allocation queries report true holdings, euro totals, and target percentages matching the ledger.
spec [0009](../specs/0009-copilot-layout-scroll-calculation-single-source-of-truth/index.md)
- [x] Design it (spec): `/architect copilot layout scroll & calculation single source of truth`
- [x] Build it: /develop copilot layout scroll & calculation single source of truth
  - [x] Enforce sidebar flexbox boundaries and independent chat scrolling (satisfies AC-1, AC-2)
  - [x] Integrate consolidated holdings engine and profile drift into analyze_investments (satisfies AC-3, AC-5)
  - [x] Add currency scaling integrity and empty state guidance (satisfies AC-4, AC-6)
  - [x] Regression suite for portfolio calculations and Copilot tool output (satisfies AC-3, AC-4, AC-5)
code in agent/tools.py, ui/theme/common.css
- [x] Verify it: /check verify copilot layout scroll & calculation single source of truth
- [x] Test it: /test copilot layout scroll & calculation single source of truth

## Slice 9: Spending Flow & Historical Burn Trajectory

### 10. Spending Flow & Historical Burn Trajectory · done
Declutter spending controls by removing redundant filter and transfer buttons, nest fiscal cycle dates into a scope tooltip, and compute burn and budget trajectories from the past three months of real ledger entries.
**Done when:** spending header displays view scope with fiscal cycle tooltip, redundant filter buttons are removed, and the trajectory chart projects spending based on the actual burn rate of the past three months.
spec [0011](../specs/0011-spending-burn-trajectory-transactions-workflow/index.md)
- [x] Design it (spec): `/architect spending flow & historical burn trajectory`
- [x] Build it: /develop spending flow & historical burn trajectory
  - [x] Calculate 3-month historical burn rate in budget service (satisfies AC-2)
  - [x] Compact spending toolbar with fiscal cycle tooltip (satisfies AC-1)
  - [x] 12-month trajectory chart with 3-month burn and runway KPI badge (satisfies AC-3)
  code in `services/budget_service.py` and `ui/pages/spending.py`
- [x] Verify it: /check verify spending flow & historical burn trajectory
- [x] Test it: /test spending flow & historical burn trajectory

## Slice 10: Transactions Select Action Workflow

### 11. Transactions Select Action Workflow · done
Modernize transaction management by replacing inline transfer checkbox columns with standard row selection checkboxes on the left, paired with a bottom action bar to mark selected items as internal transfers alongside deletion.
**Done when:** transaction table removes inline transfer checkboxes, left row selection checkboxes drive bulk actions, and a bottom action button marks selected rows as internal transfers.
spec [0011](../specs/0011-spending-burn-trajectory-transactions-workflow/index.md)
- [x] Design it (spec): `/architect transactions select action workflow`
- [x] Build it: /develop transactions select action workflow
  - [x] Atomic transaction batch helpers in database layer (satisfies AC-5, AC-6, AC-7)
  - [x] Row selection checkboxes with Select All and Clear All helpers (satisfies AC-4)
  - [x] Bottom action bar with transfer toggle, bulk categorize, and delete dialog (satisfies AC-5, AC-6)
  code in `db/database.py`, `ui/pages/transactions.py`, and `ui/dialogs.py`
- [x] Verify it: /check verify transactions select action workflow
- [x] Test it: /test transactions select action workflow

## Slice 11: Investment Exposure Dimensions, TradingView Panel & Realized P&L

### 12. Investment Exposure Dimensions, TradingView Panel & Realized P&L · done
Expand portfolio allocation beyond asset classes to sector, theme, region, currency, and commodity dimensions, embed a minimizable scrollable live TradingView watchlist of distinct holdings, report realized profit and loss from closed positions, and move market news to the page bottom.
**Done when:** portfolio exposure charts display sector, theme, region, and currency breakdowns, a minimizable scrollable TradingView widget tracks distinct assets, realized profit and loss displays in its own panel, and market news rests at the bottom of the investments page.
spec [0012](../specs/0012-investment-exposure-dimensions-tradingview-realized-pnl/index.md) · code in ui/pages/investments.py, db/migrations/, db/repositories/
- [x] Design it (spec): `/architect investment exposure dimensions tradingview panel & realized p&l`
- [x] Build it: /develop investment exposure dimensions tradingview panel & realized p&l
  - [x] Database migration and repository queries for closed positions realized P&L (satisfies AC-4, AC-5)
  - [x] Multi dimension exposure aggregation and interactive pill switcher (satisfies AC-1, AC-2)
  - [x] Compact minimizable TradingView live watchlist container (satisfies AC-3)
  - [x] Dedicated Realized P&L panel and closed positions table (satisfies AC-6)
  - [x] Relocate cached market news fragment to investments page bottom (satisfies AC-7)
  - [x] Automated unit test suite for exposure, realized P&L, and masking (satisfies AC-1, AC-2, AC-4, AC-5, AC-6)
- [x] Verify it: /check verify investment exposure dimensions tradingview panel & realized p&l
- [x] Test it: /test investment exposure dimensions tradingview panel & realized p&l

## Slice 12: Multi Bank Manual Accounts & Hybrid Statement Ingestion

### 13. Multi Bank Manual Accounts & Hybrid Statement Ingestion · done
Support manual bank account creation and balance tracking, paired with a hybrid ingestion pipeline combining deterministic table extraction and local Ollama fallback for diverse statements including Turkish and English Türkiye İş Bankası files.
**Done when:** users can manually add bank accounts and track balances, and statement imports parse diverse PDF and CSV files (including Turkish and English İş Bankası statements) via deterministic parsers or local Ollama fallback.
spec [0013](../specs/0013-multi-bank-manual-accounts-hybrid-statement-ingestion/index.md) · code in ui/dialogs.py, connectors/file_import/, ui/pages/import_files.py
- [x] Design it (spec): `/architect multi bank manual accounts & hybrid statement ingestion`
- [x] Build it: /develop multi bank manual accounts & hybrid statement ingestion
  - [x] Implement manual account creation database helpers (satisfies AC-2)
  - [x] Build reusable manual account dialog in Settings and Import Files (satisfies AC-1, AC-2)
  - [x] Deterministic Türkiye İş Bankası PDF extractor supporting Turkish and English headers (satisfies AC-3)
  - [x] Ingestion dispatch with local Ollama fallback for unrecognized formats (satisfies AC-4)
  - [x] Account auto matching selectbox and ending balance confirmation in Import Files (satisfies AC-5, AC-7)
  - [x] Native currency support and unit test suite for accounts and PDF ingestion (satisfies AC-1, AC-2, AC-3, AC-5, AC-6)
- [x] Verify it: /check verify multi bank manual accounts & hybrid statement ingestion
- [x] Test it: /test multi bank manual accounts & hybrid statement ingestion

## Slice 13: System Cleanup, Architecture Hardening & Regression Suite

### 14. System Cleanup, Architecture Hardening & Regression Suite · in-progress
Perform a comprehensive cleanup pass to remove dead code and orphan routines, harden single source of truth financial services, ensure error free navigation across all pages, and verify end to end test suite stability.
**Done when:** dead code is pruned, financial calculations share a unified tested core, all pages render without warnings, and automated test suite passes completely.
spec [0014](../specs/0014-system-cleanup-architecture-hardening/index.md)
- [x] Design it (spec): `/architect system cleanup architecture hardening & regression suite`
- [ ] Build it: /develop system cleanup architecture hardening & regression suite
  - [x] Money type, logging, typed session state and demo mode seams (satisfies AC-1, AC-2, AC-4, AC-5, AC-7, AC-8)
  - [x] Dashboard tracer migrated end to end on demo data (satisfies AC-1, AC-4, AC-5, AC-10)
  - [x] Split agent/tools.py, ui/charts.py and investments page into packages (satisfies AC-3, AC-6)
  - [x] Migrate remaining pages and services, remove float money path (satisfies AC-1, AC-2, AC-4, AC-5)
  - [x] Visual consistency pass and README showcase (satisfies AC-9, AC-10, AC-11)
- [ ] Verify it: /check verify system cleanup architecture hardening & regression suite
- [ ] Test it: /test system cleanup architecture hardening & regression suite

## Slice 14: UI Polish, Allocation Strategy Management & Copilot Hardening

### 15. UI Polish, Allocation Strategy Management & Copilot Hardening · in-progress
Fix the layout and table defects found while clicking through the live app (dashboard top gap and panel order, KPI cards that change height, the half width Top Merchants table, the per lot holdings table, the duplicate quotes table, a blur over public market data), and give allocation strategies real create and delete paths in the UI and through the Copilot, with the tool surface and latency tuned from a measured evaluation.
**Done when:** the dashboard opens flush under the navigation with the charts above the account cards, KPI rows keep one height with Hide values on, Spending panels line up with a full width merchant table, Investments shows distinct assets with the Status column and duplicate table gone, and an allocation strategy can be created and deleted from the UI and by asking the Copilot, with a confirmation before a delete.
spec [0016](../specs/0016-ui-polish-allocation-strategy-copilot/index.md) · code in ui/theme/common.css, ui/pages/dashboard.py, ui/pages/spending.py, services/analytics.py, services/portfolio.py, services/allocation_service.py, ui/allocation_ui.py, ui/pages/investments/, ui/pages/settings.py, ui/copilot_sidebar.py, agent/tools/
- [x] Design it (spec): `/architect ui polish, allocation strategy management & copilot hardening`
- [x] Build it: /develop ui polish, allocation strategy management & copilot hardening
  - [x] Dashboard layout and panel height parity (satisfies AC-1, AC-2, AC-3)
  - [x] Spending merchant panel and investment table aggregation (satisfies AC-4, AC-5, AC-6, AC-7, AC-8, AC-9, AC-10)
  - [x] Allocation strategy create and delete, service layer plus both UI surfaces (satisfies AC-11, AC-12, AC-13)
  - [x] Copilot tools, correctness fixes, latency tuning and timing footer (satisfies AC-12, AC-14, AC-15, AC-16, AC-17)
  - [x] CSS and masking cleanup with regression tests (satisfies AC-18, AC-19)
- [ ] Verify it: /check verify ui polish, allocation strategy management & copilot hardening
- [ ] Test it: /test ui polish, allocation strategy management & copilot hardening

## Deferred
Out of scope for the current build pass, kept so the plan stays honest.
- **Deep tax schedule breakdown**: expanded regional Italian tax regimes · needs a decision
- **Mortgage payoff scenario modeling**: advanced refinancing and early payoff comparisons · needs a decision
- **Multi currency auto rebalancing**: portfolio currency conversion rebalance rules · needs a decision
- **Copilot phrasing robustness**: a wording test set for allocation requests, and a larger default tool calling model or two stage routing if a first turn stays above roughly 30 seconds · from spec 0016
- **Streamlit upgrade review**: re-verify the generated selectors behind the dashboard top gap and the options menu after a framework major version · from spec 0016

## Legend

**The decision box.** Every feature carries exactly one, the sub task whose label ends with `(spec)`. Skills locate it by that `(spec)` suffix, never by an exact label. Every other box is an execution box and `/architect` never ticks one.

**Feature lifecycle**: the scope updates as a feature moves; each row is what it shows and who sets it:

| State | Set by | The feature shows |
|---|---|---|
| `planned` · needs a decision | `/scope` | one box: `Design it (spec): /architect <feature>` |
| `in-progress` (designed) | `/architect` at spec capture | `Design it` ticked; spec linked; `Build it: /develop <feature>` + 2 to 5 milestones; the tier closing boxes (`Verify it` Alpha+, `Test it` Beta+, `Review it` + `Document it` GA); any surfaced follow up enrolled |
| `in-progress` (building) | `/develop` | milestone sub boxes tick one by one; code pointer filled |
| `in-progress` (verified) | `/check verify` | `Build it` + milestones ticked; `Verify it` ticked |
| `done` | you, when you decide it is; `/sync` reconciles | boxes you ran ticked, skipped ones marked skipped; the tier last stage (`Prototype` after `/develop`; `Alpha` after `/check verify`; `Beta`/`GA` after `/test`) is the suggested point to call it done; `/sync` captures conventions |

- **Next step** = the first unticked box (always a command or a tracked milestone).
- **needs a decision** = run `/architect` first; otherwise straight to `/develop`. The tag drops once the spec is captured.
- **Atomic build tasks live in the spec Build plan, not here**: the scope carries only the milestone rollup.
- **Status** `planned` → `in-progress` → `done`, plus `existing` (pre workflow) and `dropped` (de scoped, kept for history).
- **Approach tag** beside a heading overrides the project default for that feature; no tag inherits it.
- **Workflow tier tag** beside a heading sets that one feature rigor above or below the project default; no tag inherits the default. It decides the feature check boxes and each skill next suggestion.
- **Workflow** (header line) is the project default, what runs after `/develop`: **Beta** runs `/check verify` then `/test`.
- **Pointer line** (`spec <n> · code in <path>`): the spec link added by `/architect`, the code path by `/develop`.
