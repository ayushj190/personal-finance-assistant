import pandas as pd
import streamlit as st
import plotly.express as px

from config import DB_PATH
from db import database
from ui.components import section_header, kpi_card, is_hidden
from services.tax_report_service import generate_dutch_tax_statement
from services.tax_optimizer import (
    calculate_jaarruimte,
    calculate_groenfondsen_arbitrage,
    simulate_capital_allocation_tradeoff,
    CERTIFIED_DUTCH_GREEN_FUNDS,
)
from services.legal_vault_service import (
    search_legal_vault,
    get_all_legal_documents,
    get_all_chunks_for_document,
    ingest_legal_corpus,
)



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


def calculate_box3_tax(cash_eur: float, invested_eur: float, has_fiscal_partner: bool, green_investments_eur: float = 0.0) -> dict:
    """Simplified Box 3 Dutch wealth tax calculation (2024 fictitious yields)."""
    tax_free_allowance = 114000.0 if has_fiscal_partner else 57000.0
    green_cap = 142502.0 if has_fiscal_partner else 71251.0
    exempt_green = min(max(0.0, green_investments_eur), green_cap)
    
    taxable_investments = max(0.0, invested_eur - exempt_green)
    total_wealth = cash_eur + taxable_investments

    if total_wealth <= tax_free_allowance:
        return {
            "taxable_basis": 0.0,
            "fictitious_return": 0.0,
            "tax_due": 0.0,
            "exempt_green": exempt_green,
        }

    # Calculate weighted fictitious return
    fictitious_cash_return = cash_eur * 0.0103
    fictitious_inv_return = taxable_investments * 0.0604
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
        "exempt_green": exempt_green,
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

    green_val = (float(dict(profile).get("green_investments_minor", 0)) / 100.0) if "green_investments_minor" in profile.keys() else 0.0
    factor_a_val = (float(dict(profile).get("factor_a_minor", 0)) / 100.0) if "factor_a_minor" in profile.keys() else 0.0

    # Calculations
    box1 = calculate_box1_tax(current_income)
    box3 = calculate_box3_tax(cash_bal, investments_bal, has_partner, green_investments_eur=green_val)
    tax_statement = generate_dutch_tax_statement()

    # 3. Box 1 Display
    with section_header("Box 1: Income from Work & Home", "Estimated annual income tax based on 2024 brackets."):
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
    with section_header("Box 3: Wealth & Savings", "Estimated annual wealth tax based on 2024 fictitious yields (ignoring debts)."):
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
    with section_header("📋 Tax Filing Statement (Aangifte Inkomstenbelasting)", "Itemized summary for your annual tax declaration"):
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

    # 6. AI Capital Allocation & Tax Optimizer
    with section_header("⚡ AI Capital Allocation & Tax Optimizer", "Simulate strategic returns across Mortgage Prepayment, Pillar 3 Pension, Green Funds, and ETFs"):
        opt_col1, opt_col2 = st.columns(2)
        with opt_col1:
            sim_capital = st.slider("Capital to Allocate (€)", min_value=1000, max_value=50000, value=10000, step=1000)
        with opt_col2:
            sim_years = st.slider("Investment Horizon (Years)", min_value=1, max_value=30, value=10, step=1)

        sim_conn = database.connect(DB_PATH)
        sim_data = simulate_capital_allocation_tradeoff(sim_capital, sim_years, conn=sim_conn)
        sim_conn.close()

        sc1, sc2, sc3, sc4 = st.columns(4)
        with sc1:
            m_val = sim_data["final_values"]["mortgage"]
            m_str = "€****" if is_hidden() else f"€{m_val:,.0f}"
            kpi_card("Mortgage Prepayment", m_str, subtext=f"Net rate {sim_data['mortgage_net_rate_pct']:.2f}% (risk-free)")
        with sc2:
            p_val = sim_data["final_values"]["pension"]
            p_str = "€****" if is_hidden() else f"€{p_val:,.0f}"
            ref_str = "€****" if is_hidden() else f"+€{sim_data['immediate_pension_refund_eur']:,.0f} refund"
            kpi_card("Pillar 3 (Jaarruimte)", p_str, subtext=ref_str)
        with sc3:
            g_val = sim_data["final_values"]["green"]
            g_str = "€****" if is_hidden() else f"€{g_val:,.0f}"
            kpi_card("Certified Groenfonds", g_str, subtext="Liquid + 2.27% tax alpha")
        with sc4:
            e_val = sim_data["final_values"]["taxable_etf"]
            e_str = "€****" if is_hidden() else f"€{e_val:,.0f}"
            kpi_card("Taxable Box 3 ETF", e_str, subtext="7% gross - 2.17% drag")

        sim_df = sim_data["trajectory_df"]
        fig_sim = px.line(
            sim_df,
            x="Year",
            y=["Mortgage Prepayment", "Pillar 3 Pension (Jaarruimte)", "Certified Groenfonds", "Taxable Box 3 ETF"],
            title=f"Net Wealth Trajectory: €{sim_capital:,.0f} Lump Sum Allocation over {sim_years} Years",
            labels={"value": "Projected Net Wealth (€)", "variable": "Allocation Strategy"},
            markers=True,
        )
        fig_sim.update_layout(
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            margin=dict(l=55, r=20, t=50, b=25),
            hovermode="x unified",
            yaxis=dict(tickprefix="€", tickformat="~s", automargin=True),
            xaxis=dict(automargin=True),
        )
        if is_hidden():
            fig_sim.update_traces(hovertemplate="Censored<extra></extra>")
        st.plotly_chart(fig_sim, use_container_width=True)

    # 7. Green Funds & Pillar 3 Pension Analysis
    with section_header("🌱 Green Funds & Pillar 3 Pension (Jaarruimte)", "Optimize tax deductions under Dutch regulations"):
        pension_res = calculate_jaarruimte(current_income, factor_a=factor_a_val)
        green_res = calculate_groenfondsen_arbitrage(cash_bal + investments_bal, current_green=green_val, has_fiscal_partner=has_partner)

        gc1, gc2, gc3, gc4 = st.columns(4)
        with gc1:
            jr_str = "€****" if is_hidden() else f"€{pension_res['annual_jaarruimte']:,.0f}"
            kpi_card("Jaarruimte Space", jr_str, subtext=f"Factor A: €{factor_a_val:,.0f}")
        with gc2:
            reb_str = "€****" if is_hidden() else f"+€{pension_res['immediate_tax_rebate']:,.0f}"
            kpi_card("Immediate Box 1 Rebate", reb_str, subtext=f"{pension_res['marginal_tax_rate']*100:.1f}% marginal bracket")
        with gc3:
            gr_used = green_res["effective_exempt_green"]
            gr_str = "€****" if is_hidden() else f"€{gr_used:,.0f} / €{green_res['exemption_cap']:,.0f}"
            kpi_card("Green Fund Exemption", gr_str, subtext="Box 3 exempt cap")
        with gc4:
            alpha_str = "€****" if is_hidden() else f"€{green_res['total_annual_tax_benefit']:,.2f}"
            kpi_card("Annual Green Tax Alpha", alpha_str, subtext=f"~{green_res['guaranteed_tax_alpha_pct']:.2f}% guaranteed")

        with st.expander("🌿 View Certified Dutch Green Funds List & Specifications"):
            st.dataframe(pd.DataFrame(CERTIFIED_DUTCH_GREEN_FUNDS), use_container_width=True, hide_index=True)

    # 8. Dutch Financial Law Vault (Hybrid Vector Explorer)
    with section_header("📚 Dutch Financial Law Vector Vault", "Local SQLite vector database with hybrid search & statutory citations"):
        col_ctrl1, col_ctrl2 = st.columns([3, 1])
        with col_ctrl1:
            search_query = st.text_input(
                "🔍 Search Dutch legislation, tax codes & court rulings...",
                "",
                placeholder="e.g. Art. 3.16, werkelijk rendement box 3, hypotheekrenteaftrek, Wtp jaarruimte...",
                key="legal_vault_search_input",
            )
        with col_ctrl2:
            category_opts = {
                "All Domains": None,
                "Box 1 Income": "tax_box1",
                "Box 3 Wealth": "tax_box3",
                "Pensions & Jaarruimte": "pension",
                "Mortgages & Wft": "mortgage",
                "Gifting & Estate": "estate",
                "Expat 30% Facility": "expat",
                "Green Funds": "green_funds",
            }
            selected_cat_label = st.selectbox("Filter Domain", list(category_opts.keys()), key="legal_vault_domain_filter")
            selected_cat = category_opts[selected_cat_label]

        if search_query.strip():
            matched_results = search_legal_vault(search_query, category=selected_cat, top_k=6)
            if matched_results:
                st.caption(f"Retrieved {len(matched_results)} matching provisions via Reciprocal Rank Fusion (sqlite-vec + FTS5):")
                for res in matched_results:
                    match_pct = int(res.score * 100)
                    with st.expander(f"📜 {res.article_ref} — {res.chunk_title} ({match_pct}% match)", expanded=True):
                        st.markdown(f"**Statute**: *{res.doc_title}* | **Effective Year**: `{res.effective_year}` | **Category**: `{res.category}`")
                        if res.summary:
                            st.info(f"💡 **Plain Language Digest**: {res.summary}")
                        if res.juriconnect_ref:
                            st.caption(f"🔗 Juriconnect Reference: `{res.juriconnect_ref}`")
                        st.markdown("**Statutory Text / Legal Ruling:**")
                        st.markdown(res.content)
            else:
                st.info("No matching statutory articles found in the local vector vault for this query.")
        else:
            legal_docs = get_all_legal_documents()
            st.markdown(f"**Statutory Knowledge Base ({len(legal_docs)} statutes indexed across 6 domains):**")
            for doc in legal_docs:
                chunks = get_all_chunks_for_document(doc["id"])
                cat_badge = doc.get("category", "general")
                with st.expander(f"🏛️ {doc['title']} ({len(chunks)} articles) — `{cat_badge}`"):
                    st.caption(f"Official BWB ID: `{doc.get('bwb_id') or 'N/A'}` | Source: {doc.get('source_url') or 'wetten.overheid.nl'}")
                    for ch in chunks:
                        with st.expander(f"📄 {ch['article_ref']}: {ch['chunk_title']}", expanded=False):
                            if ch.get("summary"):
                                st.markdown(f"**Digest**: {ch['summary']}")
                            st.markdown(ch.get("content", ""))

        st.divider()
        col_btn, _ = st.columns([2, 4])
        with col_btn:
            if st.button("🔄 Reindex Legal Knowledge Corpus", use_container_width=True):
                ingest_res = ingest_legal_corpus(force_reindex=True)
                st.success(f"Successfully reindexed {ingest_res.get('documents_indexed')} statutes and {ingest_res.get('chunks_indexed')} statutory chunks!")
                st.rerun()


