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
| 5 | Copilot Calming & Tool Hardening | Slice 4 | planned |
| 6 | Dutch Financial Law Vector Vault | Slice 5 | done |

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

### 5. Copilot Calming & Tool Hardening · needs a decision
Tame the copilot sidebar into an on demand assistant without unprompted background runs, and make query tool errors recover gracefully.
**Done when:** copilot runs only on user request, background automation stays quiet, and failed tool queries display friendly troubleshooting notices.
- [ ] Design it (spec): `/architect copilot calming & tool hardening`

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

## Deferred
Out of scope for the current build pass, kept so the plan stays honest.
- **Deep tax schedule breakdown**: expanded regional Italian tax regimes · needs a decision
- **Mortgage payoff scenario modeling**: advanced refinancing and early payoff comparisons · needs a decision
- **Multi currency auto rebalancing**: portfolio currency conversion rebalance rules · needs a decision

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
