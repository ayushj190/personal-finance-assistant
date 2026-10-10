import streamlit as st
from db import database
from config import DB_PATH
from datetime import date, datetime
from services.mortgage import sync_liability_schedule

@st.dialog("📝 Complete Tax Profile")
def tax_profile_dialog():
    conn = database.connect(DB_PATH)
    profile = conn.execute("SELECT * FROM tax_profile WHERE id = 1").fetchone()
    if not profile:
        profile = {"gross_annual_income": 0, "has_fiscal_partner": 0, "has_30_percent_ruling": 0, "is_entrepreneur": 0, "owns_home": 0, "birth_year": 1990, "has_13th_month": 0, "expected_bonus_eur": 0, "pension_contribution_pct": 0, "employer_pension_match_pct": 0}
        
    with st.form("copilot_tax_profile_form"):
        gross_annual_income = st.number_input("Gross Annual Income (€)", min_value=0.0, value=float(profile["gross_annual_income"]), step=1000.0)
        
        c1, c2 = st.columns(2)
        with c1:
            has_fiscal_partner = st.checkbox("Has Fiscal Partner", value=bool(profile["has_fiscal_partner"]))
            has_30_percent_ruling = st.checkbox("Has 30% Ruling", value=bool(profile["has_30_percent_ruling"]))
            is_entrepreneur = st.checkbox("Is Entrepreneur", value=bool(profile["is_entrepreneur"]))
            owns_home = st.checkbox("Owns Home", value=bool(profile["owns_home"]))
            has_13th_month = st.checkbox("Has 13th Month", value=bool(dict(profile).get("has_13th_month", 0)))
        with c2:
            b_year = profile["birth_year"]
            birth_year = st.number_input("Birth Year", min_value=1900, max_value=2100, value=int(b_year) if b_year else 1990, step=1)
            expected_bonus_eur = st.number_input("Expected Bonus (€)", min_value=0.0, value=float(dict(profile).get("expected_bonus_eur", 0)), step=500.0)
            pension_contribution_pct = st.number_input("Pension Contribution (%)", min_value=0.0, max_value=100.0, value=float(dict(profile).get("pension_contribution_pct", 0)), step=1.0)
            employer_pension_match_pct = st.number_input("Employer Pension Match (%)", min_value=0.0, max_value=100.0, value=float(dict(profile).get("employer_pension_match_pct", 0)), step=1.0)
            
        col1, col2 = st.columns(2)
        with col1:
            if st.form_submit_button("Save Tax Profile", use_container_width=True, type="primary"):
                from agent.tools import tool_save_tax_profile
                res = tool_save_tax_profile(
                    gross_annual_income, has_fiscal_partner, has_30_percent_ruling, is_entrepreneur, owns_home,
                    birth_year, has_13th_month, expected_bonus_eur, pension_contribution_pct, employer_pension_match_pct
                )
                if "copilot_history" in st.session_state:
                    st.session_state.copilot_history.append({"role": "assistant", "content": "✅ " + res["message"]})
                if "pending_form" in st.session_state:
                    del st.session_state["pending_form"]
                conn.close()
                st.rerun()
        with col2:
            if st.form_submit_button("Cancel", use_container_width=True):
                if "pending_form" in st.session_state:
                    del st.session_state["pending_form"]
                conn.close()
                st.rerun()
    conn.close()

@st.dialog("📝 Complete Risk Profile")
def risk_profile_dialog():
    conn = database.connect(DB_PATH)
    profile = conn.execute("SELECT * FROM risk_profiles ORDER BY id DESC LIMIT 1").fetchone()
    
    with st.form("risk_profile_form"):
        risk_score = st.slider("Risk Score (1-10)", 1, 10, int(profile["risk_score"]) if profile else 5)
        risk_tolerance_opts = ["Conservative", "Moderate", "Aggressive"]
        risk_idx = risk_tolerance_opts.index(profile["risk_tolerance"]) if profile and profile["risk_tolerance"] in risk_tolerance_opts else 1
        risk_tolerance = st.selectbox("Risk Tolerance", risk_tolerance_opts, index=risk_idx)
        notes = st.text_input("Notes", value=profile["notes"] if profile else "")
        investment_horizon_years = st.number_input("Investment Horizon (Years)", min_value=1, step=1, value=int(profile["investment_horizon_years"]) if profile else 10)
        
        liquidity_opts = ["Low", "Medium", "High"]
        liq_idx = liquidity_opts.index(profile["liquidity_needs"]) if profile and profile["liquidity_needs"] in liquidity_opts else 1
        liquidity_needs = st.selectbox("Liquidity Needs", liquidity_opts, index=liq_idx)
        
        exp_opts = ["None", "Beginner", "Intermediate", "Advanced"]
        exp_idx = exp_opts.index(profile["investment_experience"]) if profile and profile["investment_experience"] in exp_opts else 1
        investment_experience = st.selectbox("Investment Experience", exp_opts, index=exp_idx)
        
        col1, col2 = st.columns(2)
        with col1:
            if st.form_submit_button("Save Risk Profile", use_container_width=True, type="primary"):
                from agent.tools import tool_save_risk_profile
                res = tool_save_risk_profile(
                    risk_score, risk_tolerance, notes, {}, investment_horizon_years, liquidity_needs, investment_experience
                )
                if "copilot_history" in st.session_state:
                    st.session_state.copilot_history.append({"role": "assistant", "content": "✅ " + res["message"]})
                if "pending_form" in st.session_state:
                    del st.session_state["pending_form"]
                conn.close()
                st.rerun()
        with col2:
            if st.form_submit_button("Cancel", use_container_width=True):
                if "pending_form" in st.session_state:
                    del st.session_state["pending_form"]
                conn.close()
                st.rerun()
    conn.close()

