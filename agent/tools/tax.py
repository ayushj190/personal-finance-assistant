from typing import Any
import plotly.express as px

from core.config import DB_PATH
from db import database
from core.money import Money
from services.tax_optimizer import (
    calculate_jaarruimte,
    calculate_groenfondsen_arbitrage,
    simulate_capital_allocation_tradeoff,
    diagnose_tax_leakage,
)
from services.analytics import calculate_current_net_worth


def tool_save_tax_profile(
    gross_annual_income: float,
    has_fiscal_partner: bool,
    has_30_percent_ruling: bool = False,
    is_entrepreneur: bool = False,
    owns_home: bool = False,
    birth_year: int | None = None,
    has_13th_month: bool = False,
    expected_bonus_eur: float = 0,
    pension_contribution_pct: float = 0,
    employer_pension_match_pct: float = 0,
    factor_a: float = 0,
    green_investments_eur: float = 0,
    reserveringsruimte_eur: float = 0,
) -> dict[str, Any]:
    """Save user tax profile to the database."""
    conn = database.connect(DB_PATH)
    try:
        factor_a_minor = Money.from_major(factor_a or 0.0).cents
        green_minor = Money.from_major(green_investments_eur or 0.0).cents
        res_minor = Money.from_major(reserveringsruimte_eur or 0.0).cents
        with conn:
            conn.execute(
                "INSERT INTO tax_profile (id, gross_annual_income, has_fiscal_partner, has_30_percent_ruling, "
                "is_entrepreneur, owns_home, birth_year, has_13th_month, expected_bonus_eur, pension_contribution_pct, "
                "employer_pension_match_pct, factor_a_minor, green_investments_minor, reserveringsruimte_minor) "
                "VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET gross_annual_income=excluded.gross_annual_income, "
                "has_fiscal_partner=excluded.has_fiscal_partner, has_30_percent_ruling=excluded.has_30_percent_ruling, "
                "is_entrepreneur=excluded.is_entrepreneur, owns_home=excluded.owns_home, birth_year=excluded.birth_year, "
                "has_13th_month=excluded.has_13th_month, expected_bonus_eur=excluded.expected_bonus_eur, "
                "pension_contribution_pct=excluded.pension_contribution_pct, employer_pension_match_pct=excluded.employer_pension_match_pct, "
                "factor_a_minor=excluded.factor_a_minor, green_investments_minor=excluded.green_investments_minor, "
                "reserveringsruimte_minor=excluded.reserveringsruimte_minor, "
                "updated_at=datetime('now')",
                (
                    gross_annual_income if gross_annual_income is not None else 0.0,
                    1 if has_fiscal_partner else 0,
                    1 if has_30_percent_ruling else 0,
                    1 if is_entrepreneur else 0,
                    1 if owns_home else 0,
                    birth_year,
                    1 if has_13th_month else 0,
                    int(expected_bonus_eur) if expected_bonus_eur is not None else 0,
                    pension_contribution_pct if pension_contribution_pct is not None else 0.0,
                    employer_pension_match_pct if employer_pension_match_pct is not None else 0.0,
                    factor_a_minor,
                    green_minor,
                    res_minor,
                ),
            )
        return {
            "success": True,
            "message": f"Tax profile saved successfully: Gross Income €{(gross_annual_income or 0):,.2f}, Fiscal Partner: {bool(has_fiscal_partner)}, Factor A: €{(factor_a or 0):,.0f}, Green Assets: €{(green_investments_eur or 0):,.0f}.",
        }
    finally:
        conn.close()


