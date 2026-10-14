# 0022 · Copilot tool call reliability and grounded answers

**Date**: 2026-10-14
**Status**: In Progress

## Summary

The local Copilot sometimes fails or misleads. When you ask about spending for a period, it hands a period hint (`date_scope`) to a tool that does not accept it, the call is refused, and the page it promised to open never does. Other times it states portfolio numbers that no tool returned. This spec makes the period hint safe, opens the right page even when a data tool fails, and stops the assistant from stating amounts it did not read from your ledger. It also makes the net worth trend say plainly what it does and does not cover.

## Requirements

**User stories**:
- As the user, I want a period question to just work, so I get the answer and the page I asked for.
- As the user, I want the assistant to never state a figure it did not read from my ledger.
- As the user, I want the net worth trend to say what it covers.

**Acceptance criteria**:
- **AC-1**: `get_spending_forecast` accepts a `date_scope` argument and computes its burn rate and projected month end for the requested window; with no scope it keeps the current three month trailing behavior. Its schema declares `date_scope`.
- **AC-2**: The system prompt names exactly which tools accept `date_scope` and states that a period must never be passed to a tool that does not list it.
- **AC-3**: When the model passes `date_scope` to a tool that does not declare it, the dispatcher drops that one argument, runs the tool, and records a warning diagnostic; the turn is not marked failed. Every other undeclared argument still returns the guided `UnknownArgumentError` (the AC-16 guard is preserved).
- **AC-4**: A turn's navigation intent is emitted independent of data tool success, so the topic's page still opens when a data tool fails; the date scope is attached only when it resolves. The deterministic topic map fallback runs the same way.
- **AC-5**: When no data tool succeeds in a turn and the drafted answer contains a money amount or a percentage, the final answer is replaced by a deterministic message built from the tool failure guidance (or, with no failure, a plain "could not retrieve the numbers" message), so no invented figure reaches the user.
- **AC-6**: `get_net_worth_history` headline and message state that the series is the ledger cash balance plus the current invested value, excludes home equity and opening balances, and point to `get_current_net_worth` for the true current figure; the Copilot repeats that scope.
- **AC-7**: A regression test suite covers the dropped argument path, navigation on a failed turn, the grounding gate, and the net worth wording, and all existing Copilot tests stay green.

## Decision

**Chosen option**: Option 1: Fix in place, align all three sides, add a deterministic grounding gate.

Make the period hint safe (add `date_scope` where it belongs, name it in the prompt, tolerate it in the dispatcher), keep navigation alive across a failed data tool, gate the final answer against invented figures, and make the net worth trend honest about its scope.

**Implementation skills**: `developing-with-streamlit` (`streamlit/agent-skills`, `.agents/skills/developing-with-streamlit/`)

## Feature design

**Data model sketch**: none. No schema change; every change is in the `agent/` and `ui/` code paths.

**State transitions** (a Copilot turn):
`user message` -> (`fast path` | `model tool calls`) -> `tool results` -> `grounding gate` -> `final stream + navigation intent`. The gate is the new step between tool results and the final stream.

**API surface**:

| Surface | Kind | Key inputs | Key outputs | Auth | Key errors |
|---|---|---|---|---|---|
| `tool_get_spending_forecast` | function | `date_scope: any` (optional) | burn rate, projected month end, message | read only conn | invalid scope message |
| `execute_tool` | dispatcher | `tool_name`, `arguments` | tool result; drops a benign `date_scope` | n/a | `UnknownArgumentError` for other unknowns |
| `SYSTEM_PROMPT` | prompt | today | per tool argument lists | n/a | n/a |
| grounding gate | turn step | tool results, drafted answer | grounded answer or deterministic fallback | n/a | n/a |
| navigation emit | turn step | captured intent | `ui_intent` (independent of failure) | n/a | n/a |

**Value sourcing**:

