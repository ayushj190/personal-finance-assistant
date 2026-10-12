# 0008. Native top navigation, sidebar privacy toggle, and compact page layout

**Date**: 2026-10-12
**Status**: Accepted

## Summary

The custom tab bar built from page links is replaced by Streamlit's own top navigation, with larger Material icons and a clear highlight on the active page. The Hide values toggle moves into the sidebar, next to a shorter one line brand title that sits flush at the top, and the sidebar can no longer be collapsed so the toggle is always reachable. The dashboard ticker sits right under the navigation and shows each asset once, using the correct exchange listing. Page controls are packed into single rows and spacing is tightened so every page shows more content above the fold.

## Context

The app shell (`app.py`) draws its own tab bar: a `top_app_bar` container holding seven `st.page_link` columns plus the Hide values toggle, styled by roughly 120 lines of CSS in `ui/theme/common.css` that fight Streamlit's DOM (negative margins, `!important` on every rule, folder tab borders). Emoji icons render small, take no color, and cannot carry an active tint. The bar wraps at mid widths because the toggle claims a fixed 16% column.

The sidebar header (`ui/copilot_sidebar.py`) opens with a full `<h1>Personal Finance Assistant</h1>`; Streamlit's default heading padding leaves a dead band above it. The privacy state lives in `st.session_state["hide_amounts"]`, mirrored from the widget key `global_privacy_toggle`, and defaults to hidden on every session.

The dashboard ticker (`_render_ticker_fragment` in `ui/pages/dashboard.py`) strips any exchange suffix (`ASML.AS` becomes `ASML`) and dedupes on the raw ticker before stripping. Two listings of one asset (a direct holding and an eToro mirror position) can therefore appear twice, and a stripped symbol often resolves to a US listing instead of the one held.

Page controls stack vertically: Spending renders the Filters popover, then View Scope, then a separate action row; Transactions renders Filters, then a checkbox and search row; Tax and Mortgage repeat the page name as an in page heading above a lone full width button. The app runs on Streamlit 1.65 (native `position="top"` navigation available since 1.46). No data, schema, or service logic is involved.

## Requirements

**User stories**:
- As the user, I want large, clearly highlighted page tabs so I always know where I am and can switch pages at a glance.
- As the user, I want the Hide values toggle always reachable in one fixed place so I can mask amounts instantly.
- As the user, I want the ticker to show each of my assets once, with the listing I actually hold.
- As the user, I want page controls packed into compact rows so more content fits on screen.

**Acceptance criteria**:
- **AC-1**: The sidebar opens with a single line brand row (`:material/savings:` icon plus the text "Finance Assistant"). Its top edge sits within 12px of the sidebar's top edge; no empty band appears above it.
- **AC-2**: The Hide values toggle sits on the right of the brand row, with the caption "Hide values" directly below the switch. Toggling masks or unmasks every amount exactly as today. A new session starts hidden. The state survives page navigation.
- **AC-3**: The sidebar cannot be collapsed at desktop widths (768px and up): no collapse or expand control is rendered.
- **AC-4**: Navigation uses `st.navigation(pages, position="top")`. All 7 pages are reachable, in the current order, with these Material icons: Dashboard `space_dashboard`, Spending `shopping_cart`, Investments `trending_up`, Mortgage `home`, Transactions `receipt_long`, Tax Analysis `account_balance`, Settings `settings`. Tab icons render at least 1.25rem and labels at least 0.95rem.
- **AC-5**: The active tab shows a tinted pill (`color-mix(in srgb, var(--primary-color) 12%, transparent)`, same rule in both themes), a primary colored icon, a bold label, and a 2px primary underline. Exactly one tab is active, and it updates on click, browser back/forward, and direct URL load (`/spending` etc.).
- **AC-6**: The old custom bar is gone: no `top_app_bar` container, no `st.page_link` row, and no `div.st-key-top_app_bar` CSS remain.
- **AC-7**: The ticker renders on the Dashboard only, directly under the navigation with at most 8px between them.
- **AC-8**: Ticker symbols come from direct holdings plus eToro mirror positions. Each ticker with a known exchange suffix maps to a TradingView prefixed symbol (table in Feature design); tickers with no suffix pass through unchanged; tickers with an unknown suffix, or containing `=` or `^`, or starting `ID_`, are skipped. The list is deduped on the final symbol, keeping first seen order. If nothing remains, the existing fallback (SPY, QQQ, FX:EURUSD) shows.
- **AC-9**: Compact layout:
  - Spending: Filters popover, View Scope, Set Budgets, and Link Mortgage share one row; the fiscal cycle caption stays, directly under that row. When no spending data matches, the row shows Filters only, followed by the existing info message.
  - Transactions: Filters popover, Review Uncategorized Only, and the search box share one row.
  - Tax: the `## 💶 Tax Analysis (NL)` heading and its intro line are removed; Edit Tax Profile is right aligned on the first row.
  - Mortgage: the configure button is right aligned on the first row (both the empty state and configured variants).
  - Investments: the Allocation Profile selector takes at most one third of the row width.
  - Global: main content top padding, vertical block gap, and heading margins are tightened on every page, Settings included.
