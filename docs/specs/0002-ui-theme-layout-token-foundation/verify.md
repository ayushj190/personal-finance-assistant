# Verify: UI Theme & Layout Token Foundation · spec 0002 · updated 2026-10-11
_Steps derived from spec 0002 acceptance criteria. `/check verify` runs these; `/test` locks the durable ones._

## UI / manual
- [ ] Toggle dark and light theme in settings or session state; confirm background, surface, and text colors update cleanly without style bleed → AC-1
- [ ] Inspect `.finance-card` and `.metric-card` DOM containers; confirm 12px border radius and 16px padding apply from CSS custom properties → AC-3, AC-5
- [ ] Check monetary figures on KPI cards and ledger tables; verify JetBrains Mono font family and tabular figure alignment render properly → AC-4
- [ ] Render Plotly charts (net worth area, spending donut, mortgage amortization); confirm semantic financial colors (income emerald, liability/fixed rose, cash teal, investment sky) align with theme palette → AC-2, AC-6

## Commands
- [ ] `.\.venv\Scripts\pytest tests/test_ui_theme.py` → 17 passed → AC-1, AC-2, AC-3, AC-4, AC-5, AC-6
- [ ] `.\.venv\Scripts\python.exe run_tests.py` → 91 passed with zero regressions across entire suite → AC-1..AC-6

## Acceptance-criteria coverage
- AC-1: CSS custom properties scoped under :root / .stApp and theme attributes · covered by `tests/test_ui_theme.py::TestCSSCustomProperties` & manual theme toggle
- AC-2: Financial semantic signal colors consistent across CSS and charts · covered by `tests/test_ui_theme.py::TestUIThemeTokens::test_semantic_financial_signals` & chart render
- AC-3: Spacing and layout 8px modular scale (4px half-step to 32px) · covered by `tests/test_ui_theme.py::TestUIThemeTokens::test_spacing_scale_adheres_to_8px_modular`
- AC-4: Inter for UI prose and JetBrains Mono with tabular figures for numbers · covered by `tests/test_ui_theme.py::TestUIThemeTokens::test_typography_tokens` and `.tabular-nums` CSS rules
- AC-5: Semantic card containers (`.finance-card`, `.metric-card`, `.section-divider`) · covered by `tests/test_ui_theme.py::TestUIComponentsHelpers`
- AC-6: Python token constants mirror CSS properties without drift · covered by `tests/test_ui_theme.py::TestCSSCustomProperties::test_common_css_tokens`
