"""Copilot `open_view` action tool.

The model may choose a destination page, a tab, a date scope, and validated view
parameters. Every value is checked against a whitelist and the tool only sets a
session intent on the task, never touching SQL (AC-1, AC-2, AC-18).
"""

from __future__ import annotations

from typing import Any

from config import DB_PATH
from db import database
from services.date_scope import resolve_date_scope
from services.navigation import (
    EXPOSURE_DIMENSIONS,
    FILTERED_PAGES,
    MOVERS,
    PAGE_IDS,
    PAGE_LABELS,
    SORT_COLUMNS,
    TAB_HOST_PAGE,
    TAB_MAP,
    VIEW_WHITELIST,
)
from services.portfolio import get_consolidated_holdings_df, get_dimension_exposure_df


def _live_focus_buckets(dimension: str) -> set[str]:
    """Return the live buckets `get_dimension_exposure_df` reports, or empty on any error."""
    try:
        conn = database.connect_readonly(DB_PATH)
    except Exception:
        return set()
    try:
        df = get_consolidated_holdings_df(conn)
    except Exception:
        return set()
    finally:
        conn.close()
    if df is None or df.empty:
        return set()
    try:
        exposure = get_dimension_exposure_df(df, dimension)
    except Exception:
        return set()
    return {str(b) for b in exposure["bucket"].tolist()}


def _clean_view(page: str, view: Any) -> tuple[dict[str, Any], list[str]]:
    """Validate a `view` object against the page whitelist, ignoring the rest (AC-2)."""
    allowed = VIEW_WHITELIST.get(page, ())
    cleaned: dict[str, Any] = {}
    notes: list[str] = []
    if not isinstance(view, dict) or not view:
        return cleaned, notes

    def _as_text(raw: Any) -> str:
        return raw.strip() if isinstance(raw, str) else str(raw or "").strip()

    # The exposure dimension is resolved first so a focus value can be checked
    # against its live buckets.
    for key in ("exposure_dimension", "focus", "sort", "movers", "category", "search"):
        if key not in view:
            continue
        if key not in allowed:
            notes.append(f"Ignored unknown view option '{key}' for {PAGE_LABELS[page]}.")
            continue
        value = _as_text(view[key])
        if not value:
            continue
        if key == "exposure_dimension":
            match = next(
                (d for d in EXPOSURE_DIMENSIONS if d.lower() == value.lower()), None
            )
            if not match:
                notes.append(
                    f"Ignored exposure dimension '{value}'; valid are "
                    f"{', '.join(EXPOSURE_DIMENSIONS)}."
                )
                continue
            cleaned[key] = match
        elif key == "focus":
            dim = cleaned.get("exposure_dimension")
            if not dim:
                notes.append("Ignored focus because no valid exposure dimension was set.")
                continue
            buckets = _live_focus_buckets(dim)
            match = next((b for b in buckets if b.lower() == value.lower()), None)
            if not match:
                notes.append(f"Ignored focus '{value}'; it is not a live {dim} bucket.")
                continue
            cleaned[key] = match
        elif key == "sort":
            match = next((s for s in SORT_COLUMNS if s.lower() == value.lower()), None)
            if not match:
                notes.append(
                    f"Ignored sort column '{value}'; valid are {', '.join(SORT_COLUMNS)}."
                )
                continue
            cleaned[key] = match
        elif key == "movers":
            match = next((m for m in MOVERS if m.lower() == value.lower()), None)
            if not match:
                notes.append(
                    f"Ignored movers option '{value}'; valid are {', '.join(MOVERS)}."
                )
                continue
            cleaned[key] = match
        else:
            cleaned[key] = value

    return cleaned, notes


def tool_open_view(
    page: str,
    tab: str | None = None,
    date_scope: Any = None,
    view: Any = None,
) -> dict[str, Any]:
    """Open a page (and optional tab) with an optional date scope and view parameters."""
    clean_page = str(page or "").strip().lower()
    if clean_page not in PAGE_IDS:
        return {
            "success": False,
            "message": (
                f"Unknown page '{page}'. Valid pages are: {', '.join(PAGE_IDS)}."
            ),
        }

    clean_tab: str | None = None
    notes: list[str] = []
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
            notes.append(
                f"Ignored the tab request because {PAGE_LABELS[clean_page]} has no tabs."
            )
        else:
            clean_tab = candidate

    resolved = resolve_date_scope(date_scope)
    if resolved.get("error"):
        return {
            "success": False,
            "message": resolved["error"],
        }

    clean_view, view_notes = _clean_view(clean_page, view)
    notes.extend(view_notes)

    label = PAGE_LABELS[clean_page]
    if clean_tab:
        label = f"{label} › {TAB_MAP[clean_tab]}"

    scope_line = None
    if resolved["requested"]:
        if clean_page not in FILTERED_PAGES:
            notes.append(
                f"{PAGE_LABELS[clean_page]} has no date scope, so I only opened the page."
            )
        else:
            scope_line = f"Applied scope: {resolved['start_iso']} to {resolved['end_iso']}"

    intent = {
        "page": clean_page,
        "tab": clean_tab,
        "date_scope": {
            "requested": resolved.get("requested"),
            "preset": resolved.get("preset"),
            "start_iso": resolved.get("start_iso"),
            "end_iso": resolved.get("end_iso"),
        },
        "view": clean_view,
        "source": "open_view",
    }

    message = f"Opened {label}."
    if scope_line:
        message = f"{message} {scope_line}."
    if notes:
        message = f"{message} {' '.join(notes)}"

    return {
        "success": True,
        "page": clean_page,
        "tab": clean_tab,
        "date_scope": intent["date_scope"],
        "view": clean_view,
        "note": " ".join(notes) or None,
        "ui_intent": intent,
        "message": message,
    }
