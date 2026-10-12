# 0014 Rationale

## Context

After 12 slices the repo has 93 Python files and about 22 thousand lines, and all 202 tests pass in 61 seconds. Agents now fail at small edits because the patterns they need have no single home:
- 110 hand written `/ 100` conversions (most in mortgage, budget service, dialogs, spending, holding repository and models). Each one is a chance for a cents versus euros bug, and slices 2 and 8 already shipped fixes for exactly that.
- 48 `except Exception: pass` blocks (legal vault, market data, tools, file detection, dashboard) hide failures, so agents and users cannot see why a number is missing.
- Three files over 1000 lines (`agent/tools.py` 1355, `ui/charts.py` 1040, `ui/pages/investments.py` 1005) overflow an agent's working view, which invites partial edits.
- 139 raw `st.session_state` accesses with string keys spread over 10 files invite typo bugs and key collisions.

The owner also needs the app to look good in screenshots for a product leadership job search, without exposing real financial data.

### Evidence snapshot (2026-10-12)
| Smell | Count | Top files |
|---|---|---|
| `/ 100` | 110 | mortgage 12, budget_service 10, dialogs 10, spending 10 |
| silent `except` | 48 | legal_vault 7, market_data 5, tools 4, detect 4 |
| `st.session_state` | 139 | copilot_sidebar 37, dialogs 21, app 17, settings 17 |
| `print(` | 9 | etoro_service 7, llm_client 2 |

## Options considered

### Option 1: Big bang rewrite into layered packages
Restructure everything at once into domain packages. **Pros**: the cleanest end state. **Cons**: a huge risk against only 202 tests, a long broken window, and exactly the work agents already fail at.

### Option 2: Fix in place along shared seams, strangler per seam (chosen)
Add `Money`, `ui/state.py`, logging and the demo config as new seams, prove them on one page, then migrate callers step by step and split files behind unchanged import paths. **Pros**: every step is small, revertible and testable, and public imports stay stable. **Cons**: mixed patterns exist until step 9, and the diff is long.

### Option 3: Lint and guard only
Add ruff, pyright and architecture tests, and leave the code as is. **Pros**: cheap. **Cons**: guards fail on day one with nothing fixing the cause. That doesn't help the owner's goal.

## Rationale

The pain is "no single home" for money, state and errors, plus files too large for an agent to hold. Option 2 creates those homes, which fixes the root cause rather than the symptoms. The strangler approach fits the Tracer Bullet project default and the thin safety net: each step either keeps the suite green or reverts cleanly. A frozen `Money` dataclass was chosen over bare helpers because the type itself documents intent and catches currency mismatches. It was chosen over Decimal everywhere because the database already stores int cents. Demo mode uses a separate database file rather than a runtime toggle, so real data cannot leak into screenshots by construction.
