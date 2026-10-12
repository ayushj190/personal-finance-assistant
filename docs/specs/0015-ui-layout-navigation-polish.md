# 0015. UI Layout and Navigation Polish

**Date**: 2026-10-12
**Status**: Proposed

## Summary

This design improves the visual presentation and navigation layout across the desktop application. Browser testing revealed that top navigation tab titles and material icons were clipped by default container widths and ellipsis styling. We will apply a pure CSS overhaul in common.css to unlock tab labels, provide adequate header spacing for the options menu, and ensure all sub tabs display without cutoff.

## Context

During autonomous browser testing of the live application on standard and compact laptop screens, several visual and layout flaws became evident. The top navigation bar rendered with truncated labels such as Dashboa..., Spendi..., and Mortga... because Streamlit applies tight default widths, hidden overflow, and text ellipsis on inner flex containers. In addition, the top right three dots options menu was placed too close to the trailing navigation items, risking overlap when viewports narrow.

If we do not fix these layout issues, the user interface feels unfinished and cramped despite having ample horizontal screen real estate. The financial modeling tools and privacy protections work cleanly, so polishing the visual typography, icon alignment, and layout padding brings the interface up to modern production standards.

## Requirements

**User stories**:
- As an active user, I want full, uncropped page titles and icons in the top navigation bar so that I can switch views with clear visual recognition.
- As an active user, I want the top right options menu positioned with comfortable breathing room so that it never crowds or overlaps page links.
- As an active user on a laptop screen, I want excess navigation tabs to wrap cleanly into the native more menu without breaking page flow.

**Acceptance criteria**:
- **AC-1**: All top navigation tab labels (Dashboard, Spending, Investments, Mortgage, Transactions, Tax Analysis) render full text without ellipsis cutoff or clipped descenders on viewports 1280 pixels wide or higher.
- **AC-2**: Material Symbols icons beside navigation labels render at 1.25rem size with adequate right margin and zero icon clipping.
- **AC-3**: The top header toolbar provides at least 64px right padding to ensure the three dots action popover never overlaps trailing tabs.
- **AC-4**: In-page sub tabs across the Investments and Settings pages render full uncropped headers and clear active indicator lines.
- **AC-5**: On narrower viewports around 1200 pixels wide, trailing tabs fold into the native overflow dropdown menu cleanly without horizontal scrollbars or page jitter.

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

## Decision

**Chosen option**: Option 1: Pure CSS Overhaul in common.css

We will overhaul common.css with explicit rules that uncrop top navigation tabs, give material icons proper margins, provide 64px right toolbar padding, and polish in-page tab containers.

## Rationale

Option 1 keeps the architecture lean and avoids introducing unnecessary components. The native st.navigation routing works reliably and already supports automatic overflow folding into the more menu on narrow viewports. Streamlit only fails on presentation because its default style sheets set restrictive wrapper widths and ellipsis overflow. By targeting those specific selectors in common.css, we solve the root cause directly with zero impact on application logic.

## Feature design

**CSS overrides and target selectors**:

```css
/* Uncrop top navigation tabs, labels, and icons */
[data-testid="stTopNavLink"] {
    width: auto !important;
    max-width: none !important;
    min-width: max-content !important;
    padding: 6px 16px !important;
    overflow: visible !important;
}

[data-testid="stTopNavLink"] > * {
    max-width: none !important;
    overflow: visible !important;
    width: auto !important;
}

[data-testid="stTopNavLink"] p,
[data-testid="stTopNavLink"] span {
    text-overflow: clip !important;
    white-space: nowrap !important;
    overflow: visible !important;
    max-width: none !important;
    line-height: 1.4 !important;
}

[data-testid="stTopNavLink"] [data-testid="stIconMaterial"] {
    font-size: 1.25rem !important;
    min-width: 1.25rem !important;
    width: 1.25rem !important;
    height: 1.25rem !important;
    overflow: visible !important;
    margin-right: 6px !important;
    flex-shrink: 0 !important;
}

/* Header toolbar breathing room for top right three dots menu */
header[data-testid="stHeader"] [data-testid="stToolbar"] {
    padding-right: 64px !important;
    overflow: visible !important;
}

/* In-page sub tabs uncropped text and indicator line */
div[data-testid="stTabs"] button[role="tab"] {
    overflow: visible !important;
    padding: 8px 16px !important;
}

div[data-testid="stTabs"] button[role="tab"] p,
div[data-testid="stTabs"] button[role="tab"] span {
    overflow: visible !important;
    text-overflow: clip !important;
    white-space: nowrap !important;
}
```

**Value sourcing**:
| Action | Value produced or displayed | Source |
|---|---|---|
| Render top navigation | Page title and icon | Defined in app.py st.Page configurations |
| Render options menu | Settings link and privacy toggle | Rendered in app.py container top_navbar_actions |
| Render in-page sub tabs | Tab titles (Holdings, Exposure, etc.) | Defined in st.tabs calls within each page module |

**Key invariants**:
- The privacy toggle must remain fully functional and visible inside the top right popover.
- Top navigation links must remain clickable and highlight the active page with primary color accents.
- No changes to page routing or database access.

**Critical test scenarios**:
- Happy path: Opening the application on a desktop browser at 1440px wide displays all six top navigation items fully spelled out without ellipsis, verifying **AC-1** and **AC-2**.
- Toolbar spacing: The three dots popover button sits comfortably in the top right corner without overlapping the rightmost navigation tab, verifying **AC-3**.
- In-page tabs: Clicking through Investments sub tabs (Holdings, Exposure, Realized P&L, Watchlist, News) shows full labels and clear underline indicators, verifying **AC-4**.
- Responsive folding: Shrinking browser width to 1200px moves trailing items into the more menu without horizontal scrollbars, verifying **AC-5**.

## Build plan

1. Update `ui/theme/common.css` top navigation rules to remove width caps, eliminate text ellipsis, and set icon margins, satisfying **AC-1** and **AC-2**.
2. Adjust header toolbar padding in `ui/theme/common.css` to 64px right clearance for the options popover, satisfying **AC-3**.
3. Refine `stTabs` styling in `ui/theme/common.css` to ensure nested sub tab labels and active underlines never clip, satisfying **AC-4**.
4. Verify responsive overflow behavior across standard and compact viewports in browser mode, satisfying **AC-5**.

## Consequences

**Positive**:
- Eliminates unsightly text truncation across all page tabs and sub tabs.
- Improves visual balance and perceived polish of the desktop interface.
- Preserves native Streamlit routing and low code simplicity.

**Negative / tradeoffs**:
- Requires ongoing awareness of Streamlit CSS class changes if the framework major version is bumped.

**Neutral**:
- Zero database or backend impact; purely styling adjustments.

## Follow-up

- [ ] Run browser verification after applying the CSS updates to confirm all labels display without clipping.
