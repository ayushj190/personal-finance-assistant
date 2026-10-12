# UI / UX / Functioning Audit — 2026-10-12

Hands-on pass over the running app (demo dataset, `PFA_DEMO=1`, **Hide values ON** as requested) to
pressure-test it for sale-readiness. Copilot exercised with real prompts; every page visited.

**Method**
- App: `streamlit run app.py` on demo dataset (`data/demo.db`, Amsterdam profile, 535 tx, 15 holdings, 8 statutes).
- Viewport ~1600×900, dark theme, Privacy Shield ON for the whole pass.
- Copilot: live `qwen2.5:7b-instruct` via Ollama on CPU.

**Severity:** `P1` broken/blocking · `P2` important · `P3` polish · `INFO` note

---

## 1. Privacy Shield (the biggest issue) — P1

### 1a. Over-masking destroys readability
With Hide values ON the app is close to unusable because it masks **non-monetary** content, not just amounts:

| Surface | Masked (wrongly) | Still visible |
|---|---|---|
| Investments → Portfolio Holdings | Ticker, Asset Name, Type, Units, Avg Open, Cost Basis, Current Price, Value, P&L, P&L(%) | Asset Class, Status |
| Investments → Live Market Quotes | Ticker, Asset Name, Market Price | — |
| Transactions | Merchant / Payee | Account, Category, Date |
| Spending → Subscription Leak Detector | Merchant | Cadence |
| Spending → Top Merchants | Merchant | — |
| Everywhere | **all percentages**: donut slice %, MoM %, Fixed/Disc %, P&L %, mortgage rate %, repayment-progress %, "**** assets" position count | — |

Result: charts lose their y-axis ticks (blank) and donuts/percentages read `****%`, so Privacy mode
actively defeats analysis. Merchant names and tickers are not secrets — they are what makes the data legible.

**Recommend:** mask only currency-formatted monetary values at the presentation boundary. Keep identifiers
(ticker, asset name, merchant, category, dates), counts, and percentages visible. If some fields must hide,
expose per-column control rather than a global scalar wipe.

### 1b. Masking leaks (inconsistent — some amounts left in the clear)
Privacy mode is not applied uniformly; derived/annotated values bypass it:
- Mortgage → **Extra Repayment Simulator**: `TOTAL INTEREST SAVED €2,428.61` shown in full while every other amount is masked.
- Tax breakdown annotation: `Tax refund benefit: +€3,634.21`; notes `0.1% tax credit on €0.00 green assets`, `Groenfondsen cap: €71,251`.
- Tax Capital Allocation chart title: `€10,000 Lump Sum Allocation over 10 Years`.
- **Copilot chat**: answers print raw amounts (e.g. net worth `€214,821.49`, spend `€743.60`) while every table is masked.

Net effect: screening-sharing with Hide values ON still leaks real figures through chat and annotations.

**Recommend:** route all displayed money (including simulator results, RAG/LLM text, chart titles/axes)
through the single mask formatter, or explicitly document that chat output is excluded.

---

## 2. Functional issues

| # | Sev | Issue | Evidence | Suggested fix |
|---|---|---|---|---|
| 2.1 | P2 | Legal vault showed **"0 statutes indexed across 6 domains"** on first visit after restart, then **8** on revisit. First-load ingest/render race. | `ui/pages/tax.py:352-353`; `data/demo.db` has 8 docs / 31 chunks | Ingest during `database.migrate()`/seed, or render a loading state until ready |
| 2.2 | P2 | RAG embedding path degraded. Ollama probe uses `all-minilm` (not pulled → `/api/embed 404`), and batch sync embeds with the **chat model** (`qwen2.5`) not an embed model, so it silently falls back to a 128-token bag-of-words pseudo-vector → weak semantic search. | `services/legal_vault_service.py:16,30,200-245`; `services/rag_service.py:238-245` | Use an installed embed model, or go straight to FastEmbed; don't embed with a chat model |
| 2.3 | P2 | **Auto-sync runs per Streamlit session.** With multiple tabs open, identical bank/eToro HTTP calls repeat (observed 4× identical requests in the same second in `data/logs/app.log`). Rate-limit/quota risk. | `app.py:54-77` (`_trigger_auto_sync`) | Single-flight global lock / dedupe by last-sync timestamp in DB, not per session |
| 2.4 | P2 | Stale PSD2 account refs: repeated `GET /accounts/{id}` → **404**, then `/balances` → 200. | `data/logs/app.log` | Re-resolve account IDs on 404; stop retrying known-stale IDs |
| 2.5 | P3 | Deep link `/dashboard` shows **"Page not found"** toast (page `url_path="dashboard"` but `default=True` serves it at `/`). | `app.py:100-102` | Rename url_path to `/` or add a redirect |
| 2.6 | P3 | Unhandled asyncio `ConnectionResetError [WinError 10054]` tracebacks in logs (13×) from httpx transport teardown. | `data/logs/app.log` | Suppress/quiet transport-reset noise; close clients cleanly |
| 2.7 | P3 | **Crypto ticker says wrong things**: `BTC-USD 1.68T −5,191,230,947.00 (−0.31%)`, `ETH-USD 312.29B +2,766,358,214.00` — market-cap magnitude in the price/change slots. | Dashboard ticker | Fix field mapping for crypto quotes (price vs change vs cap) |
| 2.8 | P3 | Spending period selector shows raw keys: `2026-09 (24 Sep — 23 Oct)` and header `Expense Breakdown (2026-09)`. | Spending page | Use `September 2026`; align range with the selected month |
| 2.9 | P3 | Copilot misreads "last month" as the **current** (partial) month (answered October 2026, not September). | Copilot test | Normalize relative dates in tool layer |
| 2.10 | INFO | Optional **Brave Search API key** implies optional cloud egress — contradicts the "zero cloud / no telemetry" positioning. | Settings → AI Model | Clarify it is opt-in and off by default |
| 2.11 | INFO | Transactions default shows `Showing 77 transactions` of 535 — scope is unlabeled. | Transactions | Label the filter (e.g. "last 30 days / needs review") |

