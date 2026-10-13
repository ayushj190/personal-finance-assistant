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

_NAV_VERB_RE = re.compile(
    r"^(?:open|go to|goto|navigate to|take me to|switch to|show me|show my|show|view|display)\b",
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
    return {
        "page": page,
        "tab": tab,
        "date_scope": {"preset": preset} if preset else None,
        "source": "fast_path",
    }
