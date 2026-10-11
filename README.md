# Personal Finance Assistant (PFA)

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/Python-3.12%2B-blue.svg)](https://www.python.org/)
[![Database: SQLite WAL](https://img.shields.io/badge/Database-SQLite%20(WAL)-green.svg)](https://www.sqlite.org/)
[![AI Engine: Ollama Local](https://img.shields.io/badge/AI%20Engine-Ollama%20(Qwen%202.5)-purple.svg)](https://ollama.com/)
[![Tests: 56 Passed](https://img.shields.io/badge/Tests-56%20Passed-brightgreen.svg)](tests/)
[![Platform: Windows 11](https://img.shields.io/badge/Platform-Windows%2011%20Optimized-0078D4.svg)](install.ps1)

> **Product Vision**: A high-trust, local-first personal financial operating system built for privacy-conscious European investors and homeowners. Consolidates multi-bank Open Banking feeds, neobroker portfolios, and Dutch mortgage/tax obligations into an interactive desktop interface with an autonomous, offline AI Copilot—**zero cloud custody, zero telemetry, and 100% data ownership.**

---

## 🧭 Executive Summary & Product Architecture

Mainstream personal finance aggregators (YNAB, Copilot Money, Monarch) mandate cloud storage of sensitive banking credentials, share telemetry, and charge monthly recurring subscriptions while offering limited localization for European regulatory and tax frameworks.

**Personal Finance Assistant** rethinks consumer FinTech around **zero-trust local-first execution**:

```
                               ┌─────────────────────────────────────────────────────────┐
                               │                    PRESENTATION LAYER                   │
                               │   Streamlit Desktop UI  •  Dynamic Plotly  •  TradingView │
                               │            Global Screen-Shield Privacy Mode (****)       │
                               └──────────────┬───────────────────────────┬──────────────┘
                                              │                           │
                                     Synchronous Renders         Asynchronous CopilotTask
                                              │                   (@st.fragment Threading)
                                              ▼                           ▼
┌─────────────────────────────────┐   ┌───────────────────────────┐   ┌──────────────────────────┐
│        INGESTION RAILS          │   │      DOMAIN SERVICES      │   │     AI AGENT ENGINE      │
│ • PSD2 Enable Banking (RSA/JWT) │──▶│ • Portfolio 5/25 Rebalance│◀──│ • Ollama (Qwen 2.5 7B)   │
│ • Direct eToro Broker API Sync  │   │ • 30-Yr Mortgage Engine   │   │ • 20 Deterministic Tools │
│ • Multi-format Parsers (MT940,  │   │ • Box 1 & 3 Tax Modeler   │   │ • Plotly Chart Generator │
│   CAMT.053, CSV, TSV, PDF)      │   │ • Budget Variance & Leaks │   │ • Dutch RAG Law Vault    │
│ • LLM Zero-Shot Fallback Parser │   │ • Dividend Yield Calendar │   │ • Read-Only SQL Authorizer│
└─────────────────────────────────┘   └─────────────┬─────────────┘   └──────────────────────────┘
                                                    │
                                                    ▼
                                      ┌───────────────────────────┐
                                      │     PERSISTENCE & SECRETS │
                                      │ • SQLite in WAL Mode      │
                                      │ • Symmetric Fernet Vault  │
                                      │ • Windows Credential Mgr  │
                                      └───────────────────────────┘
```

---

## 💡 Strategic Product Decisions & Trade-Offs

| Decision | Alternative Evaluated | Product & Engineering Rationale |
| :--- | :--- | :--- |
| **Local SQLite (WAL Mode)** | Cloud PostgreSQL / Supabase | **Zero Data Custody & Speed**. Eliminates cloud infrastructure costs, GDPR compliance liability, and vendor lock-in. WAL mode guarantees crash resilience and concurrency. |
| **Local LLM (Ollama) via Native Tools** | OpenAI / Anthropic API Calls | **Uncompromising Privacy**. Financial records are never sent over the wire. Deterministic Python engines handle calculation; the LLM handles semantic routing and commentary. |
| **Engine-Level SQL Authorizer** | Prompt-engineered SQL filtering | **Zero-Trust AI Guardrails**. Read-only access enforced directly at SQLite C-authorizer level. Any LLM-generated `INSERT`, `UPDATE`, `DELETE`, `DROP`, or `ATTACH` statement is denied at the database engine. |
| **Decoupled Background Threading** | Synchronous Streamlit runs | **Non-Blocking Copilot UX**. LLM turn execution runs in an isolated `CopilotTask` worker thread with `@st.fragment`. UI actions (e.g. toggling privacy mode) never cancel or crash the assistant. |
| **OS-Level Keyring Encryption** | Plaintext `.env` configs | **Enterprise Security Posture**. Banking certificates, API secrets, and tokens are encrypted symmetrically with Fernet; master key is stored in the Windows Credential Manager. |

---

## 🛠️ Core Functional Modules

### 1. 📊 Executive Wealth Dashboard (`ui/pages/dashboard.py`)
- **4-Metric Liquidity Ribbon**: Real-time tracking of Net Worth, Liquid Cash, Invested Capital, and Emergency Runway Buffer (months of coverage).
- **Consolidated Account Grid**: Live balances grouped across checking, high-yield savings, brokerage, and real estate assets.
- **Cash Drag & Obligation Monitor**: Forward-looking calendar highlighting upcoming fixed bills and scheduled liability payments.

### 2. 🌊 Spending Topology & Cash Flow Engine (`ui/pages/spending.py`)
- **Interactive Cash Flow Sankey**: Full flow topology tracing gross income through banking accounts directly into fixed vs. discretionary spend buckets.
- **Subscription Leak Detector**: Automatic frequency pattern analyzer detecting silent recurring charges and SaaS creep.
- **Category Drilldowns**: Monthly variance tracking against target budgets with merchant-level breakdowns.

### 3. 📈 Multi-Asset Portfolio Rebalancer (`ui/pages/investments.py`)
- **5/25 Rebalancing Monitor**: Tracks asset class drift against target allocations using the classic Swensen / Boglehead 5/25 threshold rule.
- **3 Execution Models**:
  - *Full Rebalance*: Calculates bidirectional buy/sell orders.
  - *Buy-Only Optimization*: Allocates new incoming capital solely to underweight assets to minimize taxable transactions.
  - *Target Cash Injection*: Computes exact capital injection needed to balance portfolios without selling.
- **Embedded TradingView Widgets**: Real-time client-side financial charts for active holdings without server API limits.
- **Dividend & Yield Forecaster**: Forward-looking 12-month dividend yield calendar across held equities and ETFs.
- **FIRE Trajectory Simulator**: Dynamic compound interest engine modeling Financial Independence, Retire Early timelines based on savings rate and safe withdrawal rates.

### 4. 🏠 Dutch Mortgage & Real Estate Modeler (`ui/pages/mortgage.py`)
- **30-Year Amortization Curves**: Interactive calculations for Annuity (*annuïteitenhypotheek*), Linear (*lineaire hypotheek*), and Interest-Only (*aflossingsvrij*) structures.
- **Penalty-Free Prepayment Simulator**: Models the exact interest-saving and term-reduction impact of voluntary repayments (*boetevrij aflossen*, up to 10–20%/year).
- **Home Equity Tracker**: Calculates real-time loan-to-value (LTV) ratios and net equity based on current market valuations.

### 5. 🇳🇱 Dutch Belastingdienst Tax Intelligence (`ui/pages/tax.py`)
- **Box 1 Calculation**: Employment income calculation with automatic **30% ruling** reduction and **Mortgage Interest Deduction (*Hypotheekrenteaftrek*)**.
- **Box 3 Wealth Tax Estimator**: Computes deemed yield (*fictief rendement*) on reference date (*peildatum 1 januari*), accounting for single/fiscal partner exemptions (€57,000 / €114,000) and *Groenfondsen* green investment exclusions.
- **AI Capital Allocation & Tax Optimizer**: 4-way simulation comparing Extra Mortgage Prepayment vs. Pillar 3 Pension (Jaarruimte) vs. Certified Groenfondsen vs. Taxable ETF with multi-year Plotly trajectories.
- **Pillar 3 Pension Room (*Jaarruimte*) Engine**: Belastingdienst calculation calculating immediate Box 1 tax rebates (up to 49.5%) and Factor A (*pensioenaangroei*) integration from UPO statements.
- **Certified Groenfondsen Arbitrage**: Double tax benefit calculator (Box 3 exemption up to €71,251 / €142,502 + 0.1% Box 1 credit, ~2.27% risk-free tax alpha).

### 6. 🤖 Sandboxed Offline AI Copilot (`agent/copilot.py`)
- **25 Native Deterministic Tools**: Copilot routes user intent to native Python optimization engines for net worth, spending analytics, mortgage recalculation, capital simulation, pension room, green fund arbitrage, and tax leak detection.
- **Persistent Local SQLite Vector RAG**: Multi-document knowledge vault referencing Dutch tax codes, mortgage deduction laws, and Groenfondsen, stored persistently in SQLite WAL with hybrid semantic vector + BM25 search.
- **Dynamic Interactive Plotly Charts**: Automatically generates interactive bar, line, area, and trajectory charts directly inside chat turns (`agent/chart_renderer.py`).
- **Autonomous Zero-Shot Statement Parsing**: Automatically extracts structured transactions from unsupported or foreign statement documents using the local LLM.

### 7. 🔒 Global Screen-Shield Privacy Mode
- Single-click global toggle masks all currency numbers across every table, metric card, and visualization with `****`, enabling safe screen sharing, demos, and public streaming.

---

## 🔌 Ingestion Rails & Connectors

| Connector | Method | Supported Entities |
| :--- | :--- | :--- |
| **Enable Banking (PSD2 AISP)** | Direct REST API (RSA-2048 / RS256 JWT) | ABN AMRO, Revolut, ING, Rabobank, and 2,500+ European financial institutions |
| **eToro Broker Connector** | Direct REST API with Local Mirror Cache | Cash balance, open positions, closed positions, profit/loss |
| **ABN AMRO Statement Parser** | Native Regex / Tab-delimited (`.TAB`) | Checking, savings, and business accounts |
| **Revolut Parser** | Structured CSV Parser | Multi-currency transactions and pocket vaults |
| **Trade Republic Parser** | PDF / CSV Parser | Cash interest payouts, stock trades, ETF savings plans |
| **Banking Standards** | CAMT.053 XML & MT940 Parsers | Universal European banking transaction files |
| **Autonomous Fallback** | Local LLM Zero-Shot Schema Extractor | Any unstructured bank or credit card export format |

---

## 🚀 Getting Started

### Prerequisites
1. **[Git](https://git-scm.com/downloads)**
2. **[Python 3.12+](https://www.python.org/downloads/)**
3. **[Ollama](https://ollama.com/)** *(Recommended for AI Copilot)*:
   ```powershell
   ollama run qwen2.5:7b-instruct
   ```

### Quick Installation (Windows 11)
Clone repository and run the automated PowerShell setup script:
```powershell
git clone https://github.com/ayushj190/personal-finance-assistant.git
cd personal-finance-assistant
.\install.ps1
```
The installer automatically:
- Creates a sandboxed virtual environment (`.venv/`)
- Installs dependencies from `requirements.txt`
- Initializes `data/finance.db` with idempotent SQLite migrations
- Creates a desktop shortcut for one-click startup

### Running the Application
Launch via desktop shortcut or terminal:
```cmd
run.bat
```
Application opens at `http://localhost:8501`. Telemetry is disabled by default.

---

## 🧪 Testing & Reliability

The application maintains an automated test suite across all critical domains:

```powershell
.\.venv\Scripts\python -m unittest discover -s tests -v
```

```
Ran 47 tests in 0.430s — OK
```

### Verified Coverage Areas
- **Database & Migrations**: Idempotent schema migrations, occurrence indices, and currency conversions.
- **Financial Math**: Dutch annuity and linear mortgage amortization, portfolio 5/25 drift, and dividend yield projections.
- **Connector Ingestion**: ABN AMRO, Revolut, eToro, MT940, and CAMT.053 parsing pipelines.
- **Security & Sandboxing**: Symmetric Fernet secrets vault encryption roundtrip and SQLite read-only query denial.
- **UI Integrity**: Privacy masking consistency, formatters, and status badges.

---

## 🗺️ Product Roadmap & Status

- [x] **Phase 1: Local Ingestion & Storage Engine** (SQLite WAL, Enable Banking PSD2, CSV/TAB/MT940/CAMT.053 parsers)
- [x] **Phase 2: Core Financial Analytics** (Net worth ribbons, Sankey spend flows, subscription leak detection)
- [x] **Phase 3: Wealth & Liability Engines** (5/25 portfolio rebalancer, Dutch mortgage simulator, Box 1/3 tax modeler)
- [x] **Phase 4: Sandboxed AI Copilot** (Local Ollama integration, 20 native tools, threaded `@st.fragment` execution, Dutch tax RAG)
- [x] **Phase 5: Enterprise-Grade Privacy & Testing** (Windows Credential Manager vault, global UI privacy masking, 45 unit tests)
- [ ] **Phase 6 (In-Flight)**: Multi-year net worth Monte Carlo simulation and automated PDF tax filing pack export.

---

## 📄 Compliance & Governance

- **[System Architecture](ARCHITECTURE.md)**: Deep dive into the threading model, security sandbox, and data schemas.
- **[Privacy Policy](PRIVACY.md)**: GDPR and EU AI Act compliance specifications.
- **[Terms of Service](TERMS.md)**: Open banking connectivity and disclaimers.
