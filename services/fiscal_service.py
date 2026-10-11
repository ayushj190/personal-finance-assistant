import calendar
from datetime import date, timedelta
import sqlite3
from typing import Any

from db import database


def get_default_salary_day(conn: sqlite3.Connection) -> int:
    """Detect default salary day based on largest salary transaction in past 2 months."""
    try:
        max_row = conn.execute("SELECT MAX(booking_date) as max_date FROM transactions").fetchone()
        ref_date = max_row["max_date"] if max_row and max_row["max_date"] else date.today().isoformat()

        row = conn.execute(
            """
            SELECT t.booking_date, t.amount_eur_minor
            FROM transactions t
            JOIN categories c ON c.id = t.category_id
            WHERE c.name = 'Salary'
              AND t.amount_eur_minor > 0
              AND t.booking_date >= date(?, '-2 month')
            ORDER BY t.amount_eur_minor DESC, t.booking_date DESC
            LIMIT 1
            """,
            (ref_date,),
        ).fetchone()

        if not row:
            row = conn.execute(
                """
                SELECT t.booking_date, t.amount_eur_minor
                FROM transactions t
                JOIN categories c ON c.id = t.category_id
                WHERE c.name = 'Salary'
                  AND t.amount_eur_minor > 0
                ORDER BY t.amount_eur_minor DESC, t.booking_date DESC
                LIMIT 1
                """
            ).fetchone()

        if row and row["booking_date"]:
            parts = str(row["booking_date"]).split("-")
            if len(parts) >= 3:
                day = int(parts[2][:2])
                return max(1, min(31, day))
    except Exception:
        pass
    return 1


def get_fiscal_salary_day(conn: sqlite3.Connection) -> int:
    """Return user-configured fiscal salary day, defaulting to detected payday."""
    val = database.get_setting(conn, "fiscal_salary_day")
    if val is not None and str(val).strip().isdigit():
        day = int(str(val).strip())
        if 1 <= day <= 31:
            return day
    return get_default_salary_day(conn)


def set_fiscal_salary_day(conn: sqlite3.Connection, day: int) -> None:
    """Save user-configured fiscal salary day."""
    day = max(1, min(31, int(day)))
    database.set_setting(conn, "fiscal_salary_day", str(day))


def get_fiscal_month_range(year: int, month: int, salary_day: int) -> tuple[date, date]:
    """Calculate start and end dates for a fiscal month cycle."""
    if salary_day <= 1:
        last_d = calendar.monthrange(year, month)[1]
        return date(year, month, 1), date(year, month, last_d)

    start_d = min(salary_day, calendar.monthrange(year, month)[1])
    start_date = date(year, month, start_d)

    next_y = year if month < 12 else year + 1
    next_m = month + 1 if month < 12 else 1
    next_start_d = min(salary_day, calendar.monthrange(next_y, next_m)[1])
    end_date = date(next_y, next_m, next_start_d) - timedelta(days=1)
    return start_date, end_date


def get_fiscal_month_for_date(d: date | str, salary_day: int) -> str:
    """Return fiscal month key 'YYYY-MM' for a transaction date."""
    if isinstance(d, str):
        d = date.fromisoformat(str(d)[:10])

    if salary_day <= 1:
        return f"{d.year:04d}-{d.month:02d}"

    if d.day >= salary_day:
        return f"{d.year:04d}-{d.month:02d}"
    else:
        prev_y = d.year if d.month > 1 else d.year - 1
        prev_m = d.month - 1 if d.month > 1 else 12
        return f"{prev_y:04d}-{prev_m:02d}"


def format_fiscal_month_label(month_str: str, salary_day: int) -> str:
    """Format fiscal month for UI selectors, showing date span."""
    if not month_str or month_str == "All Months (Monthly Average)":
        return str(month_str)
    try:
        y, m = map(int, month_str.split("-"))
        s_d, e_d = get_fiscal_month_range(y, m, salary_day)
        if salary_day <= 1:
            return f"{month_str} ({s_d.strftime('%b %Y')})"
        return f"{month_str} ({s_d.strftime('%d %b')} – {e_d.strftime('%d %b')})"
    except Exception:
        return str(month_str)
