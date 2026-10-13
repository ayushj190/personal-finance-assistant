# 0017 rationale. Copilot action layer and daily use release polish

Decision record for [index.md](index.md). Builders do not need this file.

## Context

The app is close to finished. Every page exists, the local Ollama Copilot answers financial questions through deterministic tools, and the read only SQL guard keeps the model away from writes. What is missing is the bridge between the two: the Copilot's knowledge and the app's screens. A user who asks about their spending still has to find the Spending tab and set the period by hand. The assistant is smart but it has no hands.

The second force is release readiness. A hands on audit (`docs/reviews/2026-10-12-ui-ux-audit.md`) found that with Hide values on the app is close to unusable, because the mask blanks tickers, merchant names, and every percentage, and it blanks chart axes so the charts say nothing. The same audit found Streamlit calls that are past their removal date (`use_container_width`, `st.components.v1.html`), so the next framework upgrade breaks most pages at once. These are small fixes with an outsized effect on first impressions, and they gate usable screenshots for a portfolio.

A third force is the honest one: this is a personal project meant to be used daily and shown publicly. Effort should go to the few changes a user feels (the Copilot driving the app) and the few defects a visitor sees first (masks, warnings, README drift), not to new subsystems.

Streamlit 1.65 is installed, and the two primitives the action layer needs already exist and are stable public APIs: `st.switch_page` for changing the page, and `st.tabs(default=...)` for selecting a tab. Before this was confirmed, the risk was that tab selection had no supported path; it does.

## Options considered

### Option 1: One thin action layer (chosen)

Add a single validated `open_view` tool to the Copilot, plus a deterministic fast path for explicit navigation phrasing. Together they resolve the request into a page, an optional tab, and an optional date scope, and write a one time intent that crosses from the worker thread on the task object to session state at turn completion. The app consumes the intent once after `st.navigation`, forwards it to `st.switch_page` and `st.tabs(default=...)`, and writes the scope into the filter state. The data tools gain the same optional date scope so the answer and the page share one resolved range. Polish rides along as fix in place.

