import sqlite3
from typing import Any
import pandas as pd

from core.config import DB_PATH
from db import database
from services.analytics import calculate_current_net_worth

# ── Certified Dutch Green Funds Catalog ──────────────────────────
CERTIFIED_DUTCH_GREEN_FUNDS = [
    {
        "name": "ASN Groenprojectenfonds",
        "isin": "NL0000440447",
        "manager": "ASN Bank / de Volksbank",
        "asset_class": "Green Project Debt & Equity",
        "focus": "Renewable Wind/Solar, Organic Agriculture, Circular Economy",
        "indicative_dividend_yield_pct": 2.10,
        "box3_exempt": True,
    },
    {
        "name": "Triodos Groenfonds",
        "isin": "NL0000286147",
        "manager": "Triodos Bank NV",
        "asset_class": "Green Loans & Sustainable Energy",
        "focus": "Clean Tech, Sustainable Real Estate, Nature Development",
        "indicative_dividend_yield_pct": 1.95,
        "box3_exempt": True,
    },
    {
        "name": "Meesman Duurzame Toekomst (Groen Component)",
        "isin": "NL0012650570",
        "manager": "Meesman Indexbeleggen",
        "asset_class": "Global Sustainable Equities & Bonds",
        "focus": "Strict ESG Screened & Certified Transition Assets",
        "indicative_dividend_yield_pct": 2.40,
        "box3_exempt": True,
    },
    {
        "name": "Rabobank Groen Deposito",
        "isin": "RABO-GROEN-DEP",
        "manager": "Rabobank Groen Bank",
        "asset_class": "Fixed Term Green Deposit",
        "focus": "Dutch Sustainable Infrastructure & Housing",
        "indicative_dividend_yield_pct": 2.25,
        "box3_exempt": True,
    },
]


def calculate_jaarruimte(
    gross_income: float,
    factor_a: float = 0.0,
    unused_carryforward: float = 0.0,
) -> dict[str, Any]:
    """Calculate official Dutch Pillar 3 pension gap (Jaarruimte & Reserveringsruimte).

    Based on Belastingdienst rules (Wet toekomst pensioenen 2024-2026):
    - AOW-franchise 2024: €17,545
    - Max pensionable salary cap: €137,800
    - Premiegrondslag = max(0, min(gross_income, cap) - AOW_franchise)
    - Jaarruimte = max(0, min(0.30 * premiegrondslag - 3 * factor_a, 30528.0))
    """
    gross = max(0.0, float(gross_income))
    fa = max(0.0, float(factor_a))
    carry = max(0.0, float(unused_carryforward))

    aow_franchise = 17545.0
    max_salary_cap = 137800.0
    max_jaarruimte_cap = 30528.0
    max_reserveringsruimte_cap = 41608.0

    pensionable_salary = min(gross, max_salary_cap)
    premiegrondslag = max(0.0, pensionable_salary - aow_franchise)

    # 30% formula minus 3x Factor A
    base_calc = (0.30 * premiegrondslag) - (3.0 * fa)
    annual_room = max(0.0, min(base_calc, max_jaarruimte_cap))
    usable_carryforward = min(carry, max_reserveringsruimte_cap)
    total_deductible_room = annual_room + usable_carryforward

    # Marginal tax rate for Box 1
    marginal_rate = 0.4950 if gross > 75518.0 else 0.3697
    immediate_tax_rebate = total_deductible_room * marginal_rate

    # Multi-year compound wealth simulation comparison
    # Assumes 7% gross investment return
    horizon_years = 20
    growth_rate = 0.07
    box3_drag = 0.021744  # 6.04% deemed yield * 36%

    # In Pillar 3 (Lijfrente): grows tax-free at 7.0%
    pillar3_future_gross = total_deductible_room * ((1.0 + growth_rate) ** horizon_years) if total_deductible_room > 0 else 0.0
    # Estimated net after retirement tax (conservative 19.07% bracket 1 after AOW age)
    pillar3_future_net = pillar3_future_gross * (1.0 - 0.1907)

    # In standard Box 3: grows at net (7.0% - 2.17%) = 4.826%
    taxable_future_net = total_deductible_room * ((1.0 + (growth_rate - box3_drag)) ** horizon_years) if total_deductible_room > 0 else 0.0

    compounding_tax_shield = max(0.0, pillar3_future_net - taxable_future_net)

    return {
        "gross_income": gross,
        "factor_a": fa,
        "aow_franchise": aow_franchise,
        "premiegrondslag": premiegrondslag,
        "annual_jaarruimte": annual_room,
        "reserveringsruimte_used": usable_carryforward,
        "total_deductible_room": total_deductible_room,
        "marginal_tax_rate": marginal_rate,
        "immediate_tax_rebate": immediate_tax_rebate,
        "horizon_years": horizon_years,
        "pillar3_future_net": pillar3_future_net,
        "taxable_future_net": taxable_future_net,
        "compounding_tax_shield": compounding_tax_shield,
        "effective_cash_outlay": total_deductible_room - immediate_tax_rebate,
    }


