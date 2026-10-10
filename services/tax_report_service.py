import sqlite3
from typing import Any
import pandas as pd
from datetime import date

from config import DB_PATH
from db import database
from services.analytics import calculate_current_net_worth


def generate_dutch_tax_statement(year: int | None = None, conn: sqlite3.Connection | None = None) -> dict[str, Any]:
    """Generates complete Dutch Belastingdienst tax filing report data."""
    close_conn = False
    if conn is None:
        conn = database.connect(DB_PATH)
        close_conn = True

    tax_year = year or (date.today().year - 1)

    try:
        profile = conn.execute("SELECT * FROM tax_profile WHERE id = 1").fetchone()
        gross_income = float(profile["gross_annual_income"]) if profile else 0.0
        has_partner = bool(profile["has_fiscal_partner"]) if profile else False
        has_30_pct = bool(profile["has_30_percent_ruling"]) if profile else False

        # 1. Box 1: Employment Income & 30% Ruling
        taxable_gross = gross_income * 0.70 if has_30_pct else gross_income
        bracket1_limit = 75518.0
        bracket1_rate = 0.3697
        bracket2_rate = 0.4950

        if taxable_gross <= bracket1_limit:
            box1_tax = taxable_gross * bracket1_rate
        else:
            box1_tax = (bracket1_limit * bracket1_rate) + ((taxable_gross - bracket1_limit) * bracket2_rate)

        # 2. Box 1 Deductions: Mortgage Interest Deduction (Hypotheekrenteaftrek)
        # Sum interest payments for the tax year from liability_schedule
        interest_row = conn.execute(
            """
            SELECT SUM(interest_minor) / 100.0 as total_interest
            FROM liability_schedule
            WHERE strftime('%Y', due_date) = ?
            """,
            (str(tax_year),),
        ).fetchone()
        deductible_mortgage_interest = float(interest_row["total_interest"] or 0.0)
        # Tax benefit from mortgage interest deduction (effective ~36.97% max deduction rate)
        mortgage_interest_tax_benefit = deductible_mortgage_interest * 0.3697

        # 3. Box 3: Wealth on reference date (Peildatum 1 Januari)
        nw = calculate_current_net_worth(conn)
        cash_balance = nw["liquid_cash"]
        investments_balance = nw["invested"]
        total_wealth = cash_balance + investments_balance
        tax_free_allowance = 114000.0 if has_partner else 57000.0

        taxable_wealth = max(0.0, total_wealth - tax_free_allowance)
        # 2024 fictitious yields: cash = 1.03%, investments = 6.04%
        fictitious_cash = cash_balance * 0.0103
        fictitious_inv = investments_balance * 0.0604
        total_fictitious = fictitious_cash + fictitious_inv

        taxable_ratio = (taxable_wealth / total_wealth) if total_wealth > 0 else 0.0
        taxable_return = total_fictitious * taxable_ratio
        box3_tax_due = taxable_return * 0.36

        net_income_after_tax = (
            gross_income
            - box1_tax
            + mortgage_interest_tax_benefit
            - box3_tax_due
        )

        report_rows = [
            {"Section": "Box 1 - Gross Annual Income", "Amount (€)": gross_income, "Notes": "Base salary + 8% holiday allowance"},
            {"Section": "Box 1 - 30% Ruling Exemption", "Amount (€)": (gross_income * 0.3) if has_30_pct else 0.0, "Notes": "Tax-free allowance" if has_30_pct else "N/A"},
            {"Section": "Box 1 - Taxable Labor Income", "Amount (€)": taxable_gross, "Notes": f"Subject to {bracket1_rate*100:.2f}% / {bracket2_rate*100:.2f}% brackets"},
            {"Section": "Box 1 - Preliminary Income Tax", "Amount (€)": -box1_tax, "Notes": "Before tax credits and deductions"},
            {"Section": "Box 1 - Mortgage Interest Paid (HRA)", "Amount (€)": deductible_mortgage_interest, "Notes": f"Tax refund benefit: +€{mortgage_interest_tax_benefit:,.2f}"},
            {"Section": "Box 3 - Liquid Cash (Peildatum)", "Amount (€)": cash_balance, "Notes": "Fictitious yield 1.03%"},
            {"Section": "Box 3 - Investments & Crypto", "Amount (€)": investments_balance, "Notes": "Fictitious yield 6.04%"},
            {"Section": "Box 3 - Tax-free Wealth Allowance", "Amount (€)": tax_free_allowance, "Notes": "With fiscal partner" if has_partner else "Single allowance"},
            {"Section": "Box 3 - Tax Due", "Amount (€)": -box3_tax_due, "Notes": "36% over fictitious yield above allowance"},
            {"Section": "Estimated Total Net Annual Income", "Amount (€)": net_income_after_tax, "Notes": "After all taxes, deductions, and refunds"},
        ]

        df = pd.DataFrame(report_rows)

        csv_content = df.to_csv(index=False)

        return {
            "tax_year": tax_year,
            "gross_income": gross_income,
            "has_partner": has_partner,
            "has_30_pct": has_30_pct,
            "box1_tax": box1_tax,
            "deductible_mortgage_interest": deductible_mortgage_interest,
            "mortgage_interest_refund": mortgage_interest_tax_benefit,
            "taxable_wealth": taxable_wealth,
            "box3_tax": box3_tax_due,
            "estimated_net_income": net_income_after_tax,
            "report_df": df,
            "csv_content": csv_content,
        }
    finally:
        if close_conn:
            conn.close()