@st.dialog("⚙️ Configure Mortgage / Loan")
def mortgage_config_dialog(existing_lib_id=None):
    conn = database.connect(DB_PATH)
    existing_lib = None
    existing_rp = None
    if existing_lib_id:
        existing_lib = conn.execute("SELECT * FROM liabilities WHERE id = ?", (existing_lib_id,)).fetchone()
    if existing_lib:
        existing_rp = conn.execute("SELECT * FROM liability_rate_periods WHERE liability_id = ? ORDER BY from_date ASC LIMIT 1", (existing_lib["id"],)).fetchone()
        
    with st.form("mortgage_config_dialog_form"):
        c1, c2 = st.columns(2)
        with c1:
            loan_name = st.text_input("Loan Name", value=existing_lib["name"] if existing_lib else "Leningdeel 1")
            lender = st.text_input("Lender", value=existing_lib["lender"] if existing_lib else "ABN AMRO")
            loan_type = st.selectbox("Loan Type", options=["annuity", "linear", "interest_only"], index=0 if not existing_lib else ["annuity", "linear", "interest_only"].index(existing_lib["loan_type"]))
            orig_principal = st.number_input("Original Principal (€)", value=float(existing_lib["original_principal_minor"] / 100.0) if existing_lib else 400000.0, step=5000.0)
            default_home_val = float(existing_lib["home_value_minor"] / 100.0) if (existing_lib and existing_lib["home_value_minor"] is not None) else (float(existing_lib["original_principal_minor"] / 100.0) if existing_lib else 450000.0)
            home_value = st.number_input("Property / Home Value (€)", value=float(default_home_val), step=5000.0, min_value=0.0)
        with c2:
            term_months = st.number_input("Term (Months)", value=int(existing_lib["term_months"]) if existing_lib else 360, step=12)
            start_date = st.date_input("Start Date", value=datetime.strptime(existing_lib["start_date"][:10], "%Y-%m-%d").date() if existing_lib else date(2024, 1, 1))
            saved_rate = (existing_rp["annual_rate"] * 100.0) if existing_rp else 3.85
            annual_rate_pct = st.number_input("Initial Interest Rate (%)", value=float(saved_rate), step=0.05, format="%.2f")
            fixed_years = st.number_input("Rate Fixed Period (Years)", value=10, step=1)
            
        st.markdown("##### Manual Balance Override (Optional)")
        co1, co2 = st.columns(2)
        with co1:
            override_val = float(existing_lib["balance_override_minor"] / 100.0) if (existing_lib and existing_lib["balance_override_minor"]) else 0.0
            bal_override = st.number_input("Statement Balance Override (€)", value=override_val, step=1000.0, min_value=0.0)
        with co2:
            bal_override_dt = st.date_input("Override Date", value=datetime.strptime(existing_lib["balance_override_date"][:10], "%Y-%m-%d").date() if (existing_lib and existing_lib["balance_override_date"]) else date.today())
            
        col1, col2 = st.columns(2)
        with col1:
            if st.form_submit_button("Save Mortgage", use_container_width=True, type="primary"):
                principal_minor = int(round(orig_principal * 100))
                home_val_minor = int(round(home_value * 100)) if home_value > 0 else None
                override_minor = int(round(bal_override * 100)) if bal_override > 0 else None
                override_date_str = bal_override_dt.isoformat() if bal_override > 0 else None
                with conn:
                    if existing_lib:
                        conn.execute("UPDATE liabilities SET name = ?, lender = ?, loan_type = ?, original_principal_minor = ?, home_value_minor = ?, term_months = ?, start_date = ?, balance_override_minor = ?, balance_override_date = ? WHERE id = ?", (loan_name, lender, loan_type, principal_minor, home_val_minor, term_months, start_date.isoformat(), override_minor, override_date_str, existing_lib["id"]))
                        lib_id = existing_lib["id"]
                    else:
                        cur = conn.execute("INSERT INTO liabilities (name, lender, loan_type, original_principal_minor, home_value_minor, term_months, start_date, balance_override_minor, balance_override_date) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", (loan_name, lender, loan_type, principal_minor, home_val_minor, term_months, start_date.isoformat(), override_minor, override_date_str))
                        lib_id = cur.lastrowid
                    conn.execute("DELETE FROM liability_rate_periods WHERE liability_id = ?", (lib_id,))
                    fixed_until = date(start_date.year + int(fixed_years), start_date.month, start_date.day).isoformat()
                    conn.execute("INSERT INTO liability_rate_periods (liability_id, from_date, annual_rate, fixed_until) VALUES (?, ?, ?, ?)", (lib_id, start_date.isoformat(), float(annual_rate_pct) / 100.0, fixed_until))
                sync_liability_schedule(conn, lib_id)
                if "copilot_history" in st.session_state:
                    st.session_state.copilot_history.append({"role": "assistant", "content": f"✅ Mortgage '{loan_name}' configured successfully!"})
                if "pending_form" in st.session_state:
                    del st.session_state["pending_form"]
                conn.close()
                st.rerun()
        with col2:
            if st.form_submit_button("Cancel", use_container_width=True):
                if "pending_form" in st.session_state:
                    del st.session_state["pending_form"]
                conn.close()
                st.rerun()
    conn.close()
