# Memory recycling on heavy pages

Part of umbrella spec [0018](index.md). Build spec for one decision.

> **Deferred.** This child is not part of the active build. Measure resident memory across a long session first, and only then decide whether to add `gc.collect()`. The AC-3 test is a weak proxy (`gc.collect()` counts unreachable objects, not memory), so treat it as a placeholder until a real measurement exists.

## Summary

Large historical DataFrames plus a running local model make Streamlit sessions grow. This child adds targeted garbage collection after the heavy render fragments and after a page switch, and releases large frame temporaries before the next heavy computation. It is deliberately small: no cache size caps and no aggressive per account eviction, because those add recomputation cost for a symptom that has not been measured.

## Requirements

**User stories**:

- As the owner, I want long sessions to stay light, so switching accounts and pages for an hour does not bloat memory.

**Acceptance criteria**:

- **AC-1**: `gc.collect()` runs after the heavy render fragments (dashboard, spending, investments) and after a page switch.
- **AC-2**: Large intermediate DataFrames in the hot page paths are explicitly released (`del`) before the next heavy computation.
- **AC-3**: A test drives repeated page and account switches and asserts that `gc.collect()` after each switch returns the tracked object count to within a small bound of the baseline, so memory does not climb monotonically.

## Decision

**Chosen option**: targeted garbage collection and frame release only; the engineer explicitly declined cache size caps and per account eviction as premature.

**Implementation skills**: none yet.

## Design

**Rules**:

- Call `gc.collect()` only after a heavy fragment or a detected page switch, never on every rerun (that would add latency to every interaction).
- Release large frame locals with `del` once a fragment has rendered.
- Leave the existing Streamlit TTL caches as they are; do not add `max_entries`.

**Value sourcing**: the freed object count is the return of `gc.collect()`; the page switch is detected from the existing navigation state.

**Invariants**: garbage collection never runs on a plain rerun; no caching behavior changes.

## Build plan

1. Add `gc.collect()` after the dashboard, spending and investments fragments. Satisfies **AC-1**
2. Release large frame temporaries in those fragments. Satisfies **AC-2**
3. Add the switch loop test with the object count bound. Satisfies **AC-3**

## Consequences

**Positive**: heavy pages release memory after render; long sessions stay lighter at low cost.

**Negative / tradeoffs**: targeted only, so a genuinely large session may still grow; a mis sized `gc.collect()` adds a few milliseconds to heavy renders.

**Neutral**: no change to cache behavior.

## Follow-up

- [ ] Optional later: measure resident memory under a long session and add cache caps only if the data shows a real ceiling is being hit.
