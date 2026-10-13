# UI Layer

## Overview

The UI layer houses the Streamlit presentation tier for the personal finance assistant. It renders the primary dashboard, portfolio analytics, spending breakdowns, tax calculators, dialog forms, and the Copilot sidebar.

## Key files

| File | Owns |
|---|---|
| `ui/theme/` | Design system tokens (`tokens.py`), theme styles (`common.css`, `dark.css`, `light.css`), and Plotly theme engine (`charts.py`) |
| `ui/copilot_sidebar.py` | Non blocking Copilot assistant panel, message threads, and quick actions |
| `ui/pages/dashboard.py` | High level net worth KPIs, cash flow trends, and account summaries |
| `ui/pages/investments/` | Tabbed portfolio holdings, native allocation donut & exposure bars, drift analysis, dividends, and FIRE goals |
| `ui/pages/spending.py` | Expense categorization views, monthly burn rates, and budget allocations |
| `ui/pages/transactions.py` | Searchable transaction ledger, inline filters, and manual edits |
| `ui/dialogs.py` | Modal dialog popups for adding manual accounts, debts, and holdings |
| `ui/charts.py` | Reusable Plotly chart builders for cash flows and allocation breakdowns |
| `ui/pages/mortgage.py` | Dutch 30-year mortgage amortization curves, penalty-free prepayments, and home equity |
| `ui/pages/tax.py` | Dutch Box 1, Box 3 wealth tax, Jaarruimte pension room, and Groenfondsen arbitrage |
| `ui/pages/import_files.py` | Hybrid statement ingestion workflow, file format detection, and manual account linkage |
| `ui/pages/settings.py` | API secrets vault, manual accounts setup, category management, and local database backups |

## Conventions

- Wrap background polling loops in `@st.fragment` to avoid triggering full page re-renders.
- Check `st.session_state["hide_amounts"]` before displaying sensitive euro values or account balances.
- Use explicit keys for all input widgets to maintain persistent state across page navigation.
- Keep business logic and calculation algorithms inside `services/`, keeping UI files focused on layout and user interactions.
- Copilot navigation: sidebar chips and the action layer write the intent and `flt_state` (`ui/filters.py`); the date scope is resolved once by `services/date_scope.py` so the page and the chat answer agree. Hide values masks money only, keeping asset names, merchants, counts, and percentages readable.

## Gotchas

- Background workers altering Streamlit state must register via `add_script_run_ctx` to avoid missing context exceptions.
- Triggering `st.rerun(scope="app")` from within a fragment forces a top level re-render, whereas default reruns stay local to the fragment.
- Plotly charts must disable default Streamlit themes by passing `theme=None` to ensure custom CSS backgrounds remain visible.

_Drafted by /audit from the repo, worth a quick human pass. Edit freely: once a line stops matching this draft, later runs treat it as curated and will flag rather than overwrite it._
