# Verify: Standalone macOS App Packaging · spec 0023 · updated 2026-10-14
_Steps derived from spec 0023 acceptance criteria. `/check verify` runs these; `/test` locks the durable ones._

## UI / manual
- [ ] Launch `python desktop_app.py` or double click application bundle on macOS → opens single native Cocoa webview window titled "Personal Finance Assistant" at 1280x840 without browser tabs, address bars, or exposed Streamlit port URLs → AC-1
- [ ] Click window close button or press Command Q → pywebview window closes, background Streamlit server terminates, and loopback port is released within 3 seconds with zero orphan processes → AC-2
- [ ] Drag bank statement CSV or PDF onto Transactions or Import tab, close application, and reopen → financial ledger rows and `finance.db` persist intact in `~/Library/Application Support/PersonalFinanceAssistant/` → AC-3
- [ ] Inspect macOS Activity Monitor for PersonalFinanceAssistant process while idle → resident memory stays below 350 megabytes with zero Ollama, fastembed, or neural network subprocesses → AC-4
- [ ] Inspect navigation bar and Settings view in desktop window → top navigation shows Dashboard, Spending, Transactions, and Settings tabs, Copilot chat sidebar is absent, and eToro integration card is hidden → AC-5

## Commands
- [ ] `.\.venv\Scripts\python.exe -m unittest tests/test_desktop_packaging.py` → 9 unit tests pass verifying config directory resolution, loopback socket binding, health polling, dependency profiling, spec exclusions, and Gatekeeper script contents → AC-1, AC-3, AC-4, AC-5, AC-6
- [ ] `grep -E "ollama|fastembed|sqlite-vec|pytr" requirements-desktop.txt` → returns exit code 1 confirming heavy machine learning and broker packages are omitted from desktop profile → AC-4
- [ ] `grep "PFA_DESKTOP" app.py` → returns active branching for desktop navigation and sidebar exclusion → AC-5
- [ ] Run GitHub Actions workflow `build-mac-dmg.yml` on `macos-14` runner → builds compressed DMG disk image containing application bundle, `/Applications` symlink, and `QUICKSTART_GATEKEEPER.txt` → AC-6

## Acceptance-criteria coverage
- AC-1 covered by UI launch step and test_desktop_runner_port_finder, test_desktop_runner_wait_for_server_success
- AC-2 covered by UI close step and desktop_app on_closed os._exit termination
- AC-3 covered by persistence UI step and test_config_macos_desktop_directory_resolution, test_config_pfa_data_dir_override
- AC-4 covered by Activity Monitor check and test_desktop_requirements_profile, test_pyinstaller_spec_excludes_ml
- AC-5 covered by navigation inspection UI step and test_desktop_navigation_page_inventory, settings desktop filtering
- AC-6 covered by build-mac-dmg workflow step and test_build_mac_script_has_gatekeeper_docs
