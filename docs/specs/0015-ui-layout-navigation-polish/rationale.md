# 0015. UI Layout and Navigation Polish — Rationale

## Context

During autonomous browser testing of the live application on standard and compact laptop screens, several visual and layout flaws became evident. The top navigation bar rendered with truncated labels such as Dashboa..., Spendi..., and Mortga... because Streamlit applies tight default widths, hidden overflow, and text ellipsis on inner flex containers. In addition, the top right three dots options menu was placed too close to the trailing navigation items, risking overlap when viewports narrow.

If we do not fix these layout issues, the user interface feels unfinished and cramped despite having ample horizontal screen real estate. The financial modeling tools and privacy protections work cleanly, so polishing the visual typography, icon alignment, and layout padding brings the interface up to modern production standards.

## Options considered

### Option 1: Pure CSS Overhaul in common.css

We modify common.css to override Streamlit internal flex wrappers, forcing tab containers and inner spans to take natural content widths and disabling text ellipsis truncation.

**Pros**:
- Preserves native Streamlit routing and page state without external dependencies.
- Surgical change contained entirely within existing design tokens and stylesheets.
- Works across all present and future pages automatically.

**Cons**:
- Relies on Streamlit DOM selectors that require periodic inspection during major framework upgrades.

### Option 2: Custom HTML and JavaScript Top Navbar

We build a custom HTML navigation component rendered via an iframe or custom Streamlit component, bypassing native st.navigation top bar styling entirely.

**Pros**:
- Total control over markup, spacing, and responsive breakpoints.

**Cons**:
- Breaks standard Streamlit session state and page link synchronization.
- Introduces iframe communication overhead and complicates deep linking.
- Much higher maintenance burden and risk of regression.

## Rationale

Option 1 keeps the architecture lean and avoids introducing unnecessary components. The native st.navigation routing works reliably and already supports automatic overflow folding into the more menu on narrow viewports. Streamlit only fails on presentation because its default style sheets set restrictive wrapper widths and ellipsis overflow. By targeting those specific selectors in common.css, we solve the root cause directly with zero impact on application logic.
