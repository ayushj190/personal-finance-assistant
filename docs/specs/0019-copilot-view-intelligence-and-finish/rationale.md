# 0019 rationale: Copilot view intelligence and daily use finish

## Context

> ⚠️ Premise note: this round spans two kinds of work. The view intelligence (routing, view shaping, the page panel, and the new tools) is one coherent judgment call. The finish items (vault first load, RAG embedding, sync dedupe, dead code prune) are independent fixes that were not forced by that decision. They are folded into one round because the goal is a single finish pass before a pause, not because they share a decision. If this round were to slip, the finish items could each move to their own small spec or scope task without touching the routing design. Every finish item is still named with an acceptance criterion (**AC-10**) so it is not lost.

Spec 0017 built an action layer for the local Copilot: one validated `open_view` tool, a deterministic fast path for explicit phrasing ("open spending"), a shared date resolver so the chat answer and the page agree, a one time intent consumed by `app.py`, and a masking rule that hides money only. That layer is built but not yet verified. It is deliberately narrow: the Copilot moves you only when you phrase the request as navigation, and it draws its chart in the sidebar.

Two limits show up in daily use. First, you do not think in navigation verbs. You ask "what did I spend over the past 3 months" or "which tech stocks and ETFs do I hold", and you expect the app to go to the view that answers it, already set to the period or the dimension, not to stay put and make you replicate the setup by hand. Second, an answer that is really a chart reads poorly squeezed into a sidebar; it belongs at full size on the page the question is about, with the page scrolled to it. Both are view intelligence: the Copilot finding the perfect view for a question and showing the result where it belongs.

The surrounding forces are stable. This is a single local user app with no auth surface and a strict local first privacy rule, so there is no multi tenant scoping and no cloud call to weigh. The database is SQLite behind a read only authorizer, and the whole numeric core (portfolio, budget, tax, mortgage) already lives in `services/`, so new tools should reuse those routines rather than add math. Streamlit is the only UI, and it has no native scroll to element, which forces a mechanism choice for the panel. The stack is settled (spec 0017 added no dependency and this round adds none), so the design work is in the intent contract, the routing behavior, and the panel, not in a stack walk.

The consequence of not deciding is that the strongest feature of the app, the Copilot, stays a chat box that answers beside the app rather than driving it.

## Options considered

### Option 1: Extend the spec 0017 action layer (chosen)

Widen the existing `open_view` intent with validated view parameters and a panel headline, keep the model as the router with a deterministic topic map as a fallback, add the new tools to the same schema and dispatch map, render one shared panel per page from the turn's figure, and close the finish items in one pass.

**Pros**:
- One place defines the whitelists and the topic map, so the tool, the app, and the tests read the same truth, the property spec 0017 already established.
- Reuses the turn's figure for the panel, so a chart answer costs no extra query and cannot disagree with the chat text.
- Smallest diff: no new dependency, no schema change, no second chart path, no page rewrite.
- The confirm gated write pattern already exists (allocation delete), so writes add behavior, not a new safety model.

**Cons**:
- Content routing is more assertive than explicit only, so a fuzzy question can occasionally land somewhere unexpected.
- Per page view parameters add surface to validate and test as pages change.
- The scroll uses `st.components.html` and a pinned selector, a small piece of browser facing fragility.

### Option 2: A deterministic router in front of the model

A keyword and domain classifier decides the page and view before the model runs, and the model only writes the answer text.

**Pros**:
- Routing is instant and fully predictable, which removes all model dependency from navigation.

**Cons**:
- Cannot understand a combined or phrased question ("compare my tech holdings to last quarter"), which is exactly the kind of question this round is meant to serve.
- Duplicates the model's judgment in a second place that then drifts from it.
- The fast path in spec 0017 already covers the explicit case; a full classifier mainly adds failure modes for the fuzzy case.

### Option 3: A separate chart tool for the panel

The model calls a dedicated chart tool with an explicit spec (type, axes, data) to build the panel chart, and the page panel renders that.

**Pros**:
- Full control over the panel chart shape independent of what the data tool returned.

**Cons**:
- A second chart path to keep visually consistent with `agent/chart_renderer.py` and the page's own charts.
- The data tools already build the right figure for their data; a second tool usually restates it.
- More schema and more to test for no new answer capability.

### Option 4: Keep the sidebar chart, no page panel

Leave the chart inline in the sidebar and only navigate the page, as spec 0017 does.

**Pros**:
- Smallest possible change; reuses everything as is.

**Cons**:
- Does not deliver the on page, scrolled to experience that is the point of the request.
- A chart that matters most to the answer stays small and away from the page that owns the data.

## Rationale

Option 1 is chosen because the hard part already exists and is sound. Spec 0017 established the pattern this round needs: one whitelist, one resolver, one intent crossing the thread boundary once, and a confirm gated write. The view intelligence is the same pattern applied one level deeper, adding view parameters to the same intent and a panel to the same completion path, so the new behavior inherits the safety and the testability of the old. Reusing the turn's figure is the decisive simplification: it means the panel cannot contradict the chat answer, because both come from the same tool result, and it avoids a second chart path that would need its own consistency work.

The model leads the routing rather than a classifier (against Option 2) because the questions this round exists to serve are the fuzzy, combined ones a classifier fails on, and because the deterministic fast path already covers the explicit case. The topic map is kept only as a fallback for when the model runs but forgets to call the tool, which keeps a clear question landing right without giving the classifier the wheel. The panel reuses the turn's figure rather than a new chart tool (against Option 3) because a second chart builder buys no answer capability and costs consistency. The page panel is built rather than deferred (against Option 4) because the on page, scrolled to experience is the explicit request and the reason the round exists.

The finish items are folded in, with the caveat in the premise note, because the goal is one clean finish pass, and each item is either a small targeted fix (the 0016 nits, the dead code) or a correctness fix worth doing before a pause (the vault first load, the RAG embedding model, the sync dedupe). Each carries its own acceptance criterion so none depends on the routing decision to be tracked or delivered.
