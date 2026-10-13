"""Single shared date scope resolver.

The Copilot answer and the destination page both resolve their date range here,
so the number quoted in chat and the range the page shows cannot disagree (AC-3).
Presets resolve exactly as the filter widget always computed them.
"""

from __future__ import annotations

import calendar
import re
from datetime import date, timedelta
from typing import Any

from services.fiscal_service import get_fiscal_month_for_date, get_fiscal_month_range

PRESETS = [
    "Last 3 Months",
    "MTD",
    "Last Month",
    "YTD",
    "Last 12 Months",
    "All Time",
]

CUSTOM_PRESET = "Custom Range"

_WINDOW_RE = re.compile(r"(\d+)\s*(day|days|week|weeks|month|months)", re.IGNORECASE)


def _parse_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            from datetime import datetime

            return datetime.strptime(text[:10], fmt).date()
        except ValueError:
            continue
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _shift_years(d: date, years: int) -> date:
    try:
        return d.replace(year=d.year - years)
    except ValueError:  # Feb 29 -> Feb 28
        return d.replace(year=d.year - years, day=28)


def resolve_preset(preset: str, today: date) -> dict[str, Any]:
    start: date | None = today
    end: date = today
    if preset == "MTD":
        start = today.replace(day=1)
    elif preset == "Last Month":
        first_this_month = today.replace(day=1)
        prev_month_end = first_this_month - timedelta(days=1)
        start = prev_month_end.replace(day=1)
        end = prev_month_end
    elif preset == "Last 3 Months":
        start = today - timedelta(days=90)
    elif preset == "YTD":
        start = today.replace(month=1, day=1)
    elif preset == "Last 12 Months":
        start = today - timedelta(days=365)
    elif preset == "All Time":
        start = None
    return {"preset": preset, "start": start, "end": end}


def resolve_window(days: int, today: date) -> dict[str, Any]:
    days = max(1, int(days))
    return {"preset": None, "start": today - timedelta(days=days), "end": today}


def resolve_explicit_range(start_val: Any, end_val: Any, today: date) -> dict[str, Any]:
    start = _parse_date(start_val)
    end = _parse_date(end_val)
    if start is None or end is None:
        return {"error": "Provide both a start and an end date, for example 2026-01-01 to 2026-03-31."}

    # Most recent past occurrence: walk whole years back while the start is in the future.
    guard = 0
    while start > today and guard < 100:
        start = _shift_years(start, 1)
        end = _shift_years(end, 1)
        guard += 1

    # A named month range ends at that month end.
    if end.day == 1:
        end = end.replace(day=calendar.monthrange(end.year, end.month)[1])

    # Clamp a range that reaches into the future.
    if end > today:
        end = today

    if start > end:
        return {"error": "The start date is after the end date. Please give an earlier start."}
    return {"preset": None, "start": start, "end": end}


def resolve_date_scope(date_scope: Any = None, today: date | None = None) -> dict[str, Any]:
    """Resolve a requested scope into {requested, preset, start, end, start_iso, end_iso, label, error}.

    `today` is injectable so tests are deterministic.
    """
    today = today or date.today()

    result: dict[str, Any]
    requested = date_scope is not None and date_scope != "" and date_scope != {}

    if not requested:
        result = {"preset": None, "start": None, "end": today}
        label = "all time"
    elif isinstance(date_scope, str):
        text = date_scope.strip()
        if text in PRESETS:
            result = resolve_preset(text, today)
            label = text
        else:
            match = _WINDOW_RE.search(text)
            if match:
                n = int(match.group(1))
                unit = match.group(2).lower()
                if unit.startswith("week"):
                    n *= 7
                elif unit.startswith("month"):
                    n *= 30
                result = resolve_window(n, today)
                label = text
            else:
                return _error(f'I did not understand the date scope "{text}". Try a preset like Last 3 Months, or a range such as 2026-01-01 to 2026-03-31.')
    elif isinstance(date_scope, dict):
        if "error" in date_scope:
            return _error(str(date_scope["error"]))
        preset = date_scope.get("preset")
        if preset in PRESETS:
            result = resolve_preset(preset, today)
            label = preset
        elif date_scope.get("start") is not None and date_scope.get("end") is not None:
            result = resolve_explicit_range(date_scope["start"], date_scope["end"], today)
            label = f"{result.get('start')} to {result.get('end')}" if "error" not in result else ""
        elif any(k in date_scope for k in ("days", "window_days", "window")):
            n = date_scope.get("days") or date_scope.get("window_days") or date_scope.get("window")
            result = resolve_window(int(n), today)
            label = f"last {n} days"
        else:
            return _error('A date scope needs a preset name or a start and end date, for example {"preset": "Last Month"}.')
    else:
        return _error("Unsupported date scope input.")

    if "error" in result:
        return result

    start = result.get("start")
    end = result.get("end") or today
    return {
        "requested": requested,
        "preset": result.get("preset"),
        "start": start,
        "end": end,
        "start_iso": start.isoformat() if start else None,
        "end_iso": end.isoformat(),
        "label": label,
        "error": None,
    }


def _error(message: str) -> dict[str, Any]:
    return {
        "requested": True,
        "preset": None,
        "start": None,
        "end": None,
        "start_iso": None,
        "end_iso": None,
        "label": "",
        "error": message,
    }


def is_aligned_fiscal_month(start: date | None, end: date | None, salary_day: int) -> str | None:
    """Return the fiscal month key when [start, end] is exactly one fiscal month, else None."""
    if start is None or end is None or start > end:
        return None
    fm_start = get_fiscal_month_for_date(start, salary_day)
    fm_end = get_fiscal_month_for_date(end, salary_day)
    if fm_start != fm_end:
        return None
    y, m = map(int, fm_start.split("-"))
    fs, fe = get_fiscal_month_range(y, m, salary_day)
    if start == fs and end == fe:
        return fm_start
    return None


def spending_view_for_scope(
    resolved: dict[str, Any],
    salary_day: int,
) -> dict[str, Any]:
    """Map a resolved scope to the Spending page View Scope (AC-5).

    Returns {option, caption, header}. `option` matches a key in the page selectbox;
    `caption` is a "Custom range" note for a non aligned explicit range.
    """
    start = resolved.get("start")
    end = resolved.get("end")
    preset = resolved.get("preset")

    aligned = is_aligned_fiscal_month(start, end, salary_day)
    if aligned:
        return {"option": aligned, "caption": None, "header": None}

    if start is None:
        return {"option": "All Months (Monthly Average)", "caption": None, "header": None}

    if preset in ("MTD", "Last Month", "Last 3 Months", "YTD", "Last 12 Months"):
        label = preset
    elif preset:
        label = "All Months (Monthly Average)"
    else:
        label = "Custom range"
        return {
            "option": "All Months (Monthly Average)",
            "caption": f"Custom range: {start.isoformat()} to {end.isoformat()}",
            "header": f"{start.isoformat()} to {end.isoformat()}",
        }
    return {"option": "All Months (Monthly Average)", "caption": None, "header": label}
