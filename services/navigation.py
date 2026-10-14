"""Navigation constants and the deterministic fast path router.

One place defines the page whitelist, the tab whitelist, and the set of filtered
pages, so the Copilot tool, the app, and the tests all read the same truth
(AC-1, AC-4, AC-18, AC-21).
"""

from __future__ import annotations

import re
from typing import Any

# Canonical page ids, in navigation order.
PAGE_IDS = [
    "dashboard",
    "spending",
    "investments",
    "mortgage",
    "transactions",
    "tax",
    "settings",
]

PAGE_LABELS = {
    "dashboard": "Dashboard",
    "spending": "Spending",
    "investments": "Investments",
    "mortgage": "Mortgage",
    "transactions": "Transactions",
    "tax": "Tax Analysis",
    "settings": "Settings",
}

# Pages that carry a date filter. Exactly these two (AC-4).
FILTERED_PAGES = ("spending", "transactions")

# Tab ids to the exact Investments tab labels (AC-2).
TAB_MAP = {
    "portfolio": "📊 Portfolio & Holdings",
    "allocation": "⚖️ Allocation & Drift",
    "income_tax": "💰 Income & Tax Strategy",
    "goals": "🎯 Goals & Planning",
}

# The page that owns the tabs above.
TAB_HOST_PAGE = "investments"

# Phrase aliases that resolve to a page id.
PAGE_ALIASES = {
    "dashboard": "dashboard",
    "home": "dashboard",
    "overview": "dashboard",
    "spending": "spending",
    "expenses": "spending",
    "investments": "investments",
    "investment": "investments",
    "holdings": "investments",
    "portfolio": "investments",
    "mortgage": "mortgage",
    "transactions": "transactions",
    "transaction": "transactions",
    "ledger": "transactions",
    "tax": "tax",
    "tax analysis": "tax",
    "taxes": "tax",
    "settings": "settings",
    "preferences": "settings",
}

# Per page view parameter whitelist (AC-2). A key absent here cannot be set, so a
# wrong key can never reach a page. Values are validated per key by `open_view`.
VIEW_WHITELIST: dict[str, tuple[str, ...]] = {
    "spending": ("category",),
    "transactions": ("category", "search"),
    "investments": ("exposure_dimension", "focus"),
}

# Investments exposure dimensions the Copilot may set (AC-2). A `focus` value is
# validated against the live buckets `get_dimension_exposure_df` returns.
EXPOSURE_DIMENSIONS = ("Sector", "Region", "Currency", "Nature")

# Deterministic topic map: single high signal keywords per page (AC-6). Mirrors
# PAGE_ALIASES without the navigation only words (home, preferences), so a clear
# content question still lands right when the model forgot to call `open_view`.
TOPIC_KEYWORDS: dict[str, tuple[str, ...]] = {
    "investments": (
        "investments", "investment", "portfolio", "holdings", "exposure",
        "allocation", "stocks", "stock", "etfs", "etf", "dividend", "dividends",
        "sector", "ticker",
    ),
    "spending": (
        "spending", "spend", "expenses", "expense", "budget", "budgets",
        "subscriptions", "merchants",
    ),
    "mortgage": ("mortgage", "mortgages", "amortization", "repayment", "loan", "loans"),
    "tax": ("tax", "taxes", "box 1", "box 3", "jaarruimte", "deduction", "deductions"),
    "transactions": ("transactions", "transaction", "ledger", "uncategorized", "payee"),
    "dashboard": ("net worth", "balance sheet", "dashboard", "overview"),
}

# Phrase aliases that resolve to an Investments tab id.
TAB_ALIASES = {
    "portfolio": "portfolio",
    "holdings": "portfolio",
    "allocation": "allocation",
    "drift": "allocation",
    "rebalancing": "allocation",
    "rebalance": "allocation",
    "income": "income_tax",
    "income and tax": "income_tax",
    "tax strategy": "income_tax",
    "goals": "goals",
    "planning": "goals",
    "fire": "goals",
}

# Preset phrases the fast path can attach without the model.
_PRESET_PHRASES = {
    "this month": "MTD",
    "mtd": "MTD",
    "last month": "Last Month",
    "last 3 months": "Last 3 Months",
    "past 3 months": "Last 3 Months",
    "last three months": "Last 3 Months",
    "this year": "YTD",
    "year to date": "YTD",
    "ytd": "YTD",
    "last 12 months": "Last 12 Months",
    "past 12 months": "Last 12 Months",
    "last year": "Last 12 Months",
    "all time": "All Time",
}

# Explicit navigation verbs only (AC-6). The content verbs (show, view, display)
# are removed so a content question reaches the model and produces an answer.
_NAV_VERB_RE = re.compile(
    r"^(?:open|go to|goto|navigate to|take me to|switch to)\b",
    re.IGNORECASE,
)


def _find_phrase(text: str, mapping: dict[str, str]) -> str | None:
    # Longest alias first so "tax analysis" wins over "tax".
    for phrase in sorted(mapping, key=len, reverse=True):
        if re.search(rf"\b{re.escape(phrase)}\b", text):
            return mapping[phrase]
    return None


def match_fast_path(prompt: str) -> dict[str, Any] | None:
    """Return an intent for explicit navigation phrasing, else None (AC-21).

    Runs before the model, makes no model call, and returns the same shape as
    the `open_view` tool.
    """
    if not prompt or not isinstance(prompt, str):
        return None
    text = prompt.strip()
    if not _NAV_VERB_RE.match(text):
        return None

    page = _find_phrase(text, PAGE_ALIASES)
    tab = _find_phrase(text, TAB_ALIASES)

    if page == "investments" and tab:
        pass
    elif tab is not None and page is None:
        page = TAB_HOST_PAGE
    elif tab is not None and page == TAB_HOST_PAGE:
        pass
    else:
        tab = None

    if page is None:
        return None

    preset = _find_phrase(text, _PRESET_PHRASES)
    date_scope = {"requested": True, "preset": preset} if preset else None
    return {
        "page": page,
        "tab": tab,
        "date_scope": date_scope,
        "source": "fast_path",
    }


def topic_map_intent(prompt: str, date_scope: Any = None) -> dict[str, Any] | None:
    """Route a content question to exactly one page, or None when weak or tied (AC-6).

    Deterministic and model free. Runs after tool execution, only when no intent
    was captured, so a clear question still lands right when the model forgot to
    call `open_view`. A weak match or a two page tie stays silent.
    """
    if not prompt or not isinstance(prompt, str):
        return None
    text = prompt.lower()
    matches = [
        page
        for page, keywords in TOPIC_KEYWORDS.items()
        if any(re.search(rf"\b{re.escape(kw)}\b", text) for kw in keywords)
    ]
    if len(matches) != 1:
        return None

    from services.date_scope import resolve_date_scope

    scope = None
    if date_scope:
        resolved = resolve_date_scope(date_scope)
        if resolved.get("requested") and not resolved.get("error"):
            scope = {
                "requested": True,
                "preset": resolved.get("preset"),
                "start_iso": resolved.get("start_iso"),
                "end_iso": resolved.get("end_iso"),
            }

    return {
        "page": matches[0],
        "tab": None,
        "date_scope": scope,
        "source": "topic_map",
    }
