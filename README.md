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

- **🔒 Global Privacy Mode:** Global sidebar toggle (`🔒 Privacy Mode`) masking all financial numbers with currency symbols and `****` across KPI cards, account grids, data tables, and metrics.
- **📊 Dashboard:** 4-KPI ribbon (Net Worth, Liquid Cash, Investments, Runway buffer), interactive Accounts & Balances grid with connection status badges and inline balance adjustment popovers, net worth trend chart, 30-day category spending donut, and upcoming recurring bills.
- **🛒 Spending:** Month-by-month spending trends bar chart, monthly breakdown table, dedicated monthly scope selector (*All Months* or specific month), 4-metric expense overview (Total, Fixed, Discretionary, Uncategorized), hierarchical Sunburst & Donut visualizers, top merchants ranking, and subscription leak detector.
- **📈 Investments:** Direct holdings table, eToro Copied Traders & CopyPortfolios tracker (with dual USD/EUR metrics, return percentages, and expandable underlying positions breakdown), portfolio allocation tracker with 5/25 tolerance drift alerts, and 3 rebalancing calculators (*No-sell injection*, *Monthly water-filling*, *Full rebalance*).
- **🏠 Mortgage:** Complete 30-year amortization schedule (Annuity, Linear, Interest-Only), interest vs principal breakdown, and penalty-free extra repayment simulator (*Boetevrij aflossen*).
- **📝 Transactions:** Editable data table with instant category learning: manual recategorization immediately creates a user rule and re-applies it across past transactions.
- **📥 Import:** Dropzone supporting ABN AMRO (.TAB), Revolut (CSV), eToro Money (TSV), Trade Republic (account statements & trade confirmation PDFs / CSV), MT940 (.sta/.940), and CAMT.053 XML.
- **🧠 AI Analyst & Merchant Intelligence:** Natural language financial queries with visual charts, query tables, and collapsible SQL inspection via local Ollama (`qwen2.5-coder:7b`). Features heuristic categorization for Dutch/international merchants and optional Brave Search API web lookup for unknown merchants.
- **⚙️ Settings:** Secure credential management for PSD2 Enable Banking, eToro, Trade Republic cash accounts & APY interest rates, mortgage parts, allocation presets, Brave Search API, and one-click database backups.

---

## 🧪 Testing

Run the full automated test suite:
```powershell
.\.venv\Scripts\python -m unittest discover -s tests -v
```
All 37 unit tests verify database migrations, deduplication hash logic, merchant cleaning rules, statement import parsers (including Trade Republic multi-format statements and closing balances), savings & runway math, rebalancing engines, mortgage schedules, eToro connectors, UI components & privacy masking, and SQL sandbox query denial.

