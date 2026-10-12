# 0014. System cleanup, architecture hardening and showcase readiness

**Date**: 2026-10-12
**Status**: In Progress

## Summary

The code has grown to about 22 thousand lines, and agents now struggle to change it safely. Money conversions are copied by hand in 110 places, 48 errors are silently ignored, and three files are over 1000 lines. This slice gives money one home (a `Money` type), splits the three giant files into small focused modules, gives session state one typed home, and makes failures visible through logging. It also adds a demo mode backed by a fake but realistic profile, a visual consistency pass on every page, and a README showcase, so you can safely take screenshots for LinkedIn.

## Requirements

**User stories**:
- As the owner, I want every money value to flow through one tested type, so totals can never drift between pages.
- As an AI agent editing this repo, I want small modules with one job and one obvious place for state and money, so that a small change touches one file.
- As the owner, I want a demo mode with realistic fake data, so I can share screenshots without exposing my real finances.
- As a recruiter viewing the repo, I want a README that shows the product, the architecture and the product decisions behind it.

**Acceptance criteria**:

Track A, code health
- **AC-1**: `money.py` (repo root, next to `config.py`) defines a frozen `Money(cents: int, currency: str = "EUR")`. Every cents to major unit conversion in `ui/`, `services/`, `agent/` and `db/` goes through it. A grep for `/ 100` and `/100` in those folders returns only percentage math, and each such line carries a `# pct` comment.
- **AC-2**: `ui/components.format_money` accepts `Money` (or `int` cents through `Money.from_cents`). The float path is removed once no callers use it. Privacy masking behaves as it does today.
- **AC-3**: `agent/tools.py`, `ui/charts.py` and `ui/pages/investments.py` become packages, with no module over 400 lines. Every existing import path (`from agent.tools import X`, `from ui.charts import X`, `ui.pages.investments.render`) keeps working through `__init__.py` re exports.
- **AC-4**: `ui/state.py` is the only module that defines session state key strings. No other file uses a raw string literal key with `st.session_state[...]`, `.get(...)` or `in st.session_state`.
- **AC-5**: Zero `except Exception: pass` (or bare `except:`) remain. Each one is narrowed to a specific exception, or logs through `logging.getLogger(__name__)` with `exc_info=True`. Logging is configured once in `app.py` and writes to the console plus a rotating file at `data/logs/app.log`.
- **AC-6**: All tests pass after every build plan step, including the existing all pages AppTest smoke test from spec 0008 (AC-10). Test count never drops, except when duplicate tests are merged on purpose.

Track B, showcase
- **AC-7**: `run.bat --demo` sets `PFA_DEMO=1`. `config.DB_PATH` then resolves to `data/demo.db` and `finance.db` and `vault.bin` are never opened. The sidebar shows a `DEMO` badge, and background bank sync plus credential prompts are disabled.
- **AC-8**: `scripts/seed_demo.py` builds `data/demo.db` deterministically (fixed seed 42, dates relative to today). The profile is a young professional in Amsterdam: EUR salary, ABN AMRO current account plus Revolut, an eToro portfolio of about 12 real tickers, a mortgage, 18 months of categorized transactions, budgets, and at least 3 closed positions. `run.bat --demo` seeds the database if it is missing. Running the script with `--reset` rebuilds it.
- **AC-9**: In demo mode every page (Dashboard, Spending, Transactions, Investments, Mortgage, Tax, Import Files, Settings, Copilot sidebar) renders with populated charts. There are no Python exceptions and no Streamlit warnings in the console, in both light and dark theme.
- **AC-10**: The visual consistency pass gives each page the same components: `kpi_card` (fixed height token), `empty_state(icon, title, body, action_label=None)` and `skeleton(rows)`. They live in `ui/components.py`, with heights and spacing taken from tokens in `ui/theme/common.css`. No page keeps its own inline `style=` for card layout.
- **AC-11**: `README.md` gains a hero image or GIF slot (captured from demo mode), a Mermaid architecture diagram (UI → services → db, agent with its read only authorizer, connectors), and a "Product decisions" section of 5 to 8 entries. Each entry gives the problem, the choice, the tradeoff and a link to the spec.

## Decision

**Chosen option**: Option 2, fix in place along shared seams, with a strangler migration per seam.

Add the shared seams first (`money.py`, `ui/state.py`, logging, demo config). Prove them end to end on the Dashboard, then migrate the remaining callers and split the giant files behind unchanged import paths.

## Rationale

See [rationale.md](rationale.md).

## Feature design

