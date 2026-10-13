# Lineage, redacted logging and zero leak context

Part of umbrella spec [0018](index.md). Build spec for one decision.

## Summary

Every ledger row should say where it came from, and nothing sensitive should reach a log or a chat history that outlives its purpose. This child adds provenance, source file and run link columns to transactions and holdings, a logging filter that masks amounts, IBANs and counterparty names, an optional JSON log format, and the rule that the copilot keeps prompt content in memory only and clears it when values are hidden or the user clears the chat.

## Requirements

**User stories**:

- As the owner, I want to know where a row came from, so I can trust and audit the ledger.
- As the owner, I want no amounts or names in my logs, and no prompt content written to disk.

**Acceptance criteria**:

- **AC-1**: `transactions` gains `provenance`, `source_file` (the basename only) and `sync_run_id`; `holdings` gains `provenance` and `sync_run_id` (reflecting the last writer). Provenance values come from one constants module (`psd2_api`, `etoro_portfolio`, `csv_import`, `manual`, `demo`, `legacy`); environment is separate from identity. Every new write populates provenance, connector writes also set `sync_run_id`, and rows written before this upgrade are backfilled to `legacy`.
- **AC-2**: A logging filter runs after `getMessage()`, clears `args`, scrubs `exc_text`, and masks IBAN patterns, bearer token and JWT patterns, and values attached to sensitive keys (amount, balance, iban, counterparty, merchant, name). It is attached to every handler including the console, and call sites pass sensitive values only through `extra=`.
- **AC-3**: Logging keeps the stdlib rotating file handler and gains an optional JSON formatter (`PFA_LOG_FORMAT=json`), and captures ingestion tracebacks and database failures at the right level.
- **AC-4**: The copilot writes no prompt or tool result to any temp file, log or model weight; in memory history is cleared when values are hidden and on an explicit Clear chat, and no chat content is persisted to disk.
- **AC-5**: `imported_at` remains the ingestion timestamp; provenance and `source_file` answer where the row came from.

## Decision

**Chosen option**: provenance and run link columns, a redaction logging filter, an optional JSON format, and in memory only copilot history with a clear on hide and on Clear chat.

**Implementation skills**: none yet. Spec 0014 already owns the logging setup, so this child extends `logging_setup.py` rather than replacing it.

## Design

**Data**: uses the shared provenance columns and `sync_run_id` from [index.md](index.md#feature-design).

**Surface**:

| Piece | Where | Inputs | Outputs |
|---|---|---|---|
| `RedactionFilter` | `logging_setup.py` | a log record | a record with sensitive values masked |
| json formatter | `logging_setup.py` | `PFA_LOG_FORMAT` | structured or text line |
| `Provenance` constants | `services/provenance.py` | none | the enum of provenance values |
| provenance stamping | `services/sync_service.py`, `connectors/file_import/` | connection identity from the module, file name | `provenance`, `source_file` (basename), `sync_run_id` on the row |
| `clear_history` | `ui/copilot_sidebar.py` | privacy toggle, Clear chat | emptied session history |

**Redaction approach**: implement a `logging.Filter` that rewrites `record.msg` from `getMessage()`, clears `record.args` and `record.exc_text`, and masks IBAN, bearer and JWT patterns plus values bound to sensitive keys; keep the key name so the line stays diagnostic. Attach it to the file and console handlers. A call site passes sensitive values only through `extra=`.

**Context rule**: the copilot keeps the in memory history during a session (so a conversation works), but clears it whenever values are hidden and on Clear chat. It never writes prompts or tool results to disk. Purging the whole history on every page switch is deliberately not done, because it would make the assistant unable to hold a conversation across pages; hiding values is the real privacy trigger.

**Value sourcing**: provenance is a constant from the provenance module; `source_file` is the basename of the imported file; log safety is the filter output.

**Invariants**: no amount, IBAN or counterparty name in any log; no chat content on disk; old rows carry `provenance = legacy` until the backfill runs.

## Build plan

1. Add `services/provenance.py`, the provenance, `source_file` and `sync_run_id` columns, stamp them on every write path, and backfill existing rows to `legacy`. Satisfies **AC-1**, **AC-5**
2. Add the `RedactionFilter` (post `getMessage`, clear args, scrub `exc_text`, IBAN, bearer and JWT patterns) and attach it to every handler including the console. Satisfies **AC-2**
3. Add the optional JSON formatter and route ingestion and database failures through the logger. Satisfies **AC-3**
4. Clear the copilot history on hide values and on Clear chat, and confirm nothing is persisted. Satisfies **AC-4**

## Consequences

**Positive**: the ledger is attributable and auditable; logs and chat leave no sensitive residue.

**Negative / tradeoffs**: redaction can over mask and hide a value that is useful for debugging; JSON logs are less readable by eye.

**Neutral**: extends the logging setup owned by spec 0014 without replacing it.

## Follow-up

- [ ] `/sync`: record the redaction and provenance conventions in the relevant `AGENTS.md` files.
