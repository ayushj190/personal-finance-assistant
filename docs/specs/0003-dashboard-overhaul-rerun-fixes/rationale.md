# 0003. Dashboard Overhaul & Rerun Fixes (Rationale)

## Context

The primary dashboard is the focal point of the personal finance assistant. In its current implementation, user interactions face two major friction points:

1. **Rerun flickers**: In Streamlit, default user interactions (such as adjusting an account balance in a form or clicking on a Plotly chart slice) trigger a script rerun from top to bottom. Because the dashboard embeds external widgets (such as the TradingView ticker tape iframe) and expensive network queries (such as the eToro news feed), every interaction destroys and recreates DOM elements, leading to noticeable visual flicker and iframe resets.
2. **Widget key collisions and card layout inconsistency**: Dynamic account grids generate form inputs and popovers inside loops. Without strict, deterministic namespacing of widget keys, dynamically filtered account lists or multiple accounts from the same institution risk colliding on keys or throwing Streamlit `DuplicateWidgetID` warnings. Furthermore, account cards with differing APY subtext or badge heights previously caused staggered card alignments.

Eliminating these problems requires modernizing the dashboard architecture using Streamlit fragments (`@st.fragment`), tokenized CSS wrappers, and strict widget key naming rules.

## Options considered

### Option 1: Fragment isolation with namespaced state and tokenized cards

Isolate interactive sections into distinct `@st.fragment` functions. External widgets like the TradingView ticker tape and eToro news feed render in static fragments that do not re-execute when charts or balance popovers are modified. Account cards use design tokens from `ui/theme` and namespaced keys formatted as `dashboard_acc_{id}_*`.

**Pros**:
- Preserves responsive in page interactions without full page teardowns or iframe reloading.
- Standardizes visual spacing and card alignment across institutions.
- Completely prevents duplicate widget key errors.

**Cons**:
- Requires managing state scoping between fragments when balance adjustments need to reflect on top level KPI totals.

### Option 2: Full page reruns with external iframe suppression and caching

Keep the existing single monolithic script structure, but cache calculations with `@st.cache_data` and remove external iframes like TradingView during interactive sessions.

**Pros**:
- Simple sequential code flow without managing fragment state boundaries.

**Cons**:
- Fails to fix the core user experience issue: every chart click or balance edit causes a noticeable flash across the entire screen.

### Option 3: Modal dialog migration for all interactive controls

Move balance adjustment forms and chart drilldown views entirely into modal dialogs (`@st.dialog`).

**Pros**:
- Clean separation of editing tasks from the overview canvas.

**Cons**:
- Adds unnecessary popup friction for quick balance adjustments and breaks seamless inline chart exploration.

## Rationale

Option 1 is selected because Streamlit fragments provide native, fine grained re-rendering without imposing modal dialog friction on the user. Isolating the TradingView widget and eToro news feed in independent fragments completely eliminates the visible iframe flicker during chart drilldowns and balance adjustments. Applying the design token system established in spec 0002 guarantees consistent typography, alignment, and responsiveness.
