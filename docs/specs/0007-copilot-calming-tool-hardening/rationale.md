# 0007. Copilot Calming & Tool Hardening (Rationale)

## Context

The local Copilot assistant sidebar was designed to provide interactive financial guidance, answering questions about cash flow, investments, Dutch tax rules, and mortgage optimization. However, several operational and stability gaps have emerged during development.

First, background activity and assistant triggering lack strict boundaries. When the application loads or background sync tasks execute, there is a risk of unprompted model calls, unneeded token polling, or unexpected rerun noise. Users expect the copilot to be a quiet assistant that speaks only when spoken to, keeping background automation completely silent.

Second, connection failures to local Ollama are handled late in the execution pipeline. If the Ollama server is offline or not serving the expected model, the assistant thread launches, encounters a connection error deep within the stream generator, and renders a generic error message in the chat history. Checking availability upfront provides a much cleaner experience, advising the user to start Ollama before launching a thread.

Third, query tool safety and error handling need hardening. Although documentation and architectural principles specify a zero trust read only SQLite authorizer, connection routines currently lack explicit engine level authorizer callbacks. If an adversarial or hallucinated prompt attempts a write operation, application layer parsing is insufficient to prevent ledger corruption. Furthermore, when tools encounter empty datasets (such as a fresh database with no accounts or transactions) or query exceptions, they return unhelpful generic messages. Hardening tools with engine level authorizers, parameter sanitization, and structured diagnostic cards ensures robust recovery.

## Options considered

### Option 1: On demand activation with engine level read only authorizer, upfront Ollama health verification, and structured tool diagnostics

The copilot initiates work strictly upon user submission or explicit quick action click. Ollama availability is checked with a fast heartbeat before starting background worker threads. A dedicated `connect_readonly()` connection attaches an SQLite C authorizer callback that rejects all write operations at the engine level. Tools catch exceptions gracefully, returning user friendly guidance with collapsible technical diagnostics and actionable hints for empty datasets.

**Pros**:
- Guarantees complete database safety at the SQLite engine level.
- Prevents wasted background threads and cryptic crashes when Ollama is offline.
- Turns tool errors into clear troubleshooting steps that guide the user.
- Keeps background sync completely silent and decoupled from the assistant.

**Cons**:
- Requires maintaining a dedicated read only connection factory alongside standard connection helpers.

### Option 2: Application layer regex query filtering with lazy error handling

Inspect SQL queries using regular expressions or keyword matching before execution. Catch Ollama connection errors only after worker threads are launched.

**Pros**:
- Requires fewer modifications to database connection routines.

**Cons**:
- Regular expression SQL parsing is notoriously brittle and vulnerable to bypass techniques like comments and subqueries.
- Launching worker threads before checking Ollama connection causes UI flicker and delayed error messages.
- Does not address empty dataset confusion.

### Option 3: Static assistant mode with precomputed answers

Disable live database queries entirely from the LLM, restricting the assistant to static financial knowledge base queries and documentation lookups.

**Pros**:
- Eliminates any risk of database writes.

**Cons**:
- Destroys core value of the copilot, preventing users from asking questions about their actual net worth, cash flows, and investments.

## Rationale

Option 1 is selected because it establishes defense in depth while delivering a calm, predictable user experience. Attaching an SQLite authorizer directly to the database connection via `set_authorizer` ensures that no SQL statement executed by the copilot can perform an `INSERT`, `UPDATE`, `DELETE`, `DROP`, or schema modification, regardless of what the language model generates.

Verifying Ollama availability with an upfront heartbeat allows the sidebar to inform users immediately if `ollama serve` is not running, avoiding unnecessary thread spawning and confusing timeouts. Providing structured troubleshooting information and contextual hints when data is empty turns common setup friction into self service onboarding. Keeping background synchronization silent ensures that the copilot remains an unobtrusive, on demand partner.