**Pros**:
- Smallest change that closes the gap: one tool, one instant fast path, one consumption point, one shared resolver, no new dependency, no schema change.
- One date resolver means the chat number and the page range agree by construction, which also fixes the "last month" misread at its root (basis: single source of truth, already the project's pattern in spec 0009).
- The fast path makes explicit navigation instant and reliable, so the most demoable interactions do not depend on a 7B model or a 30 to 60 second turn.
- Keeps the existing read only SQL rule and the deterministic tool pattern, so the security model does not change.
- Reuses each page's own tested charts, so no second chart system to keep aligned.

**Cons**:
- Depends on `st.switch_page` and `st.tabs(default=...)` continuing to exist, plus a remount workaround for tab selection; a future major Streamlit change could break it (though both are stable public APIs, unlike generated CSS selectors).
- A 7B model can still pick a valid but wrong destination on a vague or combined prompt, which is why the destination is explicit in the tool and the fast path, and unclear cases ask (AC-6).

### Option 2: Per page tools plus a Copilot results panel

Give the Copilot one tool per page, and add a dedicated Copilot results panel pinned to the top of each page carrying exactly the chart the model built.

**Pros**:
- More explicit tool names can help a small model route.

**Cons**:
- Grows the tool list sharply, and spec 0016 already trimmed tools because selection accuracy degrades with count.
- A second chart system on the page duplicates the page's own charts and drifts from them over time.
- More surface to test, for a result no better than reusing the page's charts.

### Option 3: Infer navigation from the data tool used

No `open_view` tool. The app watches which data tool the model called and navigates there.

**Pros**:
- No new tool at all, so no schema growth.

**Cons**:
- Implicit and hard to predict; a question that reads two kinds of data has no single obvious destination.
- The user cannot ask to "just open the spending page" without also making a data query.
- The mapping from tool to page lives in the app, invisible to the model, which makes the behavior hard to reason about and test.

### Option 4: Deterministic router as the only mechanism

No model path for navigation at all. A code side matcher on the page and tab names handles every navigation request, and the model only answers.

**Pros**:
- Instant and perfectly reliable for the phrasing it covers.
- No new tool, so no schema growth and no model selection risk.

**Cons**:
- Covers only exact phrasing; "how am I doing this quarter" or "where did my money go" cannot be routed without the model.
- The combined case (navigate and answer) still needs the model for the answer, so the router does not remove the model from the turn.

### Option 5: Rewrite the app as one page with URL driven sections

Fold every page into a single scroll page whose sections are shown by a query parameter, and let the Copilot set the parameter.

**Pros**:
- A single navigation mechanism, and deep links become trivial.

**Cons**:
- A large rewrite of a working app, exactly the big bang pattern the project avoids.
- Loses the tested per page structure and the `st.navigation` model that already works.
- No user felt problem it solves that Option 1 does not.

## Rationale

Option 1 wins because the missing piece is thin. The app already has the pages, the charts, the filters, and a strong tool pattern; it lacks only a way for the assistant to point at them. One tool plus one consumption point adds that without touching the parts that already work (basis: enhancement mode, fix in place, strangler instinct). It keeps the security model intact, since the only new power the model gains is naming a page, a tab, and a date scope from a whitelist, never a write and never SQL.

Option 2 was rejected mainly on the chart decision: the user asked for the page to show relevant charts, and the page already has them. Reusing them means the chart always matches the page and there is one chart system, not two. Option 3 was rejected because the destination is a user intent, not a side effect of a data query; making it explicit and visible to the model is both easier to test and easier to reason about with a small model. Option 4, the router alone, was rejected as too narrow: it cannot reach the fuzzy requests that are the point of having an assistant at all, and it still leaves the model in the turn for the answer. Option 4's engine was, however, adopted as a fast path inside Option 1, because it makes the explicit interactions instant and takes the biggest reliability risk off the 7B model. Option 5 is a rewrite with no proportional benefit.

An independent cross check of the first draft changed several details, all folded in: the intent must cross the thread boundary on the task object rather than through a direct session state write from the worker (the existing `figure` and `form_request` pattern), consumption must sit after `st.navigation` and pop before `st.switch_page`, Dashboard has no date filter so it joins the no scope group, the Spending View Scope needs its own mapping from a range, "last month" is ambiguous between the calendar and the fiscal month so the resolver owns it, the filter widget needs persistent state rather than a key plus `index=`, tab selection needs a remount, and the answering and page paths must share one turn scope so a small model cannot split them.

The shared date resolver is the load bearing detail. The audit item about "last month" (2.9) and the requirement that the answer and the page agree are the same problem, and one resolver fed by both the chat path and the page filter is the only version that stays correct as the code changes (basis: the project's existing single source of truth pattern, spec 0009).

On masking, the engineer chose to replace the rule spec 0016 recorded. 0016 masked money and personal percentages and blanked charts; the audit showed that made the app unreadable with Hide values on. Masking money only, at every display boundary including chat, keeps the privacy intent (no balances leak) while keeping the app legible (basis: audit 1a and 1b, and the project rule that financial ledgers stay local).

On the polish list, the engineer chose the visible, cheap items (spending label, crypto ticker, deep link) and deliberately deferred the heavier vault and RAG fixes, which touch ingestion and deserve their own round.

## References

Reference level: sources only, no links.

**Project sources** (verifiable, in this repo):
- `docs/reviews/2026-10-12-ui-ux-audit.md`: the hands on audit that seeded the polish items (1a, 1b, 2.5, 2.7, 2.8, 2.9, 3.5, 3.7, and section 4 on deprecated APIs).
- `docs/specs/0016-ui-polish-allocation-strategy-copilot/index.md`: the prior round, whose tool trim, confirmation token pattern, and AC-10 masking rule this round builds on and partly revises.
- `docs/specs/0009-copilot-layout-scroll-calculation-single-source-of-truth/index.md`: the single source of truth pattern reused for the date resolver.
- `agent/copilot.py`, `agent/tool_schemas.py`, `agent/tools/`: the existing tool pattern, tool map, and dispatcher the new tool joins.
- `app.py`, `ui/filters.py`, `ui/pages/investments/__init__.py`, `ui/copilot_sidebar.py`: the navigation, filter, tab, and sidebar surfaces the action layer touches.
- `AGENTS.md` (root and the `agent/`, `ui/` nested files): the stack, the local first privacy rule, the read only SQL rule, and the declined skills.
- Installed Streamlit 1.65 signatures: `st.switch_page` and `st.tabs(..., default=..., key=...)` confirmed present in the installed version.

**Practices & standards**:
- Thin action layer over an existing system, reusing what works (fix in place, strangler instinct for live systems).
- Single source of truth for a computed value, so two consumers cannot disagree.
- Whitelist validation for anything a language model names, since the model is the trust boundary in this app.
- Mask at the display boundary and only the sensitive class, so privacy and legibility coexist.
- Migrate deprecated framework APIs before the upgrade that removes them.
