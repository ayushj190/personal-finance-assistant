# Verify: UI Layout and Navigation Polish · spec 0015 · updated 2026-10-12
_Steps derived from spec 0015 acceptance criteria. `/check verify` runs these; `/test` locks the durable ones._

## UI / manual
- [ ] Open http://127.0.0.1:8501 at 1440px viewport width → verify Dashboard, Spending, Investments, Mortgage, Transactions render full text without ellipsis or clipped descenders → AC-1
- [ ] Inspect Material Symbols icons in top navigation → verify icons render cleanly at 1.25rem size with margin and zero clipping → AC-2
- [ ] Inspect top right toolbar area → verify 3-dots popover button has at least 64px right clearance without overlapping navigation tabs, and Deploy button is hidden → AC-3
- [ ] Navigate to /investments and /settings → verify in-page sub tabs (Holdings, Exposure, Realized P&L, Watchlist, News) render full text with clear underline indicators → AC-4
- [ ] Resize viewport to 1200px width → verify trailing tabs fold cleanly into native overflow dropdown without horizontal scrollbars or page jitter → AC-5
- [ ] Open top right 3-dots popover menu → verify Settings link and Hide Values / Privacy toggle function as expected → spec Value sourcing row 2

## Commands
- [ ] `.\.venv\Scripts\pytest -q` → 215 tests pass with zero failures → regression check

## Acceptance-criteria coverage
- AC-1 covered by step 1 · AC-2 covered by step 2 · AC-3 covered by step 3 · AC-4 covered by step 4 · AC-5 covered by step 5
