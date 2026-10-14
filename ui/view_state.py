"""Apply validated Copilot view parameters to the destination page session keys.

The Copilot's `open_view` sets a whitelisted `view` object on the intent; this maps
each (page, view key) to the page's own session key so the page renders shaped to
the question (AC-2). A value not whitelisted for the page never reaches here.
"""

from __future__ import annotations

from typing import Any

from ui import state

_VIEW_SESSION_KEYS: dict[tuple[str, str], str] = {
    ("spending", "category"): "spending_category",
    ("transactions", "category"): "tx_category",
    ("transactions", "search"): "tx_search",
    ("investments", "exposure_dimension"): state.K.INVESTMENTS_EXP_DIM,
    ("investments", "focus"): state.K.INVESTMENTS_EXP_FOCUS,
}


def apply_view(page: str, view: Any) -> None:
    """Write each validated view value into its page session key."""
    if not isinstance(view, dict):
        return
    for key, value in view.items():
        session_key = _VIEW_SESSION_KEYS.get((page, key))
        if session_key is not None and value not in (None, ""):
            state.set(session_key, value)
