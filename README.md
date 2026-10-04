# Personal Finance Assistant (PFA)

Local-first, private personal finance assistant for Windows 11.
Integrates ABN AMRO, Revolut, eToro, and Trade Republic into a local SQLite database, offering automated normalization, categorization, investment rebalancing, mortgage tracking, and an offline AI analyst powered by Ollama.

Zero cloud aggregation. Zero telemetry. All financial data remains on your machine.

---

## 🚀 Quick Start

### 1. Installation
Run PowerShell as administrator (or normal user) in the project directory:
```powershell
.\install.ps1
```
This will:
- Check for Python 3.12+
- Create the virtual environment in `.venv/`
- Install all dependencies (`requirements.txt`)
- Run database migrations (`data/finance.db`)
- Create a desktop shortcut for `run.bat`

### 2. Launch
Double-click the desktop shortcut or run:
```cmd
run.bat
```
Streamlit will launch locally at `http://localhost:8501` with telemetry disabled (`gatherUsageStats = false`).

---

## 🔒 Security & Privacy Architecture

- **Database:** Local SQLite database at `data/finance.db` using WAL mode. No external database servers or cloud databases.
- **Secrets Vault:** Fernet symmetric encryption storing credentials in `data/vault.bin`. Master encryption key stored securely in the Windows Credential Manager via `keyring`.
- **AI Analyst Sandbox:** The AI Analyst runs read-only SQL queries via a strict SQLite authorizer. It only has access to sanitized reporting views (`v_transactions`, `v_net_worth_daily`, `v_holdings`, `v_monthly_cashflow`, `v_mortgage_payments`). Any `INSERT`, `UPDATE`, `DELETE`, `DROP`, `PRAGMA`, or `ATTACH` statements are automatically blocked at the engine level.
- **Offline LLM:** Analyzes questions and generates SQL via a local Ollama instance (`qwen2.5-coder:7b`). No prompt or transaction data ever leaves your computer.

---

## 🛠️ Features & Pages

- **📊 Dashboard:** Real-time KPI ribbon (Net Worth, Liquid Cash, Invested, Savings Rate, Runway), net worth stacked area chart, category donut, and detected upcoming bills.
- **🛒 Spending:** Multi-level Sunburst and Donut breakdown (Parent Category → Category → Merchant), top merchants table, and subscription leak detector.
- **🌊 Cash Flow:** Interactive Sankey diagram tracing inflows to fixed expenses (with mortgage interest/principal split), discretionary spending, and savings.
- **📈 Investments:** Holdings table, portfolio allocation tracker with 5/25 tolerance drift alerts, and 3 rebalancing calculators (*No-sell injection*, *Monthly water-filling*, *Full rebalance*).
- **🏠 Mortgage:** Complete 30-year amortization schedule (Annuity, Linear, Interest-Only), interest vs principal breakdown, and penalty-free extra repayment simulator (*Boetevrij aflossen*).
- **📝 Transactions:** Editable data table with instant category learning: manual recategorization immediately creates a user rule and re-applies it across past transactions.
- **📥 Import:** Dropzone supporting ABN AMRO (.TAB), Revolut (CSV), eToro Money (TSV), Trade Republic (CSV), MT940 (.sta/.940), and CAMT.053 XML.
- **🧠 AI Analyst:** Natural language financial queries with visual charts, query tables, and collapsible SQL inspection.
- **⚙️ Settings:** Secure credential management for PSD2 Enable Banking, eToro, Trade Republic, mortgage parts, allocation presets, and one-click database backups.

---

## 🧪 Testing

Run the full automated test suite:
```powershell
.\.venv\Scripts\python -m unittest discover -s tests -v
```
All 22 unit tests verify database migrations, deduplication hash logic, merchant cleaning rules, statement import parsers, savings & runway math, rebalancing engines, mortgage schedules, and SQL sandbox query denial.