- **AC-10**: All 7 pages render with no exception and no Streamlit warning (duplicate key, deprecation) in an automated smoke test.

## Options considered

### Option 1: Fix the custom page link bar in place
Keep `top_app_bar`, swap emoji for Material icons, restyle the CSS.
**Pros**: toggle stays inline with the tabs; smallest diff to `app.py`.
**Cons**: keeps 120 lines of fragile CSS against Streamlit internals; wraps at mid widths; every Streamlit upgrade risks breaking it.

### Option 2: Native `st.navigation(position="top")`, toggle moves to the sidebar
**Pros**: Streamlit owns layout, active state, URL sync, and overflow (extra tabs fold into a menu on narrow widths); deletes most custom bar CSS.
**Cons**: the toggle cannot sit in the nav row, so it moves to the sidebar, which then must stay open; styling the active pill still needs a few selectors on Streamlit's top nav DOM.

### Option 3: `st.segmented_control` driving `st.switch_page`
**Pros**: one widget, easy styling.
**Cons**: tabs stop being real links (no middle click, no URL on hover); extra rerun on every switch.

## Decision

**Chosen option**: Option 2: native top navigation, with the privacy toggle in a non collapsible sidebar.

Replace the custom bar with `st.navigation(position="top")`, move the toggle into the sidebar brand row, fix ticker symbol identity, and tighten page density with per page control rows.

## Rationale

The pain is fragility and density, and both come from the hand built bar. Native navigation removes the CSS that fights Streamlit, gives correct active state and URL behavior for free, and handles narrow widths. The cost (toggle cannot share the nav row) is answered by a fixed sidebar home, made safe by blocking collapse. The privacy default (hidden) means even a narrow screen overlay sidebar never leaks values. The ticker change fixes a real correctness bug (wrong listing, duplicates) rather than styling. Spending header work stops at regrouping because Slice 9 owns its declutter.

## Feature design

**Data model sketch**: none; no schema change.

**Interface surface** (UI only, no endpoints):

