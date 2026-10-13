# Connector resilience, sync runs and synthetic SLAs

Part of umbrella spec [0018](index.md). Build spec for one decision.

## Summary

External APIs fail. This child makes every ingestion resilient and every run visible. Transient network and rate limit failures retry with backoff; each run writes a `sync_run` row and each endpoint call writes a `connector_health` row; and the Settings page shows a Connector health panel with freshness, latency and schema match, so degradation and staleness are seen instead of guessed. The app stays fully usable on cached local data while a provider is down.

## Requirements

**User stories**:

- As the owner, I want a flaky provider to retry quietly, so a temporary blip does not need my attention.
- As the owner, I want to see each connector's health and freshness, so I know when to trust the numbers.

**Acceptance criteria**:

- **AC-1**: A shared `connectors/retry.py` retries transient failures (timeout, connection error, HTTP 429, HTTP 5xx) up to 3 attempts with exponential backoff (base 0.5s, factor 2, jitter), honoring a `Retry-After` header when present, and a whole run has a total wall time budget (`PFA_RUN_BUDGET_SECONDS`). It never retries HTTP 401, and treats HTTP 403 as retryable only for token or session errors (otherwise `error`).
- **AC-2**: Each ingestion invocation writes exactly one `sync_run` row per (connector, account) (account null for account less connectors such as market data), carrying start and finish time, status, and the fetched, inserted and rejected counts (fetched is raw records, inserted excludes `ON CONFLICT` no ops). Status starts `running` and finishes `ok`, `partial`, `error` or `needs_reauth`, with precedence `needs_reauth` > `error` > `partial` > `ok`.
- **AC-3**: Each external endpoint call writes one `connector_health` row per logical call (ok, latency in ms, http status, schema match, attempts, checked at), linked to its run; a paginated call writes one row per page.
- **AC-4**: The Settings page shows a Connector health panel listing, per connector, the last successful sync (the last `ok` or `partial` run, taking the worst account), its age, the current status, and the average latency and schema match rate over the last 50 calls or 7 days; a connector older than `PFA_SYNC_STALE_HOURS` is marked stale, and "never synced" when no run exists.
- **AC-5**: When the network is unavailable or an API returns an auth or rate limit error, every page still renders from the last synced local data, no page raises, and the health panel shows the stale or error state.
- **AC-6**: `needs_reauth` is recorded distinctly from a generic error, so the user knows to reconnect credentials rather than just retry.
- **AC-7**: `sync_run`, `connector_health` and `ingest_rejection` are pruned to `PFA_HEALTH_RETENTION_DAYS` (default 90), and a run left `running` past 15 minutes is swept to `error` at startup.

## Decision

**Chosen option**: bounded retries with backoff plus the `sync_run` and `connector_health` tables and a Settings health panel, reusing the existing `sync_log` failure handling.

**Implementation skills**: none yet.

## Design

**Data**: uses the shared `sync_run` and `connector_health` tables from [index.md](index.md#feature-design).

**Surface**:

| Function | Where | Inputs | Outputs | Errors |
|---|---|---|---|---|
| `with_retry` | `connectors/retry.py` | callable, attempts, base delay | response | raises the last error |
| `start_run` / `finish_run` | `services/sync_service.py` | connector, account | `sync_run.id` | db error |
| `record_health` | `services/sync_service.py` | run id, endpoint, ok, latency, http status, schema match, attempts | `connector_health.id` | db error |

**Status mapping**: precedence `needs_reauth` > `error` > `partial` > `ok`. `partial` when some records were rejected and others persisted; `error` on an unhandled failure or when all records were rejected with none inserted; `needs_reauth` on a token or session HTTP 401 or 403, which keeps the counts already persisted.

**Retry rule**: retry only idempotent reads (the sync calls are reads), honor a `Retry-After` header, and stop when the run budget `PFA_RUN_BUDGET_SECONDS` is spent. `connector_health.latency_ms` is the final attempt only and `attempts` counts them; `schema_match` is null when no body arrived.

**sync_log**: the existing `sync_log` has a status check that likely excludes `partial`, so dual write it (mapping `partial` to `ok`) with a redacted message until it is retired.

**Offline behavior**: the UI never blocks on a live call; it reads SQLite, which already holds the last good data. The health panel is the only place the failure is shown.

**Value sourcing**: freshness is `now` minus the last `ok` or `partial` `sync_run.started_at` (worst account), in UTC ISO 8601; the stale threshold is `PFA_SYNC_STALE_HOURS`; average latency and schema match rate are aggregates over `connector_health` for the last 50 calls or 7 days.

**Invariants**: exactly one active `sync_run` per (connector, account); every `connector_health` row links to a run; a run left `running` past 15 minutes is swept to `error` on next startup.

## Build plan

1. Add `connectors/retry.py` and route Enable Banking calls through it. Satisfies **AC-1**
2. Add the `sync_run` and `connector_health` tables (migration) and the `start_run`, `finish_run` and `record_health` writers. Satisfies **AC-2**, **AC-3**
3. Map the status outcomes, including the distinct `needs_reauth`. Satisfies **AC-6**
4. Add the Settings Connector health panel with freshness, status, latency and schema match, and the stale flag. Satisfies **AC-4**
5. Confirm offline rendering on every page with the network down, and surface the stale state. Satisfies **AC-5**
6. Add retention pruning for `sync_run`, `connector_health` and `ingest_rejection`, the startup stuck run sweep, and the redacted `sync_log` dual write. Satisfies **AC-7**

## Consequences

**Positive**: transient failures self heal; every run is measurable; degradation and staleness are visible.

**Negative / tradeoffs**: retries add up to about 10 seconds of latency on a failing call; the health panel adds a new read path and a small aggregate query cost.

**Neutral**: `sync_log` stays for backward compatibility with a redacted dual write until it is retired; `sync_run` and `connector_health` become the source of truth for health.

## Follow-up

- [ ] Optional later: a circuit breaker if a provider degrades repeatedly.