**Data model**: no schema change. Database columns stay integer cents (root `AGENTS.md` rule). `Money` exists only in Python.

**`money.py` contract**:
```python
@dataclass(frozen=True, slots=True)
class Money:
    cents: int
    currency: str = "EUR"
    @classmethod
    def from_cents(cls, cents: int | None, currency="EUR") -> "Money"   # None → 0
    @classmethod
    def from_major(cls, value: str | Decimal | float, currency="EUR") -> "Money"  # Decimal, ROUND_HALF_UP
    def to_major(self) -> float          # presentation boundary only (charts, format)
    __add__/__sub__/__neg__/__abs__      # same currency, else ValueError
    __mul__(int | Decimal)               # result rounded ROUND_HALF_UP
    __lt__/__eq__ ...                    # same currency, else ValueError
def sum_money(items, currency="EUR") -> Money
```
- Parsers and form inputs use `from_major`. Repositories return int cents. Services return `Money` or int cents (never floats). The UI calls `format_money(m)`, and charts call `m.to_major()`.
- `Money` comes with one self check test file, `tests/test_money.py` (rounding, currency mismatch, None, negative values).

**Package splits** (AC-3). Targets, which `/develop` may adjust if a file's real seams differ:
| Old file | New package modules |
|---|---|
| `agent/tools.py` | `agent/tools/__init__.py` (dispatch map plus re exports), `net_worth.py`, `investments.py`, `spending.py`, `tax.py`, `legal.py`, `imports.py`, `market.py` |
| `ui/charts.py` | `ui/charts/__init__.py`, `common.py` (layout and palette helpers), `sankey.py`, `portfolio.py`, `spending.py`, `trajectory.py` |
| `ui/pages/investments.py` | `ui/pages/investments/__init__.py` (`render`), `holdings.py`, `exposure.py`, `realized_pnl.py`, `watchlist.py`, `news.py`, `tabs.py` |
- Move code as is first, in a commit of its own, with no behavior change. Clean up afterwards.
- `mock.patch` targets must point at the submodule that looks up the name. For example, `ui.pages.investments.kpi_card` becomes `ui.pages.investments.holdings.kpi_card`, because patching a package re export does not affect the submodule. Update the targets in the same commit, for all three packages (known cases: `tests/test_investments_holdings.py` patches `DB_PATH`, `kpi_card`, `is_hidden` and `update_quotes`). After each split, check that each patched test still fails when its mock is removed.
- `app.py` registers pages by callable (`st.Page(investments.render)`), so a package exposing `render` from `__init__.py` is safe.

**`ui/state.py`** (AC-4):
```python
class K:  # namespaced constants, grouped by owner
    PRIVACY_HIDDEN = "global.privacy_hidden"
    COPILOT_MESSAGES = "copilot.messages"
    ...
def get(key: str, default=None): ...
def set(key: str, value) -> None: ...
def init_defaults() -> None  # called once in app.py, replaces scattered setdefault calls
```
- Keep existing key string values when renaming would break widget `key=` bindings. The constant name changes, the value can stay.

**Logging** (AC-5): `logging_setup.configure()` lives in `app.py` before page routing. It uses a `RotatingFileHandler` (1 MB, 3 backups) at `data/logs/app.log` plus a stderr handler. Level comes from `PFA_LOG_LEVEL` (default `INFO`). The 9 `print(` calls in `connectors/etoro_service.py` and `services/llm_client.py` switch to the logger. Logs never contain amounts, IBANs or credentials (local first rule).

**Demo mode** (AC-7, AC-8):
- `config.py` gains `DEMO = os.environ.get("PFA_DEMO") == "1"` and `DB_PATH = DATA_DIR / ("demo.db" if DEMO else "finance.db")`. Everything already reads `config.DB_PATH`.
- `run.bat`: if the first argument is `--demo`, set `PFA_DEMO=1`, run `scripts\seed_demo.py` when `data\demo.db` is missing, then start Streamlit.
- The seed script runs the normal migrations through `db.database.connect()`, then inserts through the existing repositories or database helpers (no raw SQL that skips invariants).
- Market quotes for the 12 tickers may refresh live. If the network fails, seeded prices stay.

**Value sourcing**:
| Action | Value | Source |
|---|---|---|
| Any money display | formatted string | `Money` from repo int cents → `format_money` |
| Demo dates | transaction dates | `date.today()` minus offsets, seed 42 |
| Demo prices | holding price | seeded `holdings` row, then optional live quote |
| Demo badge | visibility | `config.DEMO` |
| Log level | level | `PFA_LOG_LEVEL` env, default `INFO` |