| Surface | Where | Change |
|---|---|---|
| Navigation | `app.py` | `st.Page(..., icon=":material/<name>:")` per AC-4; `st.navigation(pages, position="top")`; delete the `top_app_bar` block and `_on_privacy_toggle` |
| Privacy toggle | `ui/components.py` | new `render_privacy_toggle()`: `st.toggle("Hide values", key="global_privacy_toggle", on_change=_on_privacy_toggle, label_visibility="collapsed")` then `st.caption("Hide values")`; `_on_privacy_toggle` moves here unchanged |
| Brand row | `ui/copilot_sidebar.py` sticky header | replace the `<h1>` with `st.columns([0.75, 0.25], vertical_alignment="center")`: left `:material/savings: Finance Assistant` (one line, about 1.2rem, bold, zero top margin); right `render_privacy_toggle()` |
| Session state sync | `app.py` lines 31 to 40 | unchanged (initial `hide_amounts = True`, mirror to `global_privacy_toggle`) |
| Ticker | `ui/pages/dashboard.py` | new pure `_tradingview_symbols(tickers: list[str]) -> list[dict]` used by `_render_ticker_fragment`; drop the outer `margin-bottom: 8px` and keep the iframe height tight |
| Styling | `ui/theme/common.css` (plus `dark.css`/`light.css` only if a color variable is missing) | remove `div.st-key-top_app_bar` rules; add top nav icon/label sizing and active pill; zero top space in sidebar header; hide sidebar collapse controls at 768px and up; density pass |
| Page rows | `spending.py`, `transactions.py`, `tax.py`, `mortgage.py`, `investments.py` | per AC-9 using `st.columns(..., vertical_alignment="bottom")` |

**Ticker suffix map** (constant in `dashboard.py`):

| Suffix | Prefix | Example |
|---|---|---|
| `.AS`, `.PA`, `.BR`, `.LS` | `EURONEXT:` | `ASML.AS` → `EURONEXT:ASML` |
| `.L` | `LSE:` | `VUSA.L` → `LSE:VUSA` |
| `.DE` | `XETR:` | `EUNL.DE` → `XETR:EUNL` |
| `.F` | `FWB:` | `SAP.F` → `FWB:SAP` |
| `.MI` | `MIL:` | `ENI.MI` → `MIL:ENI` |
| `.MC` | `BME:` | `SAN.MC` → `BME:SAN` |
| `.SW` | `SIX:` | `NESN.SW` → `SIX:NESN` |

Any other suffix (e.g. `.TO`, `.HK`) is skipped. `description` stays the original ticker.

**Value sourcing**:

| Action | Value produced / displayed | Source |
|---|---|---|
| Render nav | page list, order, titles | `pages` list in `app.py` |
| Render nav | icons | constants per AC-4 |
| Render nav | active tab | `st.navigation` current page (URL path) |
| Toggle | hidden or shown state | `st.session_state["global_privacy_toggle"]` mirrored to `hide_amounts` |
| Toggle | default on new session | `app.py` init: `hide_amounts = True` |
| Ticker | raw tickers | `HoldingRepository.get_distinct_tickers(conn)` |
| Ticker | mirror symbols | `data/etoro_mirrors_cache.json`, `positions[].symbol` for `COPY:` tickers |
| Ticker | TradingView symbol | `_tradingview_symbols` with the suffix map above |
| Ticker | color theme | `st.get_option("theme.base")` (unchanged) |
| Spending row | fiscal caption | `get_fiscal_salary_day(conn)` (unchanged) |

**Key invariants**:
- Exactly one widget owns `global_privacy_toggle`, rendered once per run (sidebar only). A second instance raises a duplicate key error.
- `hide_amounts` defaults to `True`; nothing in this slice changes masking logic in `ui/components.py`.
- `_tradingview_symbols` is pure: no DB, no file, no Streamlit calls.
- Dialog triggers (Set Budgets, Link Mortgage, Edit Tax Profile, mortgage config) keep their current keys and arguments; only their placement moves.
- Spending row fill order: create the four columns first, render Filters into column 1, load the data with those filters, then render View Scope and the two buttons into columns 2 to 4. The early return on empty data happens after Filters and before the other three.
- Top nav styling targets Streamlit's `data-testid` attributes, confirmed against the 1.65 DOM at build time; no positional `nth-child` selectors.

**Security model**: no new data access. Privacy masking keeps its hidden by default behavior; blocking sidebar collapse keeps the toggle reachable.

**Configuration required**: none.

