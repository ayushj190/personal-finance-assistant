# Personal Finance Assistant (PFA)

A local-first, privacy-focused personal finance assistant for Windows 11.

Integrates Open Banking (ABN AMRO, Revolut), brokers (eToro, Trade Republic), and manual file imports into a secure local SQLite database. Offers automated transaction categorization, investment rebalancing, mortgage tracking, and an offline **AI Copilot** powered by local LLMs (Ollama) to perform complex financial analysis without your data ever leaving your machine.

Zero cloud aggregation. Zero telemetry. 100% private.

---

## 📖 Documentation

- **[Architecture & Security](ARCHITECTURE.md)**: Detailed overview of the system design, offline LLM sandbox, and encrypted credential vault.
- **[Privacy Policy](PRIVACY.md)**: GDPR and EU AI Act compliance details.
- **[Terms of Service](TERMS.md)**: Usage guidelines and bank connectivity terms.

---

## 🚀 Getting Started

Follow these steps to clone and run the application on your own machine.

### Prerequisites
1. **[Git](https://git-scm.com/downloads)**: To clone the repository.
2. **[Python 3.12+](https://www.python.org/downloads/)**: Required for running the backend and Streamlit UI.
3. **[Ollama](https://ollama.com/)** *(Optional but highly recommended)*: Required for the local AI Copilot features. Once installed, pull the default model:
   ```powershell
   ollama run qwen2.5:7b-instruct
   ```

### 1. Clone the Repository
Open PowerShell or your preferred terminal and clone the repository:
```powershell
git clone https://github.com/ayushj190/personal-finance-assistant.git
cd personal-finance-assistant
```

### 2. Installation
Run the provided installation script (as Administrator or normal user):
```powershell
.\install.ps1
```
This script will automatically:
- Create a Python virtual environment in `.venv/`
- Install all dependencies from `requirements.txt`
- Run database migrations to initialize `data/finance.db`
- Create a handy desktop shortcut for `run.bat`

### 3. Launch the Application
Double-click the generated desktop shortcut, or run:
```cmd
run.bat
```
The Streamlit interface will launch locally in your browser at `http://localhost:8501`. Telemetry is disabled by default.

---

## 🛠️ Features & Modules

- **🔒 Global Privacy Mode:** Hide all financial numbers with currency symbols and `****` across the app with a single click. Ideal for screen sharing.
- **🤖 Background AI Copilot:** Chat with your finances while navigating the app. The AI can execute complex Python analytics and safe SQL queries without blocking your UI.
- **📊 Dashboard:** 4-KPI ribbon (Net Worth, Liquid Cash, Investments, Runway buffer), accounts grid, net worth trend chart, and upcoming recurring bills.
- **🛒 Spending:** Month-by-month trends, interactive category drill-down visuals, **Cash Flow Sankey Diagram**, top merchants ranking, and a subscription leak detector.
- **📈 Investments:** Direct holdings table with embedded TradingView live market widgets, eToro/Trade Republic tracker, 3 rebalancing calculators with 5/25 drift alerts, **FIRE Trajectory Calculator**, **Tax-Loss Harvesting Assistant**, and **Savings Goals tracking**.
- **🏠 Mortgage:** Complete 30-year amortization schedule (Annuity, Linear, Interest-Only) and penalty-free extra repayment simulators (*Boetevrij aflossen*).
- **📝 Transactions:** Instant category learning. Manual recategorization creates a local rule and re-applies it automatically.
- **📥 Import:** Support for ABN AMRO (.TAB), Revolut (CSV), eToro (TSV), Trade Republic (PDF/CSV), MT940, and CAMT.053 XML.

---

## 🧪 Testing & Development

Run the full automated test suite to ensure local integrity:
```powershell
.\.venv\Scripts\python -m unittest discover -s tests -v
```
All 48 unit tests verify database migrations, merchant cleaning rules, statement import parsers, savings math, rebalancing engines, UI privacy masking, and the strict SQL sandbox query denial.
