# Rationale: 0001 · Modular Data Pipeline & UI Component Decoupling

## Context

The Personal Finance Assistant is built as a local first Windows application using Streamlit, SQLite in write ahead logging mode, and local Ollama models. While the application functions well feature wise, maintenance and bug fixing have become stubborn due to tight coupling across multiple subsystems.

Several architectural pain points currently limit progress:
1. **Tight Coupling of Queries and UI Layout**: Streamlit pages directly execute raw SQL queries, inspect database table columns, and perform complex business logic during layout rendering. This causes frequent layout bugs, subtle state desynchronization, and duplicated data fetching logic across pages.
2. **Monolithic Styling and Monkey Patching**: The current styling module spans over 1,500 lines, mixing color definitions, massive raw CSS strings, and runtime monkey patching of `st.plotly_chart`. This makes UI styling fragile and hard to adjust safely.
3. **Streamlit Context and Background Thread Collisions**: Background tasks (auto synchronization and local Copilot inference) interact with Streamlit session state and rerun schedules. When thread execution context detaches, Streamlit generates silent errors or rerun loops.
4. **Startup Migration Overhead**: The migration script executes comprehensive DDL and seeding on every application rerun, running unnecessary table inspections and insert attempts.

Without decoupling these layers, adding new capabilities (such as multi currency tracking, unified cash flow forecasting, or advanced portfolio risk attribution) will compound existing maintenance hurdles.

## Options considered

### Option 1: Full Layered Monolith with Typed Repositories & Worker Coordination (Chosen)

Extract domain queries into repository classes returning typed dataclasses, split styling into modular tokens and static CSS files, coordinate background tasks with thread safe status containers, and transition database migrations to versioned SQL files.

**Pros**:
- Establishes clear component boundaries while maintaining the single process local first deployment model.
- Strongly typed entities make refactoring predictable and prevent silent dictionary key typos.
- Removes monkey patching and isolates UI rendering from database access.
- Eliminates repetitive migration checks on application startup.

**Cons**:
- Requires updating existing page scripts to call repository and service functions instead of inline SQL.

### Option 2: Ad-Hoc Utility Extraction (Incremental Query Functions)

Keep dictionary and `sqlite3.Row` structures, moving SQL queries into a shared `db/queries.py` file without defining typed domain entities or modularizing CSS.

**Pros**:
- Lower initial migration effort.

**Cons**:
- Retains untyped dictionary access where field name mismatches can fail silently at runtime.
- Leaves massive styling files and thread context vulnerabilities untouched.

### Option 3: Distributed Multi-Service Architecture

Split the backend into a local FastAPI REST service running alongside a separate Streamlit or React frontend.

**Pros**:
- Enforces strict process isolation between data processing and UI display.

**Cons**:
- Introduces excessive overhead for a local first desktop application, including port management, serialization latency, and multiple background processes.
- Violates the principle of minimum code and simple operational reality.
