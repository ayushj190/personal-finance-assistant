# 0016 rationale

Decision record for [index.md](index.md). Reasoning, the options weighed, and the evidence gathered while writing the spec.

## Context

> ⚠️ Premise note: this round is a bundle, not one decision. It holds five independently implementable changes (dashboard layout, spending panels and merchants, investment tables, allocation strategy management, Copilot correctness and tuning) plus a cleanup pass. One spec is right only because they arrived together as one review pass and share the same root causes: panel height that follows content, and one money and holdings value computed in two places. If the five drift apart during the build, split them: the allocation management work is the one that can stand alone, and the Copilot work should then follow it as its own spec. The narrower alternative, one spec per complaint, was rejected because it would produce six near identical Context sections for what is mostly one styling pass.

This round started as a set of reviewer comments made directly on the running application: too much space between the navigation bar and the market ticker, charts that should sit above the account cards, a Top Merchants table squeezed into half a column, a holdings table that shows one row per lot instead of one row per asset, a Status column nobody asked for, a second quotes table that duplicates the live watchlist, a blur over public market data, and panels that resize when a status change appears. One more asked for something genuinely new: creating and deleting allocation strategies, including by talking to the Copilot.

Two forces shaped the work. First, this is a live app with a large amount of existing styling and layout work already shipped (specs 0002, 0003, 0004, 0006, 0007, 0008, 0009, 0010, 0011, 0012, 0015), so the instinct is fix in place, not rewrite. Several of the complaints are the same defect seen from different screens: panels that do not line up, and money display state that changes layout. Second, the natural language request for allocation management collides with a hard rule in `AGENTS.md`: the Copilot executes read only SQL and never lets the model write. Any design that satisfies the request has to answer that collision honestly.

The Copilot itself had never been measured. The user asked for an extensive check of how it performs and whether it needs tuning, so this spec is grounded in a real evaluation against the local database rather than an opinion.

## Options considered

### Option 1: Fix in place, one change per defect, deterministic tool layer for writes

Each complaint gets the smallest change that removes it: CSS and render order for layout, one shared aggregation function for holdings, the existing repository for allocation writes, and new validated tool functions for the natural language path.

**Pros**:
- Small blast radius per change, reviewable one screen at a time.
- Fixes the shared root causes (panel height, holdings aggregation) once, so several complaints close together.
- Keeps the read only rule intact while still shipping the requested capability.

**Cons**:
- Leaves the existing CSS approach in place, so some fixes remain tied to Streamlit's generated markup.
- Adds write capability to the Copilot, which widens what a mistaken model call can do.

### Option 2: Rebuild the Streamlit layout layer on a stricter component wrapper

Wrap every page in one owned layout component so panel height, spacing, and grid come from project code rather than generated classes.

**Pros**:
- Complaints like misaligned panels and the top gap become impossible rather than fixed.
- One place to change spacing for every page.

**Cons**:
- Touches every page and every panel in the app, well beyond the reviewer's comments.
- A layout wrapper over Streamlit fights the framework exactly the way the current CSS already does, just from a different place.
- High regression risk for a cosmetic gain.

### Option 3: Give the Copilot write access through generated SQL

Loosen the authorizer so the model's own INSERT and DELETE run against the database.

**Pros**:
- Any natural language request works without a new tool per capability.

**Cons**:
- Directly breaks the `AGENTS.md` rule that the Copilot must never write, and puts the ledger behind a 7B model's SQL. Rejected outright.

## Rationale

Option 1 wins because the complaints are defect shaped, not architecture shaped. The top gap, the misaligned panels, and the KPI height jump are three symptoms of "layout depends on content height and on generated DOM classes"; each is a small, local fix, and none of them justify touching all eleven other pages. The holdings aggregation is the one change worth making at the service layer rather than in the page, because the Copilot reads the same data through `analyze_investments`, and today the two disagree in a visible way: the UI and the assistant both call one thousand one hundred thirty one positions for a portfolio of a few dozen assets (see the evidence below). One function, two consumers, one number.

