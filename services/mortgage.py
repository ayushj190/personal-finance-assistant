from datetime import date, datetime
import sqlite3
from typing import Any


def add_months(sourcedate: date, months: int) -> date:
    month = sourcedate.month - 1 + months
    year = sourcedate.year + month // 12
    month = month % 12 + 1
    day = min(sourcedate.day, 28)  # safe day for monthly schedule
    return date(year, month, day)


def calculate_mortgage_schedule(
    loan_type: str,
    principal_cents: int,
    start_date: date,
    term_months: int,
    # list of {from_date: date, annual_rate: float, fixed_until: date|None}
    rate_periods: list[dict[str, Any]],
    # list of {paid_date: date, amount_minor: int, recalc: str}
    extra_payments: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    schedule: list[dict[str, Any]] = []
    if principal_cents <= 0 or term_months <= 0:
        return schedule

    sorted_rates = sorted(
        rate_periods, key=lambda x: x["from_date"]) if rate_periods else []
    current_rate = sorted_rates[0]["annual_rate"] if sorted_rates else 0.0385

    extras_by_date = {}
    for ep in extra_payments:
        d = ep["paid_date"]
        if isinstance(d, str):
            d = datetime.strptime(d[:10], "%Y-%m-%d").date()
        extras_by_date[d] = ep

    balance = float(principal_cents)
    initial_principal = float(principal_cents)
    remaining_months = term_months
    monthly_payment = 0.0

    # Calculate initial payment
    r = current_rate / 12.0
    if loan_type == "annuity":
        if r > 0:
            monthly_payment = balance * r / \
                (1.0 - (1.0 + r) ** (-remaining_months))
        else:
            monthly_payment = balance / remaining_months

    for month_idx in range(1, term_months + 1):
        if balance <= 1:  # paid off
            break

        due_date = add_months(start_date, month_idx)

        # Check for rate updates
        for rp in sorted_rates:
            rp_date = rp["from_date"]
            if isinstance(rp_date, str):
                rp_date = datetime.strptime(rp_date[:10], "%Y-%m-%d").date()
            if due_date >= rp_date and rp["annual_rate"] != current_rate:
                current_rate = rp["annual_rate"]
                r = current_rate / 12.0
                if loan_type == "annuity" and r > 0 and remaining_months > 0:
                    monthly_payment = balance * r / \
                        (1.0 - (1.0 + r) ** (-remaining_months))

        r = current_rate / 12.0
        interest = balance * r

        if loan_type == "linear":
            principal = initial_principal / term_months
            if principal > balance:
                principal = balance
            payment = principal + interest
        elif loan_type == "interest_only":
            interest = balance * r
            principal = balance if month_idx == term_months else 0.0
            payment = interest + principal
        else:  # annuity
            if remaining_months <= 1:
                payment = balance + interest
                principal = balance
            else:
                payment = monthly_payment
                principal = payment - interest
                if principal > balance:
                    principal = balance
                    payment = principal + interest

        extra_paid = 0.0
        # Check extra payments in this month period
        for ep_date, ep in list(extras_by_date.items()):
            prev_date = add_months(start_date, month_idx - 1)
            if prev_date < ep_date <= due_date:
                extra_amt = float(ep["amount_minor"])
                extra_paid += extra_amt
                balance -= extra_amt
                recalc_mode = ep.get("recalc", "lower_payment")
                if recalc_mode == "lower_payment" and loan_type == "annuity" and remaining_months > 1:
                    r = current_rate / 12.0
                    if r > 0:
                        monthly_payment = balance * r / \
                            (1.0 - (1.0 + r) ** (-(remaining_months - 1)))
                    else:
                        monthly_payment = balance / (remaining_months - 1)

        balance -= principal
        if balance < 0:
            principal += balance
            balance = 0.0
            payment = principal + interest

        remaining_months -= 1

        schedule.append(
            {
                "month_idx": month_idx,
                "due_date": due_date.isoformat(),
                "payment_minor": int(round(payment)),
                "interest_minor": int(round(interest)),
                "principal_minor": int(round(principal)),
                "extra_minor": int(round(extra_paid)),
                "balance_minor": int(round(balance)),
            }
        )

    return schedule


def sync_liability_schedule(conn: sqlite3.Connection, liability_id: int) -> None:
    lib_row = conn.execute(
        "SELECT * FROM liabilities WHERE id = ?", (liability_id,)).fetchone()
    if not lib_row:
        return

    rates = [
        dict(r)
        for r in conn.execute(
            "SELECT * FROM liability_rate_periods WHERE liability_id = ? ORDER BY from_date ASC",
            (liability_id,),
        ).fetchall()
    ]
    extras = [
        dict(r)
        for r in conn.execute(
            "SELECT * FROM liability_extra_payments WHERE liability_id = ? ORDER BY paid_date ASC",
            (liability_id,),
        ).fetchall()
    ]

    start_date_raw = lib_row["start_date"]
    start_date = (
        datetime.strptime(start_date_raw[:10], "%Y-%m-%d").date()
        if isinstance(start_date_raw, str)
        else start_date_raw
    )

    sched = calculate_mortgage_schedule(
        loan_type=lib_row["loan_type"],
        principal_cents=lib_row["original_principal_minor"],
        start_date=start_date,
        term_months=lib_row["term_months"],
        rate_periods=rates,
        extra_payments=extras,
    )

    with conn:
        conn.execute(
            "DELETE FROM liability_schedule WHERE liability_id = ?", (liability_id,))
        for s in sched:
            conn.execute(
                """
                INSERT INTO liability_schedule (
                    liability_id, month_idx, due_date, payment_minor,
                    interest_minor, principal_minor, extra_minor, balance_minor
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    liability_id,
                    s["month_idx"],
                    s["due_date"],
                    s["payment_minor"],
                    s["interest_minor"],
                    s["principal_minor"],
                    s["extra_minor"],
                    s["balance_minor"],
                ),
            )
