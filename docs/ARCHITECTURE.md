# System Architecture & Technical Specifications

**Personal Finance Assistant (PFA)** is an enterprise grade, local first personal financial operating system built for privacy conscious European investors and homeowners. It runs entirely on the user's local machine with zero cloud telemetry, zero remote data custody, and native hardware optimization.

---

## 🏛️ High-Level Architectural Topology

```
┌──────────────────────────────────────────────────────────────────────────────────────────┐
│                                    PRESENTATION TIER                                     │
│  Streamlit Desktop  •  Custom CSS Token Engine  •  Dynamic Plotly  •  TradingView Engine │
│                     Global Screen-Shield Privacy Mode Masking (****)                     │
└────────────────────────────┬─────────────────────────────────┬───────────────────────────┘
                             │                                 │
                   Synchronous UI Actions             Asynchronous CopilotTask
                             │                        (@st.fragment Threading)
                             ▼                                 ▼
┌───────────────────────────────────────────────┐   ┌──────────────────────────────────────┐
│             DOMAIN SERVICES CORE              │   │           AI AGENT ENGINE            │
│ • services/portfolio.py (5/25 Drift & Multi-D)│◀──│ • Ollama (Local Qwen 2.5 7B)         │
│ • services/budget_service.py (3-Mo Burn Rate) │   │ • 25 Deterministic Tool Handlers     │
│ • services/tax_optimizer.py (Box 1, 3 & RAG)  │   │ • Strict C-Level SQLite Authorizer   │
│ • services/mortgage.py (30-Yr Amortization)   │   │ • Plotly Interactive Chart Generator │
│ • services/analytics.py (Liquidity & Runway)  │   │ • Legal Vector Vault (RRF Hybrid)    │
└───────────────────────┬───────────────────────┘   └──────────────────┬───────────────────┘
                        │                                              │
                        │             ┌────────────────────────────────┘
                        ▼             ▼
┌──────────────────────────────────────────────────────────────────────────────────────────┐
│                                 PERSISTENCE & SECURITY                                   │
│  • SQLite3 Engine in WAL Mode (data/finance.db)  •  Enforced Foreign Keys                │
│  • Minor-Unit Integer Ledgers (cents / kuruş)   •  sqlite-vec + FastEmbed Dense Vectors  │
│  • Symmetric Fernet Cryptography Vault          •  Windows Credential Manager (Keyring)  │
└──────────────────────────────────────────────────────────────────────────────────────────┘
                        ▲
                        │ Ingestion Pipeline
┌───────────────────────┴──────────────────────────────────────────────────────────────────┐
│                                   INGESTION RAILS                                        │
│  • Enable Banking PSD2 AISP (RSA-2048 / RS256 JWT)                                       │
│  • Direct eToro Broker API with Local Mirroring & Realized P&L                           │
│  • Native Deterministic Parsers: CAMT.053 XML, MT940, ABN AMRO (.TAB), Revolut CSV,      │
│    Trade Republic (PDF/CSV), Türkiye İş Bankası PDF (Bilingual TR/EN)                    │
│  • Autonomous Local LLM Zero-Shot Fallback Schema Extractor                              │
└──────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 🔒 1. Security & Zero-Trust Privacy Sandbox

### Zero Cloud Custody
All sensitive financial entities—including transaction ledgers, bank balances, asset holdings, mortgage obligations, and risk profiles—reside strictly on disk in `data/finance.db`. The application transmits zero telemetry, zero metrics, and zero analytical logs over the wire.

### Secrets Vault & OS-Level Credential Management
External authentication credentials (Enable Banking client certificates, eToro API access keys, and user configuration secrets) are protected using symmetric Fernet encryption in `data/vault.bin`. 
- The master decryption key is managed securely via the operating system's native secret storage: the **Windows Credential Manager** (`keyring` library).
- Credentials are decrypted strictly in memory at invocation time and never written to logs, terminal output, or version controlled `.env` files.

### C-Level SQLite Authorizer for AI Execution
To grant the local AI Copilot SQL inspection capabilities without risking database corruption or data loss, database connections passed to the Copilot are initialized via `db.database.connect_readonly()`.
- An authorizer callback hooked into the SQLite engine's C API intercepts all SQL statements prior to evaluation.
- Permitted operations: `SQLITE_SELECT`, `SQLITE_READ`, and column inspection functions.
- Prohibited operations: `SQLITE_INSERT`, `SQLITE_UPDATE`, `SQLITE_DELETE`, `SQLITE_PRAGMA`, `SQLITE_ATTACH`, `SQLITE_DETACH`, and schema alteration calls (`DROP`, `ALTER`, `CREATE`). Any violating query is halted at the database engine level before execution begins.

### Global Screen-Shield Privacy Mode
A single click toggle in the sidebar (`st.session_state["hide_amounts"]`) applies instant client side privacy masking across every page:
- Formats every financial balance, transaction amount, portfolio metric, and chart label with `****`.
- Allows safe demonstrations, public screen sharing, and streaming without leaking net worth or account figures.

---

## ⚡ 2. Domain Services & Quant Math Core

Business logic and financial mathematics are strictly isolated in `services/`, decoupled from Streamlit rendering loops:

### Portfolio Valuation & 5/25 Rebalancing (`services/portfolio.py`)
- **Single Source of Truth**: Consolidates holdings across all active brokerage accounts, cash balances, and manual assets into a unified calculation engine.
- **Multi-Dimensional Exposures**: Aggregates exposure distributions across five orthogonal dimensions: Asset Class, Sector, Region, Currency, and Theme.
- **Swensen / Boglehead 5/25 Rebalance Rule**: Computes absolute allocation drift against target profiles. Identifies assets exceeding either 5% absolute drift or 25% relative drift.
- **Execution Models**:
  - *Full Rebalance*: Bidirectional buy and sell orders.
  - *Buy-Only Optimization*: Allocates new incoming cash injection exclusively to underweight assets, avoiding taxable capital gains sales.
  - *Target Cash Injection*: Calculates the minimum new capital needed to bring the entire portfolio into target balance without selling.
- **Realized P&L Tracking**: Tracks closed positions, cost basis, realized proceeds, and total profit/loss (`db/repositories/holding_repository.py`).

### Spending & Historical Burn Trajectory (`services/budget_service.py`)
- Computes trailing 3-month actual burn rate from ledger entries, insulating runway forecasting from single-month seasonal outliers.
- Projects 12-month forward burn trajectories paired with emergency runway KPI badges.
- Automatically calculates monthly budget variance rollups and flags category overspending.

### Dutch Belastingdienst Tax Intelligence (`services/tax_optimizer.py`)
- **Box 1 Income Tax**: Evaluates progressive tax brackets, Dutch 30% expat ruling reductions, and Mortgage Interest Deduction (*Hypotheekrenteaftrek* / HRA).
- **Box 3 Wealth Tax**: Calculates deemed yield (*fictief rendement*) on reference date (*peildatum 1 januari*), applying single/fiscal partner exemptions (€57,000 / €114,000) and distinguishing bank deposits from other investments.
- **Pillar 3 Pension Room (*Jaarruimte*)**: Calculates deductible pension contributions and immediate Box 1 tax rebates (up to 49.5%) incorporating Factor A (*pensioenaangroei*) from Uniform Pensioenoverzicht (UPO) records.
- **Certified Groenfondsen Arbitrage**: Computes double tax alpha from green investments (Box 3 exemption up to €71,251 / €142,502 plus 0.1% Box 1 tax credit).

### Mortgage Amortization & Liabilities (`services/mortgage.py`)
- Simulates 30-year amortization curves for Annuity (*annuïteitenhypotheek*), Linear (*lineaire hypotheek*), and Interest-Only (*aflossingsvrij*) loans.
- Simulates penalty-free early voluntary repayments (*boetevrij aflossen*, up to 10–20%/year), calculating compound interest savings and term reduction.
- Calculates real-time Loan-to-Value (LTV) and accumulated net home equity.

---

## 🤖 3. AI Agent Engine & Legal Vector Vault

### Local Inference via Ollama
- Connects to locally hosted open weight LLMs (default: `qwen2.5:7b-instruct`).
- Employs upfront connectivity health checks (`agent/copilot.py`) and graceful degradation if the model daemon is offline.
- Features **25 native deterministic tools** mapped to underlying Python service calculations for math, tax calculations, and database queries.

### Dutch Financial Law Vector Vault (`services/legal_vault_service.py`)
- Persistent legal knowledge vault embedded in SQLite using `sqlite-vec` virtual tables and FastEmbed CPU embeddings (384-dimensional dense vectors).
- Curated statutory corpus covering Dutch income tax, Box 3 wealth tax, pension legislation, mortgage regulations, Groenfondsen, and gifting rules.
- **Reciprocal Rank Fusion (RRF)**: Combines dense vector cosine similarity with FTS5 BM25 keyword search, ranking statutory articles with verified legal citations directly in Copilot chat cards.

### Dynamic Interactive Plotly Generation (`agent/chart_renderer.py`)
- Translates conversational queries into structured visualization payloads.
- Directly renders interactive bar charts, burn trajectories, allocation donuts, and Sankey diagrams within Copilot response turns.

---

## 🧵 4. Decoupled Threading & Reactive Lifecycle

Streamlit's synchronous script execution model presents concurrency challenges when interacting with background tasks and local LLMs. PFA implements a decoupled threading architecture:

### Asynchronous Copilot Worker (`agent/copilot_task.py`)
- LLM response generation and tool execution run inside a detached `threading.Thread` wrapped with Streamlit's `add_script_run_ctx`.
- Background inference never stalls the main Streamlit thread.
- Background polling is isolated into a dedicated `@st.fragment` (`_render_chat_status()` in `ui/copilot_sidebar.py`). Rerun events triggered by polling remain scoped to the fragment and never cause top-level page flickers or widget state loss.

### Thread-Safe Database Connections
- Main database connections are configured with `check_same_thread=False` to accommodate modal dialog forms (`ui/dialogs.py`).
- Background worker threads instantiate their own clean SQLite connection context, preventing cross-thread lock contentions in WAL mode.

---

## 💾 5. Data Model & Persistence Architecture

The relational schema in `data/finance.db` enforces financial accuracy and auditability:

```
┌────────────────────┐         ┌────────────────────────┐
│      accounts      │1       *│      transactions      │
│────────────────────│─────────│────────────────────────│
│ id (PK)            │         │ id (PK)                │
│ name               │         │ account_id (FK)        │
│ institution        │         │ date                   │
│ asset_class        │         │ amount_minor (Integer) │
│ currency           │         │ currency               │
│ is_manual          │         │ category_id (FK)       │
│ is_active          │         │ is_transfer            │
└─────────┬──────────┘         │ dedupe_hash (Unique)   │
          │1                   └────────────────────────┘
          │
          │*