The allocation request is satisfied without weakening the trust boundary. The model's job is narrow, pick the tool and parse the sentence into named arguments; the tool's job is to validate and write. This is the pattern `set_active_allocation_profile` and `save_risk_profile` already use, so the spec extends an existing convention rather than inventing a second one. The two extra guards, targets must sum to 100 and a delete needs an explicit confirmation, exist because a language model can produce a valid looking but wrong argument set, and deletion of a live allocation profile is not something to learn about afterwards.

Measurement changed the Copilot plan. Retuning the tool set is only worth doing because the evaluation showed the specific failure: eight prompts, correct tool on the first call in five, a hallucinated parameter on one, the wrong tool on another, and no tool at all for the delete request (which has no tool to find). It also showed a first call cost of up to seventy seconds against three to four seconds on later calls in the same process, which is a cold model load and a prompt that costs more to prefill than it needs to.

## Evidence: layout measurements

Measured live in the running app (viewport 1062 by 766, Windows, Edge).

**Dashboard top gap.** The navigation bar ends at y 48. The ticker iframe starts at y 84, so 36 pixels of dead space. The cause is structural, not padding: the main block's first child is an empty element container, the second is the fixed position options wrapper, and because the parent uses a column flex layout with a 16 pixel gap, two zero height rows still contribute two full gaps (52 to 68, then 68 to 84).

**KPI height.** `st.metric` renders 104 pixels tall without a delta and 118 pixels with one. On the Investments Holdings tab, Unrealized P&L and Cumulative Realized P&L measure 118 while their row neighbours measure 104, which is the "status changes the panel size" complaint and also why toggling Hide values shifts the layout, since masking turns a delta into `+****%`.

**Spending panels.** Spending by Category sits at y 427 with a 350 pixel chart. Subscription Leak Detector starts at y 476 and its table is 360 pixels tall, so the two panels differ by 49 pixels at the top and 59 at the bottom. Top Merchants sits at y 825 inside the left column at 302 pixels wide, with a 395 pixel table under it, which makes the left column far taller than the right.

**Blur.** `ui/pages/investments/watchlist.py` injects a `backdrop-filter: blur(8px)` overlay across 60 percent of the TradingView market quotes iframe whenever Hide values is on. The widget shows public prices, so the overlay hides nothing private (source: the same file that builds the widget HTML).

**CSS duplication.** `ui/theme/common.css` is 1389 lines and repeats whole rule blocks, including the top navbar actions block several times over. Not a defect the reviewer can see, but it is where the next layout change will go wrong.

## Evidence: Copilot evaluation

Eight prompts run headless against the real database, model `qwen2.5:7b-instruct`, temperature 0, `COPILOT_TOOLS_SCHEMA` at 25 tools.

| Prompt | Tool chosen | Select | Summary | Outcome |
|---|---|---|---|---|
| What is my net worth right now? | `get_current_net_worth` | 72.2s | 8.2s | Correct |
| How much did I spend on groceries this month? | `get_spending_by_category` with `category` | 52.0s | 15.2s | Failed, `TypeError`, no such argument |
| Show me my investment portfolio allocation and drift | `analyze_investments` | 48.2s | 64.2s | Ran, but reported 1131 positions and the summary contradicted the drift alerts |
| Create a new allocation strategy called 60/40 split | `set_active_allocation_profile` | 5.8s | 17.7s | Wrong tool, none exists that creates |
| Delete the allocation strategy Crypto Heavy | none | 70.2s | n/a | No tool exists, model said so in prose |
| What are my 10 most recent transactions? | `get_recent_transactions`, limit 10 | 4.1s | 51.6s | Correct |
| How much mortgage interest can I deduct this year? | `analyze_mortgage` | 3.4s | 32.0s | Ran, then quoted minor units as euros |
| What does Box 3 say about taxing actual returns? | `search_dutch_law_vault` | 7.1s | 100.3s | Correct citations, slow |

Three defects are visible in that table and are fixed by this spec.