---

## 3. UI / visual

| # | Sev | Issue |
|---|---|---|
| 3.1 | P2 | Tax → **Net Wealth Trajectory chart has a duplicated title**: Streamlit section header *and* the Plotly title overlap at the top of the plot. Remove one. |
| 3.2 | P2 | Privacy mode blanks **all chart y-axis ticks** (Runway projection, Monthly expense trend, Amortization, Net wealth trajectory) → charts convey nothing. (see 1a) |
| 3.3 | P3 | Donut labels crowded/rotated/overlapping (Spending by Category; Box 1 / Box 3 half-donuts). Prefer legend + no in-slice labels. |
| 3.4 | P3 | TradingView attribution (`TV`) overlaps the last ticker; leftmost ticker clipped at the left edge. |
| 3.5 | P3 | Demo dashboard charts render **blank for several seconds** (Plotly mounts late) with no skeleton/spinner — first impression looks broken. Add a loading placeholder. |
| 3.6 | P3 | Settings → Open Banking setup guide is **expanded by default** — a wall of text as the first thing you see. Collapse it. |
| 3.7 | P3 | Most pages leave a large black gap below content (dashboard ~157px overflow; others more). Tune vertical rhythm/spacing. |
| 3.8 | INFO | Sidebar quick-action DOM shows stray icon ligature text (`savings`, `expand_more`) — visually fine, but confirm accessible names. |

---

## 4. Deprecated APIs (will break) — P1 for maintenance

Streamlit emits removal warnings on **every** render, and the removal dates are already past:

- `use_container_width` — *"will be removed after 2025-12-31"* — used across virtually every table/chart/metric.
- `st.components.v1.html` — *"will be removed after 2026-06-01"* — used in the charts/embeds.

**Recommend:** migrate to `width="stretch" | "content"` and `st.iframe`. Do this before the next Streamlit
upgrade; a future bump will break most pages at once.

---

## 5. Copilot assessment

**Works well**
- "What is my net worth?" → correct, itemised (`€214,821.49` = cash + investments + home equity).
- "How much did I spend last month?" → category breakdown **plus an auto-generated chart** (`Spending by Category (for 2026-10)`).
- "Explain the Dutch 30% expat ruling…" → structured, cited (Art. 31a / 10ea / 2.6).

**Gaps**
- **Unmasked output** (see 1b) — chat bypasses Privacy Shield.
- **Latency ~30–60 s/turn** on CPU `qwen2.5:7b` (two `/api/chat` calls per turn: route + answer). Add a model/size guidance note or GPU path for demos.
- No surfaced timeout/error state if the model stalls (UI just keeps "thinking…").
- Relative-date understanding (#2.9).

---

## 6. Screenshots / README

- Current `docs/assets/screenshots/dashboard.png` was captured too early: top nav labels truncated
  (`Dashboa`, `Spendi`, `Investmen`…) and the metric row shows unrendered loading skeletons. Capture after charts settle.
- README stats drift: badge says **Tests: 215 Passed** while the pasted log shows **200 passed**; verify tool count ("25 native tools") and the Privacy-Shield "masks all numbers" claim (see 1a/1b).
- Screenshots intentionally keep Hide values ON per request — but see §1: masked screenshots will show
  `****` tickers, blank axes and `****%`, which undercuts the "showcase" intent. Consider fixing masking
  (mask amounts only) before re-shooting the README.

---

## 7. Suggested priority order

1. **Fix Privacy Shield scope + leaks** (§1) — biggest UX/trust win, and unblocks good README shots.
2. **Migrate deprecated Streamlit APIs** (§4) — prevents a hard break.
3. Vault first-load race + RAG embedding model (§2.1, §2.2).
4. Per-session auto-sync duplication + stale PSD2 refs (§2.3, §2.4).
5. Duplicate chart title, chart-y-axis/percent masking, ticker crypto mapping (§3.1, §3.2, §2.7).
6. Polish: date labels, donut legends, loading skeletons, spacing (§2.8, §3.3–3.7).