def tool_simulate_tax_optimization(capital_eur: float, horizon_years: int = 10) -> dict[str, Any]:
    """Simulate 4-way capital trade-off (Mortgage Prepayment vs. Pillar 3 Jaarruimte vs. Certified Groenfonds vs. Taxable ETF)."""
    try:
        clean_capital = float(capital_eur)
    except (ValueError, TypeError):
        return {
            "success": False,
            "message": f"Invalid capital amount '{capital_eur}'. Please provide a numeric value.",
        }
    if clean_capital <= 0:
        return {
            "success": False,
            "message": f"Capital amount must be greater than 0, got €{clean_capital:,.2f}.",
        }

    try:
        clean_horizon = int(horizon_years)
    except (ValueError, TypeError):
        clean_horizon = 10
    if not (1 <= clean_horizon <= 50):
        return {
            "success": False,
            "message": f"Horizon must be between 1 and 50 years, got {horizon_years}.",
        }

    conn = database.connect_readonly(DB_PATH)
    try:
        sim = simulate_capital_allocation_tradeoff(clean_capital, clean_horizon, conn=conn)
        df = sim["trajectory_df"]

        fig = px.line(
            df,
            x="Year",
            y=["Mortgage Prepayment", "Pillar 3 Pension (Jaarruimte)", "Certified Groenfonds", "Taxable Box 3 ETF"],
            title=f"Capital Allocation Strategy Comparison (€{clean_capital:,.0f} Horizon {clean_horizon}y)",
            labels={"value": "Total Net Wealth (€)", "variable": "Strategy"},
            markers=True,
        )
        fig.update_layout(
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            margin=dict(l=10, r=10, t=50, b=10),
            hovermode="x unified",
        )

        winner = sim["winner_strategy"].replace("_", " ").title()
        msg = (
            f"Simulated €{clean_capital:,.0f} across {clean_horizon} years. "
            f"Top outcome: {winner} yielding €{sim['final_values'][sim['winner_strategy']]:,.2f} net. "
            f"Immediate Pillar 3 tax refund: €{sim['immediate_pension_refund_eur']:,.2f}."
        )

        return {
            "success": True,
            "simulation": sim,
            "figure": fig,
            "df": df,
            "message": msg,
        }
    finally:
        conn.close()


def tool_calculate_pension_room(gross_income: float | None = None, factor_a: float = 0.0) -> dict[str, Any]:
    """Calculate official Dutch Pillar 3 pension gap (Jaarruimte & Reserveringsruimte) and immediate Box 1 tax refund."""
    clean_income = None
    if gross_income is not None:
        try:
            clean_income = float(gross_income)
            if clean_income < 0:
                return {
                    "success": False,
                    "message": f"Gross annual income cannot be negative, got €{clean_income:,.2f}.",
                }
        except (ValueError, TypeError):
            return {
                "success": False,
                "message": f"Invalid gross income '{gross_income}'. Please provide a valid numeric amount.",
            }

    try:
        clean_factor_a = float(factor_a)
        if clean_factor_a < 0:
            return {
                "success": False,
                "message": f"Factor A cannot be negative, got €{clean_factor_a:,.2f}.",
            }
    except (ValueError, TypeError):
        clean_factor_a = 0.0

    conn = database.connect_readonly(DB_PATH)
    try:
        if clean_income is None:
            profile = conn.execute(
                "SELECT gross_annual_income, factor_a_minor, reserveringsruimte_minor FROM tax_profile WHERE id = 1"
            ).fetchone()
            clean_income = float(profile["gross_annual_income"]) if profile else 65000.0
            if clean_factor_a == 0.0 and profile and "factor_a_minor" in profile.keys():
                clean_factor_a = Money.from_cents(profile["factor_a_minor"]).to_major()

        pension_data = calculate_jaarruimte(gross_income=clean_income, factor_a=clean_factor_a)
        msg = (
            f"Calculated Jaarruimte for €{clean_income:,.0f} gross (Factor A: €{clean_factor_a:,.0f}): "
            f"Annual room €{pension_data['annual_jaarruimte']:,.2f}. "
            f"Immediate Box 1 tax refund: €{pension_data['immediate_tax_rebate']:,.2f} "
            f"({pension_data['marginal_tax_rate']*100:.2f}% marginal bracket). "
            f"20-year compound tax shield: €{pension_data['compounding_tax_shield']:,.2f}."
        )
        return {
            "success": True,
            "pension_data": pension_data,
            "message": msg,
        }
    finally:
        conn.close()


