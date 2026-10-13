# Inbound data contracts and ingestion validation

Part of umbrella spec [0018](index.md). Build spec for one decision.

## Summary

This child puts a strict gate in front of the database. Every payload from Enable Banking (PSD2) and eToro is parsed through a typed Pydantic model before it becomes a `Raw*` object. A record that is missing a field or carries the wrong type never reaches storage: it is quarantined in `ingest_rejection`, the rest of the batch is written, and the user is warned.

## Requirements

**User stories**:

- As the owner, I want a provider payload change caught at the boundary, so it can never corrupt my ledger.

**Acceptance criteria**:

- **AC-1**: `connectors/schemas.py` defines a Pydantic v2 model for every PSD2 and eToro payload the connectors consume (accounts, balances, transactions, holdings, portfolio, cash). Connectors parse raw JSON through these models before mapping into the frozen `Raw*` dataclasses; no connector constructs a `Raw*` from an unvalidated dict.
- **AC-2**: On a validation error for a single record, the record is not persisted; a row is written to `ingest_rejection` keyed by `record_key`, carrying the field paths and error types (never the input value); the remaining valid records in the batch are persisted; the sync run status becomes `partial`.
- **AC-3**: A missing required field or an unusable value is caught at validation, never reaches the storage layer, and is surfaced through the Settings connector health panel and a message. Enable Banking sends amounts as decimal strings, so a decimal string is accepted and parsed to `Decimal` then minor units (aligned with the `Money` type from spec 0014); a float or non numeric amount is rejected.
- **AC-4**: Every endpoint call records whether its payload matched the expected schema (`connector_health.schema_match`), and a mismatch is logged at warning level with the connector and endpoint, with no amounts or PII in the line.
- **AC-5**: `pydantic` is added to `requirements.txt`, `install.ps1` installs it, and the existing connector and parser tests still pass.
- **AC-6**: Validation errors record field paths and error types only, never the offending input value, so a quarantined row cannot re leak a name or an amount.

## Decision

**Chosen option**: Pydantic v2 models at the connector boundary, mapping into the existing dataclasses.

**Implementation skills**: none yet.

## Design

**Surface**:

| Function | Where | Inputs | Outputs | Errors |
|---|---|---|---|---|
| `validate_payload` | `connectors/schemas.py` | raw dict, model class | validated model | `pydantic.ValidationError` |
| `quarantine` | `services/sync_service.py` | run id, connector, account, record key, error fields, error | `ingest_rejection` row | db error |

**Rules**:

- `extra="ignore"` on every model, so a provider adding a field never quarantines a valid record. A missing envelope key counts as a schema mismatch.
- Use strict typing where a silent coercion would hide a real provider change (currency, dates). Accept a decimal string for amounts and parse it, but reject a float or a non numeric value.
- Set `hide_input_in_errors=True` and store field paths plus error types in `error_fields`; never store the offending value.
- Map the validated model into the existing `Raw*` dataclass so downstream code is unchanged; the validation adds a gate, not a new pipeline.
- Quarantine is keyed by `record_key` (a hash of the record identity), so a repeated bad record upserts instead of growing the table; retention is 90 days.
- Persist ledger rows in one transaction per run per account; write the rejection and health rows in a separate commit so they survive a rollback.
- Counting: `records_fetched` is raw records received, `records_inserted` is rows actually inserted (`ON CONFLICT` no ops excluded), `records_rejected` is the rejection count. A batch level (envelope) failure is `error` with `schema_match=0`.

**Value sourcing**: `schema_match` comes from the Pydantic `model_validate` result; `ingest_rejection.error_fields` comes from the error location and type (never the input value); `records_rejected` is the count of `ingest_rejection` rows for the run.

**Invariants**: no unvalidated dict reaches persistence; a single bad record never aborts a batch.

## Build plan

1. Add `connectors/schemas.py` and `pydantic` to `requirements.txt` and `install.ps1`. Satisfies **AC-1**, **AC-5**
2. Wire the Enable Banking account, balance and transaction payloads through the gate, accepting decimal string amounts and rejecting float or non numeric. Satisfies **AC-1**, **AC-2**, **AC-3**
3. Add the `ingest_rejection` quarantine write (keyed by `record_key`, error fields only) and the `partial` run status. Satisfies **AC-2**, **AC-6**
4. Record `schema_match` per call and log a mismatch warning. Satisfies **AC-4**
5. Surface the quarantine count and the schema mismatch in the Settings health panel. Satisfies **AC-3**
6. Widen to eToro, market data and the file parsers. Satisfies **AC-1**

## Consequences

**Positive**: a provider change can no longer corrupt the ledger; bad records are visible and inspectable.

**Negative / tradeoffs**: one schema per payload to maintain; some legitimate provider changes will now surface as quarantines until the schema is updated.

**Neutral**: `pydantic` becomes a new runtime dependency.

## Follow-up

- [ ] Consider a repair action to re replay quarantined records after a schema update.
