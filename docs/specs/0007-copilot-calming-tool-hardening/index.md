# 0007. Copilot Calming & Tool Hardening

**Date**: 2026-10-11
**Status**: Accepted

## Summary

This decision calms the personal finance copilot sidebar into an on demand assistant and hardens its database query tools. Background tasks stay completely quiet and decoupled from copilot session state so that inference runs only when you enter a prompt or click an action. Ollama connectivity is checked before thread execution so that offline models present clear troubleshooting advice rather than silent task failures. All database access for copilot query tools runs through an engine level read only SQLite authorizer, and tool errors return friendly guidance with collapsible technical diagnostics.

## Context

The rationale and decision context are recorded in rationale.md.

## Requirements

**User stories**:
- As a user, I want the copilot to run only when I explicitly ask for help so that background automation never interrupts me or consumes system resources unprompted.
- As a user, I want clear guidance when Ollama is offline so that I know how to start the local language model without seeing cryptic connection errors.
- As a user, I want query tools to be strictly read only so that conversational turns can never alter or corrupt my financial ledger.
- As a user, I want tool failures to show friendly troubleshooting steps so that I can fix missing data or configuration issues easily.

**Acceptance criteria**:
- **AC-1**: Pure on demand execution. The copilot sidebar initiates LLM inference and background threads strictly in response to an explicit user prompt or quick action button click. Background synchronization routines remain completely silent and decoupled from copilot state, generating zero unprompted chat messages or inference calls.
- **AC-2**: Upfront Ollama connectivity verification. The copilot verifies connection to the local Ollama instance before launching a background task. If Ollama is offline or unreachable, the sidebar renders a friendly warning with the command to start Ollama (`ollama serve`), without launching a failing background thread.
- **AC-3**: Dedicated read only SQLite authorizer. A dedicated database connection helper `db.database.connect_readonly()` attaches an engine level SQLite authorizer via `sqlite3.Connection.set_authorizer` that permits only read operations (`SQLITE_SELECT`, `SQLITE_READ`, and PRAGMA reading) and strictly denies any write, update, delete, table creation, or schema modification. All copilot database query tools execute through this read only connection.
- **AC-4**: Structured query tool error recovery. When any tool execution encounters an exception (such as a database lock, connection timeout, or invalid parameter), `execute_tool` captures the error and returns a structured payload with success status false, a user friendly explanation, and diagnostic details. The assistant presents a helpful remedy in chat, while technical diagnostics appear in a collapsed troubleshooting card.
- **AC-5**: Informative empty dataset handling. Query tools encountering empty ledgers, missing accounts, or unconfigured tax profiles return structured guidance explaining what data is missing and pointing to the specific app page or action to populate it (such as importing a statement or opening a profile modal), rather than returning blank responses.
- **AC-6**: Transparent quick actions chat logging. Clicking any sidebar quick action button (such as Assess Risk, Categorize, or Check Drift) logs an explicit user message bubble in chat history before triggering execution, keeping conversation turns transparent and reproducible.
- **AC-7**: Tool schema hardening and parameter sanitization. All tools in `agent/tool_schemas.py` and `agent/tools.py` sanitize input arguments with bounds checking on numeric limits, type coercion, and date validation, rejecting malformed parameters gracefully with an explanatory message before executing queries.

## Options considered

Options and trade offs are evaluated in rationale.md.

## Decision

**Chosen option**: Option 1: On demand activation with engine level read only authorizer, upfront Ollama health verification, and structured tool diagnostics.

The copilot executes only on explicit user request, verifies Ollama availability upfront, queries SQLite through a strict engine level authorizer, and recovers from tool exceptions with structured diagnostic cards.

## Rationale

Reasoning and options: see rationale.md.

## Feature design

**Data model sketch**:

No new database tables are created. The database connection factory in `db/database.py` introduces a specialized read only connection routine:

```python
def connect_readonly(db_path: Path | str = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{Path(db_path).resolve().as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    conn.set_authorizer(readonly_authorizer)
    return conn
```

The authorizer callback evaluates SQLite action codes:
- Allowed action codes: `SQLITE_SELECT`, `SQLITE_READ`, `SQLITE_FUNCTION`, `SQLITE_PRAGMA` (read only PRAGMAs like `table_info`)
- Denied action codes: `SQLITE_INSERT`, `SQLITE_UPDATE`, `SQLITE_DELETE`, `SQLITE_CREATE_TABLE`, `SQLITE_DROP_TABLE`, `SQLITE_ALTER_TABLE`, `SQLITE_ATTACH`, `SQLITE_DETACH`

**API surface**:

| Function | File | Inputs | Outputs | Safety | Key errors |
|---|---|---|---|---|---|
| `connect_readonly` | `db/database.py` | `db_path: Path \| str` | `sqlite3.Connection` | Read only authorizer attached | File not found, permission denied |
| `check_ollama_status` | `services/llm_client.py` | None | `dict[str, Any]` (online: bool, model: str, error: str \| None) | Safe HTTP heartbeat with 1.5s timeout | Connection refused, timeout |
| `execute_tool` | `agent/copilot.py` | `tool_name: str`, `arguments: dict[str, Any]` | `dict[str, Any]` with success flag, friendly message, diagnostic details | Exception caught and structured | Unknown tool, parameter validation error, query failure |