def tool_analyze_green_fund_strategy(target_allocation: float | None = None) -> dict[str, Any]:
    """Analyze Dutch Groenfondsen double tax benefit (Box 3 wealth tax exemption and 0.1% Box 1 credit)."""
    clean_target = None
    if target_allocation is not None:
        try:
            clean_target = float(target_allocation)
            if clean_target < 0:
                return {
                    "success": False,
                    "message": f"Target allocation cannot be negative, got €{clean_target:,.2f}.",
                }
        except (ValueError, TypeError):
            return {
                "success": False,
                "message": f"Invalid target allocation '{target_allocation}'. Please provide a valid numeric amount.",
            }

    conn = database.connect_readonly(DB_PATH)
    try:
        nw = calculate_current_net_worth(conn)
        total_wealth = nw["liquid_cash"] + nw["invested"]
        profile = conn.execute("SELECT * FROM tax_profile WHERE id = 1").fetchone()
        has_partner = bool(profile["has_fiscal_partner"]) if profile else False
        current_green = Money.from_cents(profile["green_investments_minor"]).to_major() if profile and "green_investments_minor" in profile.keys() else 0.0
        prospective = clean_target if clean_target is not None else (25000.0 if current_green == 0 else 0.0)

        arb = calculate_groenfondsen_arbitrage(
            total_wealth=total_wealth,
            current_green=current_green,
            prospective_green=prospective,
            has_fiscal_partner=has_partner,
        )

        msg = (
            f"Groenfondsen Analysis: Exemption cap €{arb['exemption_cap']:,.0f}. "
            f"Annual tax benefit for €{arb['total_green']:,.0f} green allocation: "
            f"€{arb['total_annual_tax_benefit']:,.2f} (avoiding €{arb['box3_annual_savings']:,.2f} in Box 3 + "
            f"€{arb['box1_annual_credit']:,.2f} Box 1 credit). "
            f"Guaranteed tax alpha: ~{arb['guaranteed_tax_alpha_pct']:.2f}%."
        )
        return {
            "success": True,
            "arbitrage": arb,
            "message": msg,
        }
    finally:
        conn.close()


def tool_diagnose_tax_leaks() -> dict[str, Any]:
    """Scan current user assets, liabilities, and income to proactively diagnose tax inefficiencies."""
    conn = database.connect_readonly(DB_PATH)
    try:
        leaks = diagnose_tax_leakage(conn)
        tot_savings = sum(l["potential_annual_saving_eur"] for l in leaks)
        msg = f"Diagnosed {len(leaks)} tax optimization opportunities with up to €{tot_savings:,.2f} in potential annual savings."
        return {
            "success": True,
            "leak_count": len(leaks),
            "total_potential_annual_savings_eur": tot_savings,
            "recommendations": leaks,
            "message": msg,
        }
    finally:
        conn.close()


def tool_analyze_tax_situation() -> dict[str, Any]:
    """Fetch the user's gross income from tax_profile, their investment/cash balances for Box 3, and return them for analysis."""
    conn = database.connect_readonly(DB_PATH)
    try:
        profile = conn.execute("SELECT * FROM tax_profile WHERE id = 1").fetchone()
        if not profile or profile["gross_annual_income"] == 0:
            guidance = "No gross annual income or tax profile configured yet. Please open the Tax Analysis tab or tell me your gross income to configure Box 1 and Box 3 calculations."
            return {
                "success": False,
                "empty_dataset": True,
                "guidance": guidance,
                "message": f"Tax profile is not configured. {guidance}",
            }

        # Get net worth data for Box 3
        nw_data = calculate_current_net_worth(conn)
        cash_bal = nw_data["liquid_cash"]
        invested_bal = nw_data["invested"]

        return {
            "success": True,
            "tax_profile": dict(profile),
            "box3_assets": {
                "liquid_cash": cash_bal,
                "invested": invested_bal,
                "total_wealth": cash_bal + invested_bal,
            },
            "message": "Tax data retrieved successfully.",
        }
    finally:
        conn.close()