┌─────────┴──────────┐         ┌────────────────────────┐
│ account_snapshots  │         │        holdings        │
│────────────────────│         │────────────────────────│
│ id (PK)            │         │ id (PK)                │
│ account_id (FK)    │         │ account_id (FK)        │
│ timestamp          │         │ ticker, name           │
│ balance_minor (Int)│         │ asset_class, sector    │
│ currency           │         │ region, currency       │
└────────────────────┘         │ quantity, cost_basis   │
                               │ status ('active'/'closed')
                               │ realized_pnl_minor     │
                               └────────────────────────┘
```

- **Minor-Unit Integer Storage**: All monetary fields (`balance_minor`, `amount_minor`, `realized_pnl_minor`, `cost_basis_minor`) are stored in integer minor units (cents / kuruş) to prevent IEEE 754 floating point rounding drift. Conversion to decimals occurs solely at presentation boundaries.
- **WAL Mode & Foreign Keys**: SQLite Write-Ahead Logging (`PRAGMA journal_mode=WAL`) enables concurrent reads while background transactions commit. Foreign key integrity (`PRAGMA foreign_keys=ON`) is enforced on all connections.
- **Idempotent Versioned Migrations**: Startup schema runner executes incremental SQL scripts under `db/migrations/` (`0001_initial_schema.sql` through `0006_holdings_realized_pnl.sql`), recording completed migrations in `schema_migrations`.