def calculate_groenfondsen_arbitrage(
    total_wealth: float,
    current_green: float = 0.0,
    prospective_green: float = 0.0,
    has_fiscal_partner: bool = False,
) -> dict[str, Any]:
    """Calculate exact Dutch Groenfondsen double tax benefit (Box 3 exemption + Box 1 credit)."""
    wealth = max(0.0, float(total_wealth))
    c_green = max(0.0, float(current_green))
    p_green = max(0.0, float(prospective_green))
    tot_green = c_green + p_green

    exemption_cap = 142502.0 if has_fiscal_partner else 71251.0
    tax_free_base_allowance = 114000.0 if has_fiscal_partner else 57000.0

    # How much of the green allocation actually shields wealth from Box 3?
    # Only amounts that would otherwise be subject to Box 3 tax generate savings.
    wealth_above_base = max(0.0, wealth - tax_free_base_allowance)
    effective_exempt_green = min(tot_green, exemption_cap, wealth_above_base if wealth_above_base > 0 else tot_green)

    # Box 3 avoided tax: 6.04% deemed return * 36%
    deemed_yield_rate = 0.0604
    tax_rate = 0.36
    box3_effective_drag = deemed_yield_rate * tax_rate  # 0.021744 (2.1744%)
    box3_annual_savings = effective_exempt_green * box3_effective_drag

    # Box 1 extra green credit: 0.1% over green balance up to cap
    box1_credit_rate = 0.001
    box1_annual_credit = min(tot_green, exemption_cap) * box1_credit_rate

    total_annual_tax_benefit = box3_annual_savings + box1_annual_credit
    guaranteed_tax_alpha_pct = (box3_effective_drag + box1_credit_rate) * 100.0  # ~2.2744%

    # Breakeven required return for taxable alternative:
    # Taxable ETF needs: net_yield + 2.174% drag to break even with green fund
    example_green_yield = 2.10
    equivalent_taxable_gross_yield = example_green_yield + guaranteed_tax_alpha_pct

    return {
        "total_wealth": wealth,
        "current_green": c_green,
        "prospective_green": p_green,
        "total_green": tot_green,
        "exemption_cap": exemption_cap,
        "effective_exempt_green": effective_exempt_green,
        "box3_annual_savings": box3_annual_savings,
        "box1_annual_credit": box1_annual_credit,
        "total_annual_tax_benefit": total_annual_tax_benefit,
        "guaranteed_tax_alpha_pct": guaranteed_tax_alpha_pct,
        "equivalent_taxable_gross_yield": equivalent_taxable_gross_yield,
        "certified_funds": CERTIFIED_DUTCH_GREEN_FUNDS,
    }