1. **Minor units quoted as euros.** `analyze_mortgage` returns `interest_minor` 116696 and `balance_minor` 38627211 with no euro formatted twin. The model answered with a balance of 38,627,211 euros and monthly interest of 116,696 euros for a 396,000 euro loan. The values are correct; the presentation is off by a factor of one hundred (source: direct tool call, recorded in this evaluation).
2. **A tool that rejects its own schema.** `tool_get_spending_by_category(year, month)` has no `category` argument, but the question "how much did I spend on groceries" needs one, so the model invented it and `execute_tool` passed it straight into the function. The result was a friendly error where an answer belonged. Both halves are fixable: add the filter, and stop passing keys the function does not declare.
3. **One thousand one hundred thirty one positions.** `analyze_investments` counts rows of the consolidated holdings frame, which has one row per lot and per copied trader. The UI has the same problem in its holdings table. The assistant also told the user the portfolio had "no significant drift" in the same breath as a tool result naming two buckets over their band, which is a prompt problem: the drift alert is in the payload but not in the message the model is asked to summarise.

Latency has the same shape for two separate reasons. The first call of the process cost 72 seconds and later calls cost 3 to 7 seconds, which is Ollama loading a 4.7 GB model on demand; `chat_with_tools` and `generate_stream` never set `keep_alive`, so the model can be unloaded between turns. Separately, summary generation ranged from 8 to 100 seconds, driven by payload size (the investments result includes fifteen positions with eleven fields each) and by there being no output cap. Trimming the tool list cuts prefill tokens, capping summary length cuts the tail, and `keep_alive` removes the cold start.

## Evidence: cross check and what it changed

A read only critique pass read the drafted spec against the code and returned sixteen decision completeness gaps and seven soundness findings. Eight changed the design and were applied before acceptance:

1. Location resolves only from a counterparty IBAN through a new service query, with no currency fallback. The fallback would have made every merchant resolve, so the conditional column could never hide, which contradicts the intent and the data reality recorded above.
2. The holdings aggregation reads the `v_holdings` frame rather than the consolidated frame, because only the former carries `quantity` and cost basis. The consolidation frame has thirteen columns and no quantity at all, so the acceptance criterion was not buildable as originally written.
3. Average open price is computed per currency rule instead of dividing a mixed currency cost by quantity.
4. The tool argument contract was pinned down (bucket keyed percent map between 0 and 100 at one decimal, exact name match ignoring case, drift band 0 to 100, include cash false, rounded sum within 0.1 with the actual sum named), because the model, not a human, produces these arguments and an ambiguous contract becomes a silent bad write.
5. A delete needs a one time confirmation token, because the model makes both the request and the follow up call, so a plain `confirm: true` is something the model can set on its own. The stale `agent/AGENTS.md` line about read only connections is corrected at the same time.
6. The schema trim is defined as safe only (merge the two overlapping knowledge base tools, drop only what no quick action, test, or prompt reaches), because sidebar quick actions and the test suite reach tools that a naive trim would remove.
7. The prompt evaluation became a committed fixture with the model mocked, since a live model at temperature 0 is not a deterministic assertion, and the live run belongs in manual verification.
8. The masking boundary became one rule (mask everything derived from personal cost, value, or quantity, keep public market data), because the old wording left average open price, personal percentages, and asset counts undecided.

Two more findings were accepted as pure text corrections to the spec: the exchange example in the acceptance criteria (`XETR:`, not `EURONEXT:`) and widening the minor unit audit to every tool payload rather than the mortgage tool alone. One finding was rejected after checking the code: the claim that the KPI height fix would miss the delta cards, since `kpi_card` renders through `st.metric` and the live measurement of 104 against 118 pixels was taken on those exact elements.

## Evidence: data availability for the merchant panel

The merchants panel depends on data that is thinner than it looks. Counted across both databases:

| Field | `data/demo.db` (535 rows) | `data/finance.db` (677 rows) |
|---|---|---|
| `merchant_normalized` | 535 | 677 |
| | `counterparty_name` | 535 | 619 |
| `counterparty_iban` | 165 | 0 |
| `mcc` | 0 | 0 |

So merchant, category, count, average, share, last date, and accounts all resolve on real data, while location depends on an IBAN that only the demo data carries, and merchant category codes are absent everywhere. That is why the spec makes the Location column conditional rather than permanent, and why location falls back to the account currency region before giving up.

## Evidence: existing allocation data

Both databases carry the same three profiles (`80/20 Core-Satellite` active on `asset_type`, `Global One-Fund` on `ticker`, `Asset Class & Cash Buffer` on `asset_class`), with targets stored per bucket. Nothing in the repository currently deletes a profile or inserts one from the app; the only management path is Settings, and it only sets a profile active. That is the gap this spec closes.