**Key invariants**: money is never a float outside `to_major()` and `format_money`. Demo mode never touches `finance.db` or `vault.bin`. Public import paths never break.

**Security model**: no change to the copilot's read only authorizer (spec 0007). Demo mode skips the keyring and the vault entirely.

**Configuration required**:
- `PFA_DEMO`: `1` switches to `data/demo.db` and demo behavior.
- `PFA_LOG_LEVEL`: optional, default `INFO`.

**Critical test scenarios**:
- `Money` rounding, mismatch and None cases, verifies **AC-1**, **AC-2**
- `format_money(Money(123456))` gives `€1,234.56`, and gives `€****` when hidden, verifies **AC-2**
- Every old import path still resolves (a parametrized import test), verifies **AC-3**
- With `PFA_DEMO=1`, `config.DB_PATH.name == "demo.db"`, verifies **AC-7**
- Seeding twice with `--reset` gives an identical row count and an identical net worth, verifies **AC-8**
- The existing all pages AppTest smoke test passes on a seeded demo database, verifies **AC-6**, **AC-9**

## Build plan

Tracer Bullet: first wire one thin thread (Dashboard) through every new seam, then widen it. Run `python run_tests.py` after every step and commit each step on its own.

0. Precondition: commit the 20 uncommitted files so the slice starts from a clean baseline (owner).
1. Add `money.py` and `tests/test_money.py`. Make `format_money` accept `Money` and int cents, keeping the float path for now. Satisfies **AC-1**, **AC-2**
2. Add the demo config switch, `scripts/seed_demo.py` and the `run.bat --demo` flag, plus the sidebar `DEMO` badge and sync guard. Satisfies **AC-7**, **AC-8**
3. Add logging setup in `app.py` and replace the `print(` calls. Satisfies **AC-5**
4. Add `ui/state.py` with `K` constants and `init_defaults()`. Satisfies **AC-4**
5. Tracer: migrate `ui/pages/dashboard.py` end to end (Money, state keys, narrowed errors, `kpi_card` and `empty_state`), and check it in demo mode. Satisfies **AC-1**, **AC-4**, **AC-5**, **AC-10**
6. Split `agent/tools.py` into a package: move first, then migrate it to Money. Satisfies **AC-3**, **AC-1**
7. Split `ui/charts.py` into a package. Satisfies **AC-3**
8. Split `ui/pages/investments.py` into a package and migrate it. Satisfies **AC-3**, **AC-1**, **AC-4**, **AC-10**
9. Migrate the remaining pages, services, `db/models.py`, repositories and dialogs to Money, state keys and narrowed errors. Remove the float path from `format_money`. Satisfies **AC-1**, **AC-2**, **AC-4**, **AC-5**
10. Visual consistency pass on every page in light and dark themes, using the demo data. Satisfies **AC-9**, **AC-10**
11. README showcase: Mermaid diagram, Product decisions, and the hero slot (the owner captures the image or GIF from demo mode). Satisfies **AC-11**

## Migration plan

**Strategy**: strangler per seam. The new seam exists alongside the old pattern, callers move one page at a time, and the old path is deleted last (step 9).
**Rollback**: every step is its own commit, so `git revert` undoes any one step.
**Risks**: package splits can break `mock.patch("agent.tools.X")` targets, so step 6 fixes patch targets in the same commit. Renamed state keys can reset widgets, so the key string values stay unchanged.

## Consequences

**Positive**: one place each for money, state and logging, so agents edit one file per change. Small modules fit in an agent's context. Silent failures become visible. Demo mode makes screenshots safe.
**Negative / tradeoffs**: a large diff touching most files, with the existing 202 tests as the only safety net (you chose no new golden number tests). Pages without coverage can regress quietly. The `Money` wrapper adds a little ceremony at chart boundaries.
**Neutral**: no schema change. Import paths are preserved. `data/demo.db` and `data/logs/` must be gitignored.

## Follow-up

- [ ] Add `data/demo.db` and `data/logs/` to `.gitignore` (step 2).
- [ ] Optional later: golden number tests (net worth, budget totals, realized P&L) on the demo database. You declined them for now, and they are cheap once the seed exists.
- [ ] Optional later: ruff, pyright and architecture guard tests (no SQL in pages, file size cap) to keep this slice's gains from eroding.
- [ ] `/sync` after done: record the `money.py`, `ui/state.py`, logging and demo mode conventions in the root and area `AGENTS.md` files. This is what keeps future agents from regressing.
