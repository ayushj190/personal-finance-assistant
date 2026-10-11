from datetime import date, datetime
import pandas as pd
import streamlit as st

from config import DB_PATH
from db import database
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
            b_year = profile["birth_year"] if "birth_year" in profile.keys() else 1990
            birth_year = st.number_input("Birth Year", min_value=1900, max_value=2100, value=int(b_year) if b_year else 1990, step=1)
            expected_bonus_eur = st.number_input("Expected Bonus (€)", min_value=0.0, value=float(dict(profile).get("expected_bonus_eur", 0)), step=500.0)
            pension_contribution_pct = st.number_input("Pension Contribution (%)", min_value=0.0, max_value=100.0, value=float(dict(profile).get("pension_contribution_pct", 0)), step=1.0)
            employer_pension_match_pct = st.number_input("Employer Pension Match (%)", min_value=0.0, max_value=100.0, value=float(dict(profile).get("employer_pension_match_pct", 0)), step=1.0)

        st.markdown("##### 🏛️ Pension Gap & Green Investment Optimization")
        c3, c4 = st.columns(2)
        with c3:
            fa_val = (float(dict(profile).get("factor_a_minor", 0)) / 100.0) if "factor_a_minor" in profile.keys() else 0.0
            factor_a = st.number_input("Factor A (€) - from annual pension UPO", min_value=0.0, value=fa_val, step=100.0, help="Annual pension accrual from employer UPO for Jaarruimte calculation")
        with c4:
            green_val = (float(dict(profile).get("green_investments_minor", 0)) / 100.0) if "green_investments_minor" in profile.keys() else 0.0
            green_investments_eur = st.number_input("Certified Green Investments (€)", min_value=0.0, value=green_val, step=1000.0, help="Groenfondsen (exempt up to €71,251 single / €142,502 partners in Box 3)")

        col1, col2 = st.columns(2)
        with col1:
            if st.form_submit_button("Save Tax Profile", use_container_width=True, type="primary"):
                from agent.tools import tool_save_tax_profile
                res = tool_save_tax_profile(
                    gross_annual_income, has_fiscal_partner, has_30_percent_ruling, is_entrepreneur, owns_home,
                    birth_year, has_13th_month, expected_bonus_eur, pension_contribution_pct, employer_pension_match_pct,
                    factor_a, green_investments_eur, 0.0
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


@st.dialog("✏️ Set Category Budgets")
def set_category_budget_dialog(conn=None):
    """Modal dialog to configure monthly spending budget caps for expense categories."""
    close_on_exit = False
    if conn is not None:
        try:
            conn.execute("SELECT 1")
        except Exception:
            conn = None

    if conn is None:
        conn = database.connect(DB_PATH)
        close_on_exit = True
    try:
        from services.budget_service import get_all_category_budgets, set_category_budget

        # Fetch deduplicated parent and child categories
        cats = conn.execute(
            """
            SELECT MIN(c.id) as id, c.name, c.kind, c.parent_id
            FROM categories c
            WHERE c.kind IN ('fixed', 'discretionary') AND c.name != 'Uncategorized'
            GROUP BY LOWER(c.name), COALESCE(c.parent_id, -1)
            ORDER BY c.parent_id IS NOT NULL, c.name ASC
            """
        ).fetchall()

        if not cats:
            st.info("No expense categories found to configure.")
            return

        budgets = get_all_category_budgets(conn)

        tab_fixed, tab_disc = st.tabs(["🔒 Fixed Expenses", "🛍️ Discretionary Spend"])

        for tab, tab_kind, icon in [
            (tab_fixed, "fixed", "🔒"),
            (tab_disc, "discretionary", "🛍️"),
        ]:
            with tab:
                kind_cats = [c for c in cats if c["kind"] == tab_kind]
                parents = [c for c in kind_cats if c["parent_id"] is None]
                children = [c for c in kind_cats if c["parent_id"] is not None]

                # Build clean hierarchical options dict
                options_map = {}
                for p in parents:
                    options_map[p["id"]] = f"⭐ {p['name']} (Main)"
                    for s in children:
                        if s["parent_id"] == p["id"]:
                            options_map[s["id"]] = f"   ↳ {s['name']}"

                # Add orphan subcategories if any
                for s in children:
                    if s["id"] not in options_map:
                        options_map[s["id"]] = f"   ↳ {s['name']}"

                if not options_map:
                    st.caption(f"No {tab_kind} categories available.")
                    continue

                with st.form(f"set_{tab_kind}_budget_form"):
                    st.caption(f"Configure monthly spending caps for {tab_kind} categories.")
                    selected_id = st.selectbox(
                        "Category",
                        options=list(options_map.keys()),
                        format_func=lambda x: options_map[x],
                        key=f"dialog_{tab_kind}_cat_select",
                    )
                    curr_val = float(budgets.get(selected_id, 0.0))
                    new_val = st.number_input(
                        "Monthly Spending Limit (€)",
                        min_value=0.0,
                        value=curr_val,
                        step=50.0,
                        format="%.2f",
                        key=f"dialog_{tab_kind}_limit_input",
                        help="Set to 0.00 to mark as unbudgeted",
                    )

                    c_save, c_cancel = st.columns(2)
                    with c_save:
                        save_clicked = st.form_submit_button(
                            "Save Budget", type="primary", use_container_width=True
                        )
                    with c_cancel:
                        cancel_clicked = st.form_submit_button("Cancel", use_container_width=True)

                    if save_clicked:
                        set_category_budget(conn, selected_id, new_val)
                        st.success(f"Saved €{new_val:,.2f} limit for {options_map[selected_id]}!")
                        st.rerun(scope="app")
                    elif cancel_clicked:
                        st.rerun(scope="app")

                # Show current budgets table for this group
                active_rows = []
                for cid, cname in options_map.items():
                    b_val = budgets.get(cid, 0.0)
                    if b_val > 0:
                        clean_lbl = cname.replace("⭐ ", "").replace("   ↳ ", "")
                        active_rows.append({"Category": clean_lbl, "Monthly Limit (€)": f"€{b_val:,.2f}"})

                if active_rows:
                    st.markdown("**Active Budgets:**")
                    st.dataframe(pd.DataFrame(active_rows), use_container_width=True, hide_index=True)
    finally:
        if close_on_exit:
            conn.close()


@st.dialog("🏠 Assign Transaction to Mortgage")
def assign_mortgage_dialog(conn=None, tx_id=None):
    """Modal dialog to link an uncategorized transaction directly to a mortgage liability."""
    close_on_exit = False
    if conn is not None:
        try:
            conn.execute("SELECT 1")
        except Exception:
            conn = None

    if conn is None:
        conn = database.connect(DB_PATH)
        close_on_exit = True
    try:
        liabilities = conn.execute("SELECT * FROM liabilities ORDER BY name ASC").fetchall()

        # Query uncategorized transactions
        if tx_id:
            uncat_rows = conn.execute(
                """
                SELECT t.id, t.booking_date, a.name AS account,
                       COALESCE(NULLIF(t.merchant_normalized, ''), t.description_raw) AS merchant,
                       -t.amount_eur_minor / 100.0 AS amount_eur,
                       t.amount_eur_minor,
                       t.description_raw
                FROM transactions t
                JOIN accounts a ON a.id = t.account_id
                WHERE t.id = ?
                """,
                (tx_id,),
            ).fetchall()
        else:
            uncat_rows = conn.execute(
                """
                SELECT t.id, t.booking_date, a.name AS account,
                       COALESCE(NULLIF(t.merchant_normalized, ''), t.description_raw) AS merchant,
                       -t.amount_eur_minor / 100.0 AS amount_eur,
                       t.amount_eur_minor,
                       t.description_raw
                FROM transactions t
                JOIN accounts a ON a.id = t.account_id
                WHERE (t.category_id IS NULL OR t.category_id = (SELECT id FROM categories WHERE name = 'Uncategorized' LIMIT 1))
                  AND t.amount_eur_minor < 0
                  AND t.is_internal_transfer = 0
                ORDER BY abs(t.amount_eur_minor) DESC
                LIMIT 50
                """
            ).fetchall()

        if not uncat_rows:
            st.info("🎉 No uncategorized transactions available to assign.")
            return

        tx_options = {}
        for r in uncat_rows:
            lbl = f"{r['booking_date']} — €{r['amount_eur']:,.2f} — {str(r['merchant'])[:40]}"
            tx_options[r["id"]] = (lbl, r)

        with st.form("assign_mortgage_dialog_form"):
            st.caption("Link this expense to your mortgage loan to sync payment schedules and category tracking.")
            default_tx_id = tx_id if (tx_id and tx_id in tx_options) else list(tx_options.keys())[0]
            chosen_tx_id = st.selectbox(
                "Uncategorized Transaction",
                options=list(tx_options.keys()),
                index=list(tx_options.keys()).index(default_tx_id),
                format_func=lambda x: tx_options[x][0],
                key="dialog_mortgage_tx_select",
            )
            chosen_tx = tx_options[chosen_tx_id][1]

            if liabilities:
                lib_map = {lib["id"]: f"{lib['name']} ({lib['lender']})" for lib in liabilities}
                chosen_lib_id = st.selectbox(
                    "Target Mortgage Loan",
                    options=list(lib_map.keys()),
                    format_func=lambda x: lib_map[x],
                    key="dialog_mortgage_lib_select",
                )
            else:
                chosen_lib_id = None
                st.warning("No mortgage loan configured yet. Set one up in Settings or Mortgage tab.")

            c1, c2 = st.columns(2)
            with c1:
                payment_kind = st.selectbox(
                    "Payment Assignment",
                    options=["Monthly Installment", "Extra Repayment (Boetevrij)"],
                    key="dialog_mortgage_payment_kind",
                )
            with c2:
                recalc_strat = "lower_payment"
                if payment_kind == "Extra Repayment (Boetevrij)":
                    recalc_strat = st.selectbox(
                        "Recalculation Benefit",
                        options=["lower_payment", "shorter_term"],
                        format_func=lambda x: "Lower Monthly Payment" if x == "lower_payment" else "Shorten Loan Term",
                        key="dialog_mortgage_recalc_strat",
                    )

            col1, col2 = st.columns(2)
            with col1:
                submitted = st.form_submit_button(
                    "Confirm Mortgage Assignment",
                    type="primary",
                    use_container_width=True,
                    disabled=chosen_lib_id is None,
                )
            with col2:
                cancelled = st.form_submit_button("Cancel", use_container_width=True)

            if submitted and chosen_lib_id is not None:
                mortgage_cat = conn.execute("SELECT id FROM categories WHERE name = 'Mortgage'").fetchone()
                if not mortgage_cat:
                    with conn:
                        cur = conn.execute("INSERT INTO categories (name, kind) VALUES ('Mortgage', 'fixed')")
                        mortgage_cat_id = cur.lastrowid
                else:
                    mortgage_cat_id = mortgage_cat["id"]

                tx_date = str(chosen_tx["booking_date"])
                tx_amount_minor = abs(int(chosen_tx["amount_eur_minor"]))
                tx_merchant = str(chosen_tx["merchant"] or "")

                with conn:
                    # 1. Update transaction category to Mortgage
                    conn.execute(
                        "UPDATE transactions SET category_id = ?, category_source = 'user' WHERE id = ?",
                        (mortgage_cat_id, chosen_tx["id"]),
                    )
                    # 2. Update merchant category rule
                    if tx_merchant:
                        database.upsert_category_rule(conn, tx_merchant, mortgage_cat_id, source="user")
                    # 3. Save payment match pattern on liability if unset
                    conn.execute(
                        "UPDATE liabilities SET payment_match_pattern = COALESCE(payment_match_pattern, ?) WHERE id = ?",
                        (tx_merchant, chosen_lib_id),
                    )
                    # 4. If extra repayment, record in liability_extra_payments
                    if payment_kind == "Extra Repayment (Boetevrij)":
                        conn.execute(
                            """
                            INSERT INTO liability_extra_payments (liability_id, paid_date, amount_minor, recalc)
                            VALUES (?, ?, ?, ?)
                            ON CONFLICT(liability_id, paid_date) DO UPDATE SET
                                amount_minor = excluded.amount_minor,
                                recalc = excluded.recalc
                            """,
                            (chosen_lib_id, tx_date, tx_amount_minor, recalc_strat),
                        )

                if payment_kind == "Extra Repayment (Boetevrij)":
                    sync_liability_schedule(conn, chosen_lib_id)

                st.success(f"Successfully linked €{chosen_tx['amount_eur']:,.2f} on {tx_date} to mortgage liability!")
                st.rerun(scope="app")
            elif cancelled:
                st.rerun(scope="app")
    finally:
        if close_on_exit:
            conn.close()
