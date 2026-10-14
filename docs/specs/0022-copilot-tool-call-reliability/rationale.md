# 0022 · Rationale

Decision record for spec 0022 · Copilot tool call reliability and grounded answers.

## Context

Forces from a live demo pass:

- `agent/copilot.py` (SYSTEM_PROMPT) tells the model to pass a period as `date_scope` to the spending and cashflow tools. `tool_get_spending_forecast` (`agent/tools/spending.py`) takes no arguments, and its schema correctly declares none, so the model over generalizes the prompt and passes `date_scope` anyway.
- `execute_tool` (`agent/copilot.py`) refuses any argument a tool does not declare (the AC-16 guard) and returns `UnknownArgumentError`. A refused call sets `had_failure`, which suppresses the turn's navigation intent, so the promised page never opens and the sidebar shows a diagnostics expander.
- With no data tool result to ground on, the model can still answer with invented amounts. A portfolio prompt returned a generic Stocks 45 and Bonds 30 split that no tool produced. The prompt rule "never estimate or invent amounts" is unenforced.
- `tool_get_net_worth_history` (`agent/tools/insights.py`) is approximate by design (the running ledger cash balance plus the current invested value held flat), so it reads far below the true net worth from `get_current_net_worth`. Shown next to the dashboard it looks like an error.

Consequence of not deciding: everyday period questions fail, the page and the chat disagree, and the user cannot trust the figures.

## Options considered

### Option 1: Fix in place, align all three sides, add a grounding gate (chosen)

Add the missing `date_scope` parameters, make the prompt name the accepted arguments per tool, have the dispatcher ignore only the benign `date_scope`, decouple navigation from data failure, gate the final answer, and make the net worth trend honest.

**Pros**:
- Small, no schema change, removes the failure, keeps the strict guard for real mistakes.

**Cons**:
- The prompt and the tool signatures must stay in sync; a future tool needs the same care.

### Option 2: Dispatcher tolerance only

Silently drop an unknown `date_scope`, change nothing else.

**Pros**:
- Smallest possible change.

**Cons**:
- Leaves the prompt misleading, other tools still fail, and the forecast never honors a period.

### Option 3: Model self correction

Return the argument error to the model and let it retry.

**Pros**:
- General across tools.

**Cons**:
- Relies on the weak 7b model to fix its own call, adds a slower second round trip, and is non deterministic.

### Option 4: Replace the summarizer

Build the answer from tool results in code.

**Pros**:
- Fully grounded by construction.

**Cons**:
- Large change, loses the conversational answer, out of proportion to the bug.

## Rationale

The failure is a contract mismatch the model cannot see. The prompt tells it every spending tool takes a period, the schema tells it one does not, so it guesses the prompt. Fixing only one side leaves the other wrong, which rules out Option 2. Naming the accepted arguments in the prompt and tolerating the single benign hint in the dispatcher makes the failure impossible while keeping the strict guard that catches real mistakes, without the slow non deterministic retry of Option 3. Grounding is added as a deterministic gate rather than a stronger prompt because a rule the 7b model already ignores is not a control. Navigation is decoupled because a failed number lookup should not also lose the page. Option 4 is more robust but disproportionate to a bug that a gate closes.
