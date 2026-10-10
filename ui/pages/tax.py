import pandas as pd
import streamlit as st
import plotly.express as px

from config import DB_PATH
from db import database
from ui.components import format_money, section_header, kpi_card, is_hidden
from services.tax_report_service import generate_dutch_tax_statement



def calculate_box1_tax(gross_income: float) -> dict:
    """Simplified Box 1 Dutch income tax calculation (2024 brackets)."""
    bracket1_limit = 75518.0
    bracket1_rate = 0.3697
    bracket2_rate = 0.4950

    if gross_income <= bracket1_limit:
        bracket1_tax = gross_income * bracket1_rate
        bracket2_tax = 0.0
    else:
        bracket1_tax = bracket1_limit * bracket1_rate
        bracket2_tax = (gross_income - bracket1_limit) * bracket2_rate

    total_tax = bracket1_tax + bracket2_tax
    net_income = gross_income - total_tax

    return {
        "bracket1_tax": bracket1_tax,
        "bracket2_tax": bracket2_tax,
        "total_tax": total_tax,
        "net_income": net_income,
    }


def calculate_box3_tax(cash_eur: float, invested_eur: float, has_fiscal_partner: bool) -> dict:
    """Simplified Box 3 Dutch wealth tax calculation (2024 fictitious yields)."""
    tax_free_allowance = 114000.0 if has_fiscal_partner else 57000.0
    total_wealth = cash_eur + invested_eur

    if total_wealth <= tax_free_allowance:
        return {
            "taxable_basis": 0.0,
            "fictitious_return": 0.0,
            "tax_due": 0.0,
        }

    # Calculate weighted fictitious return
    # 2024 rates approx: cash = 1.03%, investments = 6.04%
    fictitious_cash_return = cash_eur * 0.0103
    fictitious_inv_return = invested_eur * 0.0604
    total_fictitious_return = fictitious_cash_return + fictitious_inv_return
    
    # Prorate the return by the taxable percentage
    taxable_ratio = (total_wealth - tax_free_allowance) / total_wealth
    taxable_return = total_fictitious_return * taxable_ratio
    
    # Flat tax rate of 36%
    tax_due = taxable_return * 0.36

    return {
        "taxable_basis": total_wealth - tax_free_allowance,
        "fictitious_return": taxable_return,
        "tax_due": tax_due,
    }