| Action | Value produced / displayed | Source |
|---|---|---|
| forecast | burn rate, projected month end | ledger aggregate over the resolved window (`services/date_scope.py`) or the trailing three months |
| dispatcher | which argument to drop | the tool signature (`inspect.signature`) |
| grounding gate | did a data tool succeed | the turn's tool results (`success` on data tools) |
| grounding gate | does the answer contain money or percent | regex over the drafted text |
| fallback message | what went wrong | the failed tool `message` or `guidance`, else a fixed string |
| navigation | page and tab | `open_view`, the fast path, or the topic map |
| navigation | date scope | `resolve_date_scope`, attached only when resolved |

**Key invariants**:
- A turn never fails solely because `date_scope` was passed to a tool that does not declare it.
- No money or percentage figure appears in a final answer unless a data tool succeeded in that turn.
- The topic's page opens even when a data tool fails.
- Undeclared arguments other than `date_scope` still return the guided error (the AC-16 guard holds).

**Security model**: unchanged. Data tools stay read only through the SQLite authorizer, and writes stay confirm gated. The grounding gate changes no access.

**Configuration required**: none.

**Critical test scenarios**:
- Happy path: "Show my spending for the past 3 months." resolves the scope, the forecast runs, the Spending page opens with the scope and the chart panel, verifies **AC-1**, **AC-4**.
- Failure case: a tool receives `date_scope` it does not declare; the argument is dropped, the tool runs, the turn is not marked failed, verifies **AC-3**.
- Grounding: a turn where only `open_view` succeeds and the draft states a figure; the answer is replaced, verifies **AC-5**.
- Net worth: the trend answer states cash plus invested and excludes home equity, verifies **AC-6**.

## Build plan

Tracer Bullet: stand up one question end to end first (spending for a period: prompt, forecast, navigation), then thicken.

1. [x] Add `date_scope` to `tool_get_spending_forecast`, resolve it with `services/date_scope.py`, window the burn and projection query, and update its schema entry, satisfies **AC-1**
2. [x] Rewrite the SYSTEM_PROMPT period guidance to name each tool that accepts `date_scope` and forbid a period on the others, satisfies **AC-2**
3. [x] Add dispatcher tolerance: drop an unknown `date_scope`, run the tool, record a warning diagnostic; keep the strict error for any other unknown argument, satisfies **AC-3**
4. [x] Decouple navigation from data failure: emit `ui_intent` regardless of failure, run the topic map fallback regardless, attach scope only when resolved, satisfies **AC-4**
5. [x] Add the grounding gate before the final stream, satisfies **AC-5**
6. [x] Make the net worth trend wording explicit and have the prompt repeat it, satisfies **AC-6**
7. [x] Tests: dropped argument, navigation on a failed turn, grounding replacement, net worth wording; keep the suite green, satisfies **AC-7**

## Consequences

**Positive**:
- Everyday period questions work end to end, and the page and the chat agree.
- Invented figures cannot reach the user.
- The trust gap on the net worth trend closes.

**Negative / tradeoffs**:
- The prompt and the tool signatures must stay in sync, a standing maintenance tax.
- The grounding gate can replace a legitimate answer if the "data tool" set is misclassified, so that set needs care.
- A dropped `date_scope` is silent to the user by design (only a warning diagnostic), which can hide a recurring model habit.

**Neutral**:
- No schema change and no new dependency; one more deterministic step in the turn pipeline.

## Follow-up

- [ ] Overlaps the deferred "Copilot phrasing robustness" item from spec 0016; a wording test set for allocation requests belongs there.
- [ ] Consider a small wording regression set that asks each data tool for a period and asserts a successful call.
- [ ] This spec is not on the scope; enroll a scope feature or keep its build tasks in `## Build plan`.

## Migration plan

**Strategy**: no migration needed (code only, no schema change).
**Phases**:
1. Ship the argument alignment and the navigation decoupling.
2. Ship the grounding gate and the net worth wording.
**Rollback**: revert the commit; no data is transformed.
**Risks**: the prompt change could shift tool selection for other questions, so re check a few representative prompts.