**Critical test scenarios**:
- Unit: `_tradingview_symbols(["ASML.AS", "ASML.AS", "VUSA.L", "AAPL"])` returns `EURONEXT:ASML`, `LSE:VUSA`, `AAPL` in that order, verifies **AC-8**.
- Unit: unknown suffix `RY.TO`, `EURUSD=X`, `^GSPC`, `ID_123` are all skipped, verifies **AC-8**.
- Unit: two inputs collapsing to one final symbol (`SAP.DE` from a holding and `SAP.DE` from a mirror) yield one entry; empty input yields the fallback trio from `_render_ticker_fragment`, verifies **AC-8**.
- Smoke: `AppTest.from_file("app.py")` switches through all 7 pages; each run has no exception, verifies **AC-4**, **AC-10**. The fixture redirects every loaded module's `DB_PATH` attribute (and any `migrate` default path) to a temp migrated DB and stubs `coordinator.submit`, so `data/finance.db` and the network are never touched.
- Smoke: toggling `global_privacy_toggle` on one page, switching page, the toggle value and `hide_amounts` persist, verifies **AC-2**.
- Manual (/check verify): measure brand row top offset, ticker gap, icon/label sizes, active pill on click, back/forward, and direct URL; confirm no collapse control; walk all AC-9 rows, verifies **AC-1**, **AC-3**, **AC-5**, **AC-6**, **AC-7**, **AC-9**.

## Build plan

Tracer Bullet: get the new navigation thread working end to end first (nav plus toggle, app still usable), then thicken with styling, ticker, and density.

1. [x] Switch `app.py` to `st.navigation(pages, position="top")` with Material icons; delete the `top_app_bar` block and its CSS in `common.css`, satisfies **AC-4**, **AC-6**
2. [x] Add `render_privacy_toggle()` to `ui/components.py` (move `_on_privacy_toggle`), build the brand row in the sidebar header, zero the sidebar top spacing, hide collapse controls at 768px and up, satisfies **AC-1**, **AC-2**, **AC-3**
3. [x] Style the top nav: icon and label sizing, active tinted pill with primary icon, bold label, and 2px underline, using theme variables, satisfies **AC-4**, **AC-5**
4. [x] Extract `_tradingview_symbols` with the suffix map, wire it into `_render_ticker_fragment`, make the ticker flush under the nav, satisfies **AC-7**, **AC-8**
5. [x] Density pass in `common.css` (main padding, block gap, heading margins, reusing `SPACE_*` tokens) plus per page rows for Spending, Transactions, Tax, Mortgage, Investments, satisfies **AC-9**
6. [x] Add unit tests for `_tradingview_symbols` and the AppTest smoke over all pages; update `tests/test_dashboard_page.py` if the ticker signature changes, satisfies **AC-8**, **AC-10**, **AC-2**

## Consequences

**Positive**:
- Most hand written nav CSS disappears; Streamlit upgrades are far less likely to break the shell.
- Correct active state, URL sync, and narrow width overflow come from Streamlit.
- Ticker quotes match the listings actually held, with no duplicates.
- Every page gains vertical space.

**Negative / tradeoffs**:
- The sidebar can never be hidden on desktop, permanently costing its width on every page.
- The toggle now depends on the sidebar header; below 768px Streamlit shows the sidebar as an overlay, so the toggle takes one extra tap there.
- Holdings on unmapped exchanges vanish from the ticker until their suffix is added to the map.
- Active pill selectors depend on Streamlit's top nav `data-testid` names, which may change in a future release.

**Neutral**:
- `_on_privacy_toggle` moves from `app.py` to `ui/components.py`.
- Spending fiscal caption and redundant filter removal remain for Slice 9; transaction bulk actions remain for Slice 10.

## Follow-up

- [ ] Slice 9 (Spending Flow) should start from the single control row built here when it moves the fiscal caption into a tooltip.
- [ ] If a holding on an unmapped exchange matters, extend the suffix map rather than relaxing the skip rule.
