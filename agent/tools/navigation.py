"""Copilot `open_view` action tool.

The model may choose a destination page, a tab, and a date scope. Every value is
checked against a whitelist and the tool only sets a session intent on the task,
never touching SQL (AC-1, AC-2, AC-18).
"""

from __future__ import annotations

from typing import Any

from services.date_scope import resolve_date_scope
from services.navigation import (
    FILTERED_PAGES,
    PAGE_IDS,
    PAGE_LABELS,
    TAB_HOST_PAGE,
    TAB_MAP,
)


def tool_open_view(
    page: str,
    tab: str | None = None,
    date_scope: Any = None,
) -> dict[str, Any]:
    """Open a page (and optional tab) with an optional date scope."""
    clean_page = str(page or "").strip().lower()
    if clean_page not in PAGE_IDS:
        return {
            "success": False,
            "message": (
                f"Unknown page '{page}'. Valid pages are: {', '.join(PAGE_IDS)}."
            ),
        }

    clean_tab: str | None = None
    if tab is not None and str(tab).strip():
        candidate = str(tab).strip().lower()
        if candidate not in TAB_MAP:
            return {
                "success": False,
                "message": (
                    f"Unknown tab '{tab}'. Valid tabs are: {', '.join(TAB_MAP)}."
                ),
            }
        if clean_page != TAB_HOST_PAGE:
            clean_tab = None
            note = f"Ignored the tab request because {PAGE_LABELS[clean_page]} has no tabs."
        else:
            clean_tab = candidate
            note = None
    else:
        note = None

    resolved = resolve_date_scope(date_scope)
    if resolved.get("error"):
        return {
            "success": False,
            "message": resolved["error"],
        }

    label = PAGE_LABELS[clean_page]
    if clean_tab:
        label = f"{label} › {TAB_MAP[clean_tab]}"

    scope_line = None
    if resolved["requested"]:
        if clean_page not in FILTERED_PAGES:
            page_note = f"{PAGE_LABELS[clean_page]} has no date scope, so I only opened the page."
            note = f"{note} {page_note}".strip() if note else page_note
        else:
            scope_line = f"Applied scope: {resolved['start_iso']} to {resolved['end_iso']}"

    intent = {
        "page": clean_page,
        "tab": clean_tab,
        "date_scope": {
            "preset": resolved.get("preset"),
            "start_iso": resolved.get("start_iso"),
            "end_iso": resolved.get("end_iso"),
            "requested": resolved.get("requested"),
        },
        "source": "open_view",
    }

    message = f"Opened {label}."
    if scope_line:
        message = f"{message} {scope_line}."
    if note:
        message = f"{message} {note}"

    return {
        "success": True,
        "page": clean_page,
        "tab": clean_tab,
        "date_scope": intent["date_scope"],
        "note": note,
        "ui_intent": intent,
        "message": message,
    }
