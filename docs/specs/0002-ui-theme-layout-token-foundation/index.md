# 0002. UI Theme and Layout Token Foundation

**Date**: 2026-10-11
**Status**: Accepted

## Summary

This specification establishes a unified design token architecture and layout system for the personal finance assistant. It standardizes color tokens, spacing scales, typography, and card container structures across light and dark modes. Developers and UI components consume these tokens through CSS custom properties for presentation styling and mirrored Python constants for charts and widgets, ensuring visual consistency with zero styling regressions.

## Requirements

**User stories**:
- As a user, I want a clean, legible, and visually cohesive interface in both dark and light modes so that reviewing balances and financial charts is effortless.
- As a developer, I want a single source of truth for spacing, colors, and typography so that new UI components automatically match the design system.

**Acceptance criteria**:
- **AC-1**: All foundational theme variables (colors, spacing, typography, radii, shadows) are defined as CSS custom properties in `ui/theme/` and scoped under `:root` and theme data attributes.
- **AC-2**: Financial semantic signals (income, expense, fixed costs, discretionary spending, cash, investments, liabilities) use consistent tokens across CSS classes and Plotly charts.
- **AC-3**: Spacing and layout tokens adhere to an 8px modular scale with half-steps (4px, 8px, 12px, 16px, 24px, 32px), eliminating arbitrary pixel values in layout containers.
- **AC-4**: Typography defines distinct type scales with Inter for UI prose and labels, paired with JetBrains Mono (with tabular figures enabled) for monetary balances and ledger values.
- **AC-5**: Streamlit container styling helpers standardize card containers, metric callouts, and section dividers using semantic CSS wrapper classes rather than fragile inline HTML snippets.
- **AC-6**: Python token constants in `ui/theme/tokens.py` mirror CSS custom properties seamlessly, ensuring `ui/theme/charts.py` renders Plotly figures matching the active theme palette without hardcoded divergent values.

## Decision

**Chosen option**: Option 1: Hybrid CSS Custom Properties and Python Constants (see `rationale.md`).

We establish CSS custom properties in static theme files for all Streamlit DOM styling, mirrored by typed Python token constants in `ui/theme/tokens.py` for Plotly chart themes and server rendered figures.

## Standard definition

**Canonical pattern**:

In `ui/theme/tokens.py`:
```python
# Color Palette Tokens
TEAL = "#2DD4BF"
VIOLET = "#A78BFA"
AMBER = "#FBBF24"
ROSE = "#FB7185"
SKY = "#38BDF8"
EMERALD = "#34D399"
SLATE = "#94A3B8"

# Semantic Financial Signals
COLOR_INCOME = EMERALD
COLOR_FIXED = ROSE
COLOR_DISCRETIONARY = AMBER
COLOR_SAVINGS = TEAL
COLOR_CASH = TEAL
COLOR_INVESTMENT = SKY
COLOR_LIABILITY = ROSE
COLOR_UNCATEGORIZED = SLATE

# Layout and Spacing Tokens (in pixels)
SPACE_XS = 4
SPACE_SM = 8
SPACE_MD = 12
SPACE_LG = 16
SPACE_XL = 24
SPACE_2XL = 32

RADIUS_SM = 8
RADIUS_MD = 12
RADIUS_LG = 16
```

In `ui/theme/common.css`:
```css
:root, .stApp {
  /* Spacing Scale */
  --space-xs: 4px;
  --space-sm: 8px;
  --space-md: 12px;
  --space-lg: 16px;
  --space-xl: 24px;
  --space-2xl: 32px;

  /* Border Radii */
  --radius-sm: 8px;
  --radius-md: 12px;
  --radius-lg: 16px;

  /* Typography */
  --font-family-sans: "Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  --font-family-mono: "JetBrains Mono", SFMono-Regular, Menlo, Monaco, Consolas, monospace;

  /* Semantic Financial Signals */
  --color-income: #34D399;
  --color-fixed: #FB7185;
  --color-discretionary: #FBBF24;
  --color-savings: #2DD4BF;
  --color-cash: #2DD4BF;
  --color-investment: #38BDF8;
  --color-liability: #FB7185;
  --color-uncategorized: #94A3B8;
}

[data-theme="dark"], body.dark {
  --bg-primary: #0a110d;
  --bg-surface: #101c15;
  --bg-surface-elevated: #1e3325;
  --border-subtle: #1e3325;
  --text-primary: #ecfdf5;
  --text-secondary: #94A3B8;
  --text-muted: #64748B;
}

[data-theme="light"], body.light {
  --bg-primary: #F8FAFC;
  --bg-surface: #FFFFFF;
  --bg-surface-elevated: #F1F5F9;
  --border-subtle: #E2E8F0;
  --text-primary: #0F172A;
  --text-secondary: #475569;
  --text-muted: #94A3B8;
}

/* Card Container Pattern */
.stCard, .finance-card {
  background-color: var(--bg-surface);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  padding: var(--space-lg);
  margin-bottom: var(--space-lg);
  transition: border-color 0.15s ease-in-out;
}
```

**Replaces**:
- Hardcoded hexadecimal values dispersed throughout page scripts.
- Unstructured pixel margins and paddings in ad-hoc HTML strings.
- Arbitrary inline CSS styling blocks embedded directly in Streamlit markdown calls.

**Enforcement**:
- Code reviews and centralized theme helper functions (`inject_custom_css()`, `render_chart()`).
- Automated tests verifying `tokens.py` exports and CSS syntax validity.

**Rollout**:
- Phase 1: Define variables in `ui/theme/common.css`, `dark.css`, `light.css`, and `tokens.py`.
- Phase 2: Refactor `ui/theme/charts.py` to bind directly to semantic tokens.
- Phase 3: Migrate dashboard and investment metric cards to standard `.finance-card` containers.

**Exceptions**:
- Custom external widgets or third party embedded iframes that do not inherit parent DOM CSS variables.

## Build plan

- [x] 1. Standardize design token definitions in `ui/theme/tokens.py`, exporting colors, modular spacing, and typography scale, satisfying **AC-1**, **AC-2**, and **AC-3**.
- [x] 2. Update `ui/theme/common.css`, `ui/theme/dark.css`, and `ui/theme/light.css` with semantic CSS custom properties for surfaces, text, borders, and financial indicators, satisfying **AC-1** and **AC-4**.
- [x] 3. Implement standard card container styles (`.finance-card`, `.metric-card`) in `ui/theme/common.css`, satisfying **AC-5**.
- [x] 4. Refactor `ui/theme/charts.py` to reference standardized financial semantic colors for income, expenses, and portfolio asset categories, satisfying **AC-2** and **AC-6**.
- [x] 5. Update unit tests in `tests/test_ui_theme.py` to validate token consistency and theme injection behavior, satisfying **AC-1** and **AC-6**.

## Consequences

**Positive**:
- Consistent visual language across every screen and modal dialog.
- Instant dark and light theme switching with coherent contrast and legibility.
- Simplifies authoring new pages by providing turnkey `.finance-card` containers and spacing helpers.
- Eliminates duplicated color hex strings between Python scripts and CSS stylesheets.

**Negative / tradeoffs**:
- Modifying a token value requires updating both the CSS variable in `common.css` and its corresponding constant in `tokens.py`.
- Existing pages using older custom CSS classes need gradual migration to the new container classes.