def simulate_capital_allocation_tradeoff(
    capital_eur: float,
    horizon_years: int = 10,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    """Run 4-way capital trade-off simulation:

    Option 1: Extra Mortgage Repayment (Guaranteed interest saved, minus reduced HRA)
    Option 2: Pillar 3 Jaarruimte Deposit (Immediate Box 1 tax refund + 0% Box 3 tax forever)
    Option 3: Certified Groenfonds (Liquid, ~2% dividend + 2.27% guaranteed tax alpha)
    Option 4: Standard Box 3 ETF (7% gross return minus 2.17% deemed yield drag)
    """
    capital = max(100.0, float(capital_eur))
    horizon = max(1, min(40, int(horizon_years)))

    close_conn = False
    if conn is None:
        conn = database.connect(DB_PATH)
        close_conn = True

    try:
        # 1. Fetch user mortgage rate
        rate_row = conn.execute("SELECT annual_rate FROM liability_rate_periods ORDER BY from_date DESC LIMIT 1").fetchone()
        mortgage_rate = float(rate_row["annual_rate"]) if rate_row else 0.0385
        # Effective net mortgage interest after 36.97% HRA deduction
        net_mortgage_rate = mortgage_rate * (1.0 - 0.3697)

        # 2. Fetch user tax profile for marginal bracket
        tax_profile = conn.execute("SELECT * FROM tax_profile WHERE id = 1").fetchone()
        gross_income = float(tax_profile["gross_annual_income"]) if tax_profile else 65000.0
        marginal_tax_rate = 0.4950 if gross_income > 75518.0 else 0.3697

        # 3. Simulate year-by-year trajectories
        years = list(range(0, horizon + 1))
        traj_mortgage = []
        traj_pension = []
        traj_green = []
        traj_taxable_etf = []

        # Assumptions
        stock_gross_growth = 0.070
        box3_drag = 0.021744
        green_fund_div = 0.020
        green_tax_alpha = 0.022744  # 2.174% avoided Box 3 + 0.1% Box 1 credit

        # Option 1: Extra Mortgage Prepayment
        # Guaranteed compound savings: capital * (1 + net_mortgage_rate)^t
        for y in years:
            val_m = capital * ((1.0 + net_mortgage_rate) ** y)
            traj_mortgage.append(round(val_m, 2))

        # Option 2: Pillar 3 Pension Deposit (Jaarruimte)
        # Immediate tax refund is collected at year 0:
        immediate_refund = capital * marginal_tax_rate
        # In pension: full capital compounds at 7.0%, taxed at retirement (~19.07% bracket 1)
        # Plus refund invested in safe cash/ETF
        for y in years:
            pension_gross = capital * ((1.0 + stock_gross_growth) ** y)
            pension_net = pension_gross * (1.0 - 0.1907)
            # Reinvested tax refund (growing at net ETF rate)
            refund_growth = immediate_refund * ((1.0 + (stock_gross_growth - box3_drag)) ** y)
            traj_pension.append(round(pension_net + refund_growth, 2))

        # Option 3: Certified Groenfonds
        # Net compound yield = 2.0% + 2.274% = 4.274%
        green_net_yield = green_fund_div + green_tax_alpha
        for y in years:
            val_g = capital * ((1.0 + green_net_yield) ** y)
            traj_green.append(round(val_g, 2))

        # Option 4: Standard Box 3 Taxable ETF
        # Net compound yield = 7.0% - 2.174% = 4.826%
        etf_net_yield = stock_gross_growth - box3_drag
        for y in years:
            val_etf = capital * ((1.0 + etf_net_yield) ** y)
            traj_taxable_etf.append(round(val_etf, 2))

        summary_df = pd.DataFrame({
            "Year": years,
            "Mortgage Prepayment": traj_mortgage,
            "Pillar 3 Pension (Jaarruimte)": traj_pension,
            "Certified Groenfonds": traj_green,
            "Taxable Box 3 ETF": traj_taxable_etf,
        })

        final_values = {
            "mortgage": traj_mortgage[-1],
            "pension": traj_pension[-1],
            "green": traj_green[-1],
            "taxable_etf": traj_taxable_etf[-1],
        }

        # Ranking best to worst
        ranked = sorted(final_values.items(), key=lambda x: x[1], reverse=True)
        winner_strategy = ranked[0][0]

        return {
            "capital_eur": capital,
            "horizon_years": horizon,
            "mortgage_nominal_rate_pct": round(mortgage_rate * 100.0, 2),
            "mortgage_net_rate_pct": round(net_mortgage_rate * 100.0, 2),
            "marginal_tax_rate_pct": round(marginal_tax_rate * 100.0, 2),
            "immediate_pension_refund_eur": round(immediate_refund, 2),
            "final_values": final_values,
            "winner_strategy": winner_strategy,
            "trajectory_df": summary_df,
        }
    finally:
        if close_conn:
            conn.close()


def diagnose_tax_leakage(conn: sqlite3.Connection | None = None) -> list[dict[str, Any]]:
    """Scan current accounts, liabilities, and profile to identify concrete tax inefficiencies."""
    close_conn = False
    if conn is None:
        conn = database.connect(DB_PATH)
        close_conn = True

    recommendations: list[dict[str, Any]] = []

    try:
        nw = calculate_current_net_worth(conn)
        cash_balance = nw["liquid_cash"]
        invested_balance = nw["invested"]
        total_wealth = cash_balance + invested_balance

        profile = conn.execute("SELECT * FROM tax_profile WHERE id = 1").fetchone()
        gross_income = float(profile["gross_annual_income"]) if profile else 0.0
        has_partner = bool(profile["has_fiscal_partner"]) if profile else False
        has_green = int(profile["green_investments_minor"]) if profile and "green_investments_minor" in profile.keys() else 0
        allowance = 114000.0 if has_partner else 57000.0

        # Leak 1: Cash Drag above Box 3 Threshold
        if total_wealth > allowance and cash_balance > 25000:
            tax_drag_cash = (cash_balance - 10000) * 0.0103 * 0.36
            recommendations.append({
                "severity": "HIGH",
                "area": "Box 3 Wealth Tax Drag",
                "title": "Sub-optimal Cash Allocation in Box 3",
                "message": (
                    f"You hold €{cash_balance:,.0f} in cash with total wealth exceeding the €{allowance:,.0f} allowance. "
                    f"Holding uninvested cash above emergency buffers incurs 0.37% tax drag plus negative real yield after inflation. "
                    f"Consider shifting funds into Groenfondsen (tax-exempt up to €71k/€142k) or high-yield deposit guarantees."
                ),
                "potential_annual_saving_eur": round(tax_drag_cash, 2),
            })

        # Leak 2: High Bracket Income with Zero Pillar 3 Deduction
        if gross_income > 75518.0:
            marginal_bracket = 0.4950
            potential_pension_room = 6000.0
            potential_refund = potential_pension_room * marginal_bracket
            recommendations.append({
                "severity": "HIGH",
                "area": "Box 1 Pension Room (Jaarruimte)",
                "title": "Unclaimed Top-Bracket (49.5%) Pension Deduction",
                "message": (
                    f"Your gross annual income (€{gross_income:,.0f}) is taxed at the highest 49.50% marginal bracket. "
                    f"Utilizing private Pillar 3 Jaarruimte returns up to 49.5% in immediate cash tax refund while shielding "
                    f"the invested capital permanently from annual Box 3 wealth taxes."
                ),
                "potential_annual_saving_eur": round(potential_refund, 2),
            })

        # Leak 3: Large Non-Green Investment Portfolio in Box 3
        if invested_balance > allowance and has_green == 0:
            potential_green_shift = min(invested_balance - allowance, 71251.0)
            potential_green_savings = potential_green_shift * 0.022744
            recommendations.append({
                "severity": "MEDIUM",
                "area": "Green Investment Shield (Groenfondsen)",
                "title": "Missing Groenfondsen Box 3 Exemption",
                "message": (
                    f"You have €{invested_balance:,.0f} in investments subject to the standard 2.17% deemed return wealth tax. "
                    f"Allocating up to €71,251 into certified Dutch green funds (e.g. ASN or Triodos Groenfonds) completely removes "
                    f"the Box 3 wealth tax on that slice and grants an extra 0.1% Box 1 credit."
                ),
                "potential_annual_saving_eur": round(potential_green_savings, 2),
            })

        # Leak 4: Mortgage Prepayment Arbitrage
        liabilities = conn.execute("SELECT id, name, original_principal_minor FROM liabilities").fetchall()
        if liabilities:
            lib = liabilities[0]
            rate_row = conn.execute("SELECT annual_rate FROM liability_rate_periods WHERE liability_id = ? ORDER BY from_date DESC LIMIT 1", (lib["id"],)).fetchone()
            if rate_row and rate_row["annual_rate"] >= 0.038:
                mortgage_rate = rate_row["annual_rate"]
                net_rate = mortgage_rate * (1 - 0.3697)
                recommendations.append({
                    "severity": "LOW",
                    "area": "Mortgage Liability Optimization",
                    "title": "Penalty-Free Prepayment Headroom",
                    "message": (
                        f"Your mortgage '{lib['name']}' has a nominal interest rate of {mortgage_rate*100:.2f}% "
                        f"(~{net_rate*100:.2f}% net after HRA). Most lenders permit 10%–20% penalty-free principal prepayment "
                        f"per calendar year. If your liquid cash yields less than {net_rate*100:.2f}%, making extra principal "
                        f"repayments guarantees a risk-free net savings."
                    ),
                    "potential_annual_saving_eur": round((lib["original_principal_minor"] / 100.0) * 0.10 * net_rate, 2),
                })

        return recommendations
    finally:
        if close_conn:
            conn.close()
