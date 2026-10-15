# 0023. Package standalone macOS desktop application for expense tracking (Rationale)

**Date**: 2026-10-14

## Context

The current application runs through Streamlit in a local terminal or browser environment. It bundles local intelligence features such as Ollama, fastembed, and vector extensions, alongside external brokers such as eToro. These machine learning dependencies require significant RAM, disk space, and runtime background services.

On an 8GB RAM MacBook Air, running local language models and embedding pipelines alongside daily desktop apps causes memory pressure and system swapping. Furthermore, sharing the project with a family member who is not a software developer requires a double click installation experience rather than manual Python environment setups and terminal commands.

The user needs a lightweight Mac application bundle that focuses strictly on personal expense management and statement imports. The application must install cleanly, preserve user financial records across updates, and run reliably without technical intervention.

## Options considered

### Option 1: PyInstaller bundle with pywebview native window

This approach bundles a Python runtime and application code with PyInstaller, runs Streamlit headlessly on a loopback socket, and renders the user interface in a native Cocoa webview using pywebview.

**Pros**:
- Provides a genuine desktop application feel with no visible browser tabs or address bars.
- Python ecosystem tooling only, requiring no Node.js, Rust, or JavaScript desktop frameworks.
- Clean process isolation where closing the window shuts down the local server immediately.

**Cons**:
- Requires packaging Streamlit static frontend assets and hidden imports explicitly in a spec file.
- PyInstaller must be executed directly on a macOS host to produce a macOS binary.

### Option 2: Electron or Tauri container embedding Python

This approach builds a dedicated desktop shell in Electron or Tauri that spawns the Python backend as a child sidecar process.

**Pros**:
- Rich native operating system integrations, dock menus, and system tray capabilities.
- Tauri provides very small binary sizes for its native window wrapper.

**Cons**:
- Introduces extra toolchain dependencies such as Node.js, npm, or Rust and Cargo.
- High architectural complexity for synchronizing two separate runtime environments.
- Electron consumes substantial additional RAM, which runs contrary to the 8GB memory budget.

### Option 3: Browser launcher app bundle

This approach packages a simple macOS shell script or minimal Python wrapper inside an application bundle that launches Streamlit in the background and opens the user default web browser.

**Pros**:
- Minimal packaging complexity and smallest possible executable size.
- Standard browser developer tools and zoom shortcuts work out of the box.

**Cons**:
- Lacks a native app feel because it opens inside existing browser sessions among everyday tabs.
- Closing browser tabs leaves background Streamlit processes running orphaned until killed.

## Rationale

Option 1 gives your brother a genuine desktop application experience while staying entirely within the Python ecosystem. By using pywebview, the window looks and behaves like a standard Mac program rather than an open browser tab, and closing the window automatically shuts down the background server.

Option 2 would add unnecessary build friction and memory overhead through Node.js or Rust toolchains. Option 3 creates orphan background processes because web browsers do not notify background servers when tabs close.

By pairing Option 1 with a trimmed dependencies file that removes Ollama, fastembed, and vector extensions, the app runs comfortably within 200 to 350 megabytes of memory. This leaves plenty of headroom on an 8GB RAM MacBook Air. Because PyInstaller cannot cross compile a Mac app from Windows, a GitHub Actions workflow handles the compilation on Apple Silicon runners automatically.