def render():
    conn = database.connect(DB_PATH)
    
    # Ensure profile row exists
    profile = conn.execute("SELECT * FROM tax_profile WHERE id = 1").fetchone()
    
    if not profile or profile["gross_annual_income"] == 0:
        # Estimate gross income from recent salary/income transactions (approx 70% retention)
        monthly_income_rows = conn.execute(
            "SELECT strftime('%Y-%m', booking_date) as m, SUM(amount_eur) as amt "
            "FROM v_transactions WHERE category_kind = 'income' AND is_internal_transfer = 0 "
            "GROUP BY m ORDER BY m DESC LIMIT 6"
        ).fetchall()
        
        avg_monthly_net = sum(r["amt"] for r in monthly_income_rows) / len(monthly_income_rows) if monthly_income_rows else 0
        avg_monthly_gross = avg_monthly_net / 0.7 if avg_monthly_net > 0 else 0
        
        # Base annual = 12 * monthly + 8% holiday allowance
        default_gross = int((avg_monthly_gross * 12) * 1.08)
        
        with conn:
            if not profile:
                conn.execute("INSERT INTO tax_profile (id, gross_annual_income, has_fiscal_partner) VALUES (1, ?, 0)", (default_gross,))
            elif default_gross > 0:
                conn.execute("UPDATE tax_profile SET gross_annual_income = ? WHERE id = 1", (default_gross,))
        profile = conn.execute("SELECT * FROM tax_profile WHERE id = 1").fetchone()

    st.markdown("## 💶 Tax Analysis (NL)")
    st.markdown("Estimate your Dutch income tax (Box 1) and wealth tax (Box 3) based on your tracked assets and salary.")

    # 1. Tax Profile Settings
    from ui.dialogs import tax_profile_dialog
    if st.button("⚙️ Edit Tax Profile", type="primary" if profile["gross_annual_income"] == 0 else "secondary"):
        tax_profile_dialog()

    current_income = float(profile["gross_annual_income"])
    has_partner = bool(profile["has_fiscal_partner"])

    # 2. Get Net Worth data for Box 3
    from services.analytics import calculate_current_net_worth
    nw_data = calculate_current_net_worth(conn)
    cash_bal = nw_data["liquid_cash"]
    investments_bal = nw_data["invested"]
    
    conn.close()

    if current_income == 0:
        st.info("Please set your Gross Annual Income above to see your tax breakdown.")
        return

    # Calculations
    box1 = calculate_box1_tax(current_income)
    box3 = calculate_box3_tax(cash_bal, investments_bal, has_partner)
    tax_statement = generate_dutch_tax_statement()

    # 3. Box 1 Display
    section_header("Box 1: Income from Work & Home", "Estimated annual income tax based on 2024 brackets.")
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        g_str = "€****" if is_hidden() else f"€{current_income:,.2f}"
        kpi_card("Gross Income", g_str)
    with c2:
        net_str = "€****" if is_hidden() else f"€{box1['net_income']:,.2f}"
        ret_sub = "****" if is_hidden() else f"{(box1['net_income'] / current_income)*100:.1f}% retention"
        kpi_card("Net Income", net_str, subtext=ret_sub)
    with c3:
        tax_str = "€****" if is_hidden() else f"€{box1['total_tax']:,.2f}"
        rate_sub = "****" if is_hidden() else f"{(box1['total_tax'] / current_income)*100:.1f}% effective tax"
        kpi_card("Total Tax (Box 1)", tax_str, subtext=rate_sub)
    with c4:
        hra_val = tax_statement["deductible_mortgage_interest"]
        hra_refund = tax_statement["mortgage_interest_refund"]
        hra_str = "€****" if is_hidden() else f"€{hra_val:,.2f}"
        hra_sub = "****" if is_hidden() else f"+€{hra_refund:,.2f} tax benefit"
        kpi_card("Mortgage HRA (Paid)", hra_str, subtext=hra_sub)
        
    b1_str = "€****" if is_hidden() else f"€{box1['bracket1_tax']:,.2f}"
    b2_str = "€****" if is_hidden() else f"€{box1['bracket2_tax']:,.2f}"
    st.caption(f"Bracket 1 (<€75,518 at 36.97%): **{b1_str}** | Bracket 2 (>€75,518 at 49.50%): **{b2_str}**")

    # 4. Box 3 Display
    section_header("Box 3: Wealth & Savings", "Estimated annual wealth tax based on 2024 fictitious yields (ignoring debts).")
    c1, c2, c3 = st.columns(3)
    with c1:
        assets_str = "€****" if is_hidden() else f"€{cash_bal + investments_bal:,.2f}"
        sub_str = "Cash: €**** | Inv: €****" if is_hidden() else f"Cash: €{cash_bal:,.0f} | Inv: €{investments_bal:,.0f}"
        kpi_card("Taxable Assets", assets_str, subtext=sub_str)
    with c2:
        allowance_val = 114000 if has_partner else 57000
        allowance_str = "€****" if is_hidden() else f"€{allowance_val:,.2f}"
        kpi_card("Tax-free Allowance", allowance_str, subtext="Fiscal partner active" if has_partner else "Single allowance")
    with c3:
        b3_str = "€****" if is_hidden() else f"€{box3['tax_due']:,.2f}"
        ret_sub = "Fictitious return: €****" if is_hidden() else f"Fictitious return: €{box3['fictitious_return']:,.2f}"
        kpi_card("Total Tax (Box 3)", b3_str, subtext=ret_sub)

    if box3['tax_due'] == 0:
        st.success("🎉 Your assets fall below the tax-free allowance. No Box 3 tax is owed.")
        
    # Charts
    st.markdown("---")
    col1, col2 = st.columns(2)
    
    with col1:
        # Income Breakdown Pie
        df_box1 = pd.DataFrame([
            {"Category": "Net Income", "Amount": box1['net_income']},
            {"Category": "Box 1 Tax", "Amount": box1['total_tax']}
        ])
        fig1 = px.pie(df_box1, names='Category', values='Amount', title='Income Breakdown', hole=0.4)
        fig1.update_layout(margin=dict(t=40, b=0, l=0, r=0))
        if is_hidden():
            fig1.update_traces(hovertemplate="Censored<extra></extra>")
        st.plotly_chart(fig1, use_container_width=True)

    with col2:
        # Box 3 Breakdown Pie
        df_box3 = pd.DataFrame([
            {"Category": "Tax-free Allowance", "Amount": min(cash_bal + investments_bal, 114000 if has_partner else 57000)},
            {"Category": "Taxable Basis", "Amount": box3['taxable_basis']}
        ])
        if (cash_bal + investments_bal) > 0:
            fig2 = px.pie(df_box3, names='Category', values='Amount', title='Asset Taxability (Box 3)', hole=0.4)
            fig2.update_layout(margin=dict(t=40, b=0, l=0, r=0))
            if is_hidden():
                fig2.update_traces(hovertemplate="Censored<extra></extra>")
            st.plotly_chart(fig2, use_container_width=True)

    # 5. Official Belastingdienst Tax Filing Statement & Export
    section_header("📋 Tax Filing Statement (Aangifte Inkomstenbelasting)", "Itemized summary for your annual tax declaration")
    report_df = tax_statement["report_df"].copy()
    if is_hidden():
        report_df["Amount (€)"] = "€****"
    else:
        report_df["Amount (€)"] = report_df["Amount (€)"].map(lambda x: f"€{x:,.2f}" if abs(x) > 0 else "—")
    
    col_t_table, col_t_dl = st.columns([3, 1])
    with col_t_table:
        st.dataframe(report_df, use_container_width=True, hide_index=True)
    with col_t_dl:
        st.download_button(
            label="📥 Export Statement (CSV)",
            data=tax_statement["csv_content"],
            file_name=f"tax_filing_statement_{tax_statement['tax_year']}.csv",
            mime="text/csv",
            use_container_width=True,
        )

