# 0023. Package standalone macOS desktop application for expense tracking

**Date**: 2026-10-14
**Status**: In Progress

## Summary

This decision defines how to package the application as a standalone desktop application for macOS. We wrap a headless Streamlit server inside a native pywebview window and exclude heavy local artificial intelligence tools. This keeps memory usage low for an 8GB RAM MacBook Air while preserving core expense tracking and bank statement imports. A dedicated entry script handles desktop lifecycle management and stores data in standard macOS application support folders.

## Requirements

**User stories**:
- As a Mac user, I want to download and open a single desktop application without touching a terminal so that I can track my personal expenses easily.
- As a user on an 8GB RAM MacBook Air, I want the application to use minimal memory and no background artificial intelligence processes so that my laptop stays cool and responsive.
- As a user importing statements, I want to upload PDF, CSV, and MT940 bank export files so that my ledger transactions stay up to date.

**Acceptance criteria**:
- **AC-1**: The application launches from an application bundle into a standalone native desktop window without exposing Streamlit server URLs or browser chrome.
- **AC-2**: Closing the desktop application window cleanly terminates the background Streamlit server process and releases all system ports and memory.
- **AC-3**: Application user data, SQLite database files, and uploaded statements persist in `~/Library/Application Support/PersonalFinanceAssistant/` so that application updates never erase records.
- **AC-4**: Heavy machine learning dependencies including Ollama, fastembed, and sqlite-vec are absent from the desktop build, keeping total idle application memory under 350 megabytes.
- **AC-5**: The desktop navigation provides access to Dashboard, Spending, Transactions, and Settings pages, while excluding the Copilot chat sidebar and eToro connector.
- **AC-6**: A GitHub Actions workflow compiles the application on a macOS runner, produces a DMG disk image, and provides step by step Gatekeeper bypass instructions for unsigned execution.

## Decision

**Chosen option**: Option 1: PyInstaller bundle with pywebview native window

We package the desktop edition using PyInstaller and pywebview. A lightweight entrypoint file handles macOS application paths, starts a headless Streamlit server on an available localhost port, and displays the interface in a dedicated native window.

**Implementation skills**: `developing-with-streamlit` (local, `.agents/skills/developing-with-streamlit/`)

## Feature design

### Desktop entrypoint design

A new entrypoint named `desktop_app.py` serves as the desktop runner. It performs initial bootstrapping before starting Streamlit:

1. Resolves the user data directory at `~/Library/Application Support/PersonalFinanceAssistant/`, creates it if missing, and exports `os.environ["PFA_DATA_DIR"]` so `core/config.py` redirects SQLite and imports there instead of inside the read only application bundle.
2. Finds an open TCP port on loopback using Python `socket` to avoid port collisions.
3. Spawns Streamlit in a daemon thread via `streamlit.web.cli.main` with command flags `--server.headless=true`, `--server.address=127.0.0.1`, `--browser.gatherUsageStats=false`, and `--global.developmentMode=false`.
4. Polls `http://127.0.0.1:<port>/_stcore/health` until receiving status 200 (timeout after ten seconds).
5. Launches `webview.create_window` with title "Personal Finance Assistant", width 1280, height 840, and minimum size 960x640.
6. Catches the window closed event to terminate the process cleanly.

### Trimmed desktop page navigation

The desktop entry file launches a streamlined page layout (`ui/desktop_navigation.py` or conditional navigation in `app.py`):
- Dashboard: general net worth, accounts overview, and monthly summaries.
- Spending: expense breakdowns, categorization, and budgeting graphs.
- Transactions: transaction ledger, filters, and manual additions.
- Settings: manual account balances, theme switching, and import logs.
- Excluded: Copilot sidebar, AI natural language query bars, and eToro connector cards.

### Memory footprint management

The build uses a tailored package profile named `requirements-desktop.txt` containing only what is required:
- Keep: `streamlit`, `plotly`, `pandas`, `httpx`, `cryptography`, `keyring`, `openpyxl`, `pypdf`, `mt-940`, `pywebview`, `pyinstaller`.
- Drop: `ollama`, `fastembed`, `sqlite-vec`, `pytr`.

This omission saves more than 1.5 gigabytes of disk space and eliminates background neural network inferencing, keeping memory usage minimal.

### Storage paths and persistence

On macOS, files must never be written inside the read only `.app` bundle:
- Database: `~/Library/Application Support/PersonalFinanceAssistant/finance.db`
- Migrations: run automatically on database connection during startup.
- Temporary statement uploads: written to operating system temp directories and cleared after parsing.

### Value sourcing