**Value sourcing**:

| Action | Value produced / displayed | Source |
|---|---|---|
| Ollama health check | Online status and active model name | Ollama HTTP endpoint heartbeat in `services/llm_client.py` |
| Quick action trigger | Explicit user prompt bubble | Predefined action mapping in `ui/copilot_sidebar.py` |
| Read only tool query | Ledger rows and analytical aggregates | SQLite tables via `connect_readonly()` |
| Tool failure recovery | User facing remedial guidance | Structured tool error handler mapping |
| Tool technical diagnostic | Raw exception string and traceback summary | Caught exception in `execute_tool` |
| Empty dataset guidance | Navigation tip or suggested modal | Tool presence validation in `agent/tools.py` |
| Chat history state | Message bubbles with citations and diagnostics | Streamlit session state `copilot_history` |

**Key invariants**:
- The copilot never triggers inference or thread creation unless a user prompt is submitted or an action button is clicked.
- Any database connection used by copilot query tools rejects write and schema operations at the SQLite engine level.
- Tool errors never crash the Streamlit fragment or terminate the conversation turn.
- Clicking a quick action always posts an explicit user message bubble before running the assistant.

**Security model**:
- Zero trust database access: The SQLite C authorizer callback rejects all write operations at the engine level, protecting against prompt injection attacks that attempt to modify tables or execute malicious SQL.
- Local execution: All language model requests and tool computations remain on the local machine with no external telemetry.

**Configuration required**:
- None. Reuses existing settings in `config.py` (`DEFAULT_OLLAMA_URL`, `DEFAULT_MODEL`, `DB_PATH`).

**Critical test scenarios**:
- Happy path: User submits financial query, copilot queries read only database, formats figures and text without errors, verifies **AC-1**, **AC-3**.
- Failure case: Ollama daemon is offline when prompt is submitted, copilot displays friendly troubleshooting warning with `ollama serve` instructions, verifies **AC-2**.
- Security enforcement: Tool attempts an `INSERT` or `DROP` query on the read only connection, SQLite authorizer raises an authorization error, copilot catches it and returns friendly error, verifies **AC-3**, **AC-4**.
- Empty dataset handling: User asks for spending breakdown when transactions table is empty, tool returns friendly guidance suggesting statement import, verifies **AC-5**.
- Quick action transparency: User clicks Assess Risk, user message bubble appears in chat history before assistant answers, verifies **AC-6**.
- Parameter sanitization: Copilot tool is invoked with negative limits or string dates in invalid formats, tool rejects gracefully with explanatory message, verifies **AC-7**.

## Build plan

- [x] 1. Implement `connect_readonly()` with SQLite authorizer callback in `db/database.py`, and switch copilot query tools to use it, satisfies **AC-3**.
- [x] 2. Add `check_ollama_status()` in `services/llm_client.py` with fast heartbeat timeout, satisfies **AC-2**.
- [x] 3. Update `agent/copilot.py` `execute_tool()` to catch exceptions, format structured friendly guidance, and provide technical diagnostic details, satisfies **AC-4**.
- [x] 4. Sanitize parameters and add helpful empty dataset responses across financial tools in `agent/tools.py`, satisfies **AC-5**, **AC-7**.
- [x] 5. Update `ui/copilot_sidebar.py` to check Ollama health upfront, log explicit user bubbles on quick action clicks, and render collapsible troubleshooting detail cards for tool errors, satisfies **AC-1**, **AC-2**, **AC-4**, **AC-6**.
- [x] 6. Ensure background sync in `app.py` stays completely isolated from copilot state without toast or rerun noise, satisfies **AC-1**.
- [x] 7. Create comprehensive test suite in `tests/test_copilot_calming.py` validating on demand behavior, authorizer enforcement, error recovery, and parameter sanitization, satisfies **AC-1**, **AC-2**, **AC-3**, **AC-4**, **AC-5**, **AC-6**, **AC-7**.

## Consequences

**Positive**:
- Unprompted background runs and unwanted inference calls are completely eliminated.
- Database integrity is guaranteed by engine level authorizer rules even if an AI model hallucinates write queries.
- Users receive clear instructions when Ollama is offline rather than seeing broken UI fragments.
- Tool errors and empty states guide users toward resolving data gaps instead of leaving them stranded.

**Negative / tradeoffs**:
- Read only connections require separate connection handling from transactional repository write paths.
- Verifying Ollama status upfront adds a brief local network heartbeat check before starting a turn.

**Neutral**:
- Sidebar quick action clicks now leave a visible prompt in the chat history.

## Follow-up

- [ ] Check whether future custom plugins require extra allowed PRAGMAs in the read only authorizer.