| Action | Value produced / displayed | Source |
|---|---|---|
| Initialize storage | Application data directory path | Standard library `pathlib.Path.home() / "Library/Application Support/PersonalFinanceAssistant"` |
| Bind server port | Available localhost port number | Python `socket` module binding to port 0 on loopback |
| Verify server readiness | Health status code 200 | HTTP GET request to `http://127.0.0.1:<port>/_stcore/health` |
| Window title | "Personal Finance Assistant" | Hardcoded string parameter passed to `webview.create_window` |
| Ledger transactions | Categorized transaction rows | Existing `TransactionRepository` querying `finance.db` |
| Statement ingestion | Parsed records from PDF and CSV | Existing `services/file_import_service.py` parsers |

### Key invariants

- Financial data and transaction records must reside exclusively in the user home application support directory.
- No network requests may be initiated to external artificial intelligence services or telemetry endpoints.
- When the pywebview window is closed by the user, all child threads and local web servers must terminate within three seconds.

### Security model and Gatekeeper

Because the application bundle will not be signed with an Apple Developer paid certificate, macOS Gatekeeper will quarantine the downloaded file.
- The DMG package will include a plain text quick start document.
- Instructions will guide the recipient to right click the application in Applications and select Open, or run `xattr -cr "/Applications/Personal Finance Assistant.app"` in Terminal once to clear the quarantine bit.

### Critical test scenarios

- Main desktop launch: App bundle launches, opens a single native window showing the financial dashboard within five seconds, verifies **AC-1**.
- Clean shutdown: User clicks the window close button or presses Command Q, process terminates completely with zero orphan Python processes, verifies **AC-2**.
- Data preservation across restarts: User imports a bank statement CSV, closes the application, reopens it, and sees all imported transactions intact, verifies **AC-3**.
- Memory efficiency: App runs on an Apple Silicon Mac with idle memory footprint below 350 megabytes, verifies **AC-4**.
- Statement import: User drags a PDF or CSV bank statement onto the transactions page, records parse and categorize without requiring AI libraries, verifies **AC-5**.
- Packaging workflow: GitHub Actions builds a DMG artifact on `macos-14` runner successfully, verifies **AC-6**.

## Build plan

- [x] 1. Create `requirements-desktop.txt` containing only the lightweight core dependencies, satisfies **AC-4**.
- [x] 2. Update configuration helpers in `core/config.py` to recognize a desktop execution mode and use macOS application support directory paths, satisfies **AC-3**.
- [x] 3. Create `desktop_app.py` script with loopback socket allocation, headless Streamlit server management, and pywebview window binding, satisfies **AC-1**, **AC-2**.
- [x] 4. Create a lightweight navigation view that renders Dashboard, Spending, Transactions, and Settings without the Copilot sidebar or eToro references, satisfies **AC-5**.
- [x] 5. Create `desktop_app.spec` for PyInstaller with hooks collecting Streamlit static assets and pywebview frameworks, satisfies **AC-1**.
- [x] 6. Create local packaging script `scripts/build_mac.sh` and GitHub Actions workflow `.github/workflows/build-mac-dmg.yml` to assemble the DMG, satisfies **AC-6**.

## Consequences

**Positive**:
- Brother receives a standalone Mac application that opens with a double click.
- Memory consumption stays comfortably within the 8GB RAM constraints.
- Existing database schema, business logic, and statement parsers are reused without modification.
- Main repository and web application continue functioning normally.

**Negative / tradeoffs**:
- macOS executable cannot be built directly on Windows; building the release requires running the GitHub Actions workflow on a macOS runner or running the build script on a physical Mac.
- Unsigned application requires a one time right click open step to clear macOS Gatekeeper quarantine.
- Packaging updates require recompiling the application bundle rather than just pulling code changes.

**Neutral**:
- Initial startup takes two to four seconds while the local Streamlit server boots behind the native window.

## Migration plan

**Strategy**: Strangler side by side pattern

**Phases**:
1. Add `desktop_app.py`, `requirements-desktop.txt`, and build configuration files alongside existing code.
2. Verify local standalone execution on a Mac or macOS virtual environment.
3. Deploy GitHub Actions workflow to generate and download release DMG files.

**Rollback**:
The desktop packaging consists of auxiliary files and does not modify existing web server code. If issues arise, delete the desktop entry files without impacting the core system.

**Risks**:
Streamlit internal package layout changes across versions can occasionally require adjusting hidden imports in `desktop_app.spec`.

## Follow-up

- [ ] Add an application icon file `assets/app_icon.icns` for a polished dock and desktop presence.
- [ ] Provide brother with sample statement files and a short quick start guide for first launch.
