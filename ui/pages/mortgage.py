from datetime import date, datetime
import pandas as pd
import streamlit as st

from config import DB_PATH
from db import database
from services.mortgage import calculate_mortgage_schedule, sync_liability_schedule
from ui.charts import build_mortgage_amortization_chart, build_mortgage_interest_principal_bar
from ui.components import format_money, kpi_card, section_header


def render_mortgage_editor(conn, existing_lib=None):
    existing_rp = None
    if existing_lib:
        existing_rp = conn.execute(
            "SELECT * FROM liability_rate_periods WHERE liability_id = ? ORDER BY from_date ASC LIMIT 1",
            (existing_lib["id"],),
        ).fetchone()

    with st.form("mortgage_config_form"):
        st.subheader("Configure Mortgage / Loan")
        c1, c2 = st.columns(2)
        with c1:
            loan_name = st.text_input("Loan Name", value=existing_lib["name"] if existing_lib else "Leningdeel 1")
            lender = st.text_input("Lender", value=existing_lib["lender"] if existing_lib else "ABN AMRO")
            loan_type = st.selectbox(
                "Loan Type",
                options=["annuity", "linear", "interest_only"],
                index=0 if not existing_lib else ["annuity", "linear", "interest_only"].index(existing_lib["loan_type"]),
            )
            orig_principal = st.number_input(
                "Original Principal (€)",
                value=float(existing_lib["original_principal_minor"] / 100.0) if existing_lib else 400000.0,
                step=5000.0,
            )
        with c2:
            term_months = st.number_input(
                "Term (Months)",
                value=int(existing_lib["term_months"]) if existing_lib else 360,
                step=12,
            )
            start_date = st.date_input(
                "Start Date",
                value=datetime.strptime(existing_lib["start_date"][:10], "%Y-%m-%d").date() if existing_lib else date(2024, 1, 1),
            )
            saved_rate = (existing_rp["annual_rate"] * 100.0) if existing_rp else 3.85
            annual_rate_pct = st.number_input(
                "Initial Interest Rate (%)",
                value=float(saved_rate),
                step=0.05,
                format="%.2f",
            )
            fixed_years = st.number_input("Rate Fixed Period (Years)", value=10, step=1)

        st.markdown("##### Manual Balance Override (Optional)")
        st.caption("If your actual bank balance differs from theoretical amortization, enter it here.")
        co1, co2 = st.columns(2)
        with co1:
            override_val = float(existing_lib["balance_override_minor"] / 100.0) if (existing_lib and existing_lib["balance_override_minor"]) else 0.0
            bal_override = st.number_input("Statement Balance Override (€)", value=override_val, step=1000.0, min_value=0.0)
        with co2:
            bal_override_dt = st.date_input(
                "Override Date",
                value=datetime.strptime(existing_lib["balance_override_date"][:10], "%Y-%m-%d").date() if (existing_lib and existing_lib["balance_override_date"]) else date.today(),
            )

        submitted = st.form_submit_button("Save Mortgage Configuration", type="primary")
        if submitted:
            principal_minor = int(round(orig_principal * 100))
            override_minor = int(round(bal_override * 100)) if bal_override > 0 else None
            override_date_str = bal_override_dt.isoformat() if bal_override > 0 else None
            with conn:
                if existing_lib:
                    conn.execute(
                        """
                        UPDATE liabilities SET
                            name = ?, lender = ?, loan_type = ?, original_principal_minor = ?,
                            term_months = ?, start_date = ?, balance_override_minor = ?, balance_override_date = ?
                        WHERE id = ?
                        """,
                        (loan_name, lender, loan_type, principal_minor, term_months, start_date.isoformat(), override_minor, override_date_str, existing_lib["id"]),
                    )
                    lib_id = existing_lib["id"]
                else:
                    cur = conn.execute(
                        """
                        INSERT INTO liabilities (name, lender, loan_type, original_principal_minor, term_months, start_date, balance_override_minor, balance_override_date)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (loan_name, lender, loan_type, principal_minor, term_months, start_date.isoformat(), override_minor, override_date_str),
                    )
                    lib_id = cur.lastrowid

                # Save rate period
                conn.execute("DELETE FROM liability_rate_periods WHERE liability_id = ?", (lib_id,))
                fixed_until = date(start_date.year + int(fixed_years), start_date.month, start_date.day).isoformat()
                conn.execute(
                    """
                    INSERT INTO liability_rate_periods (liability_id, from_date, annual_rate, fixed_until)
                    VALUES (?, ?, ?, ?)
                    """,
                    (lib_id, start_date.isoformat(), float(annual_rate_pct) / 100.0, fixed_until),
                )
            sync_liability_schedule(conn, lib_id)
            st.success("Mortgage saved and amortization schedule calculated successfully!")
            st.rerun()


def render():
    st.title("Mortgage & Liability Tracker")

    conn = database.connect(DB_PATH)
    liabilities = conn.execute("SELECT * FROM liabilities").fetchall()

    if not liabilities:
        st.info("No mortgage or liability configured yet. Enter your mortgage details below to generate the schedule.")
        render_mortgage_editor(conn)
        conn.close()
        return

    with st.expander("⚙️ Add / Edit Mortgage Configuration"):
        render_mortgage_editor(conn, existing_lib=liabilities[0])

    lib = dict(liabilities[0])
    lib_id = lib["id"]

    # Ensure schedule is generated
    sync_liability_schedule(conn, lib_id)

    schedule_df = pd.read_sql_query(
        "SELECT * FROM liability_schedule WHERE liability_id = ? ORDER BY month_idx ASC",
        conn,
        params=(lib_id,),
    )

    if schedule_df.empty:
        conn.close()
        st.warning("Schedule could not be computed.")
        return

    original_principal = lib["original_principal_minor"] / 100.0

    today_str = date.today().isoformat()
    if lib.get("balance_override_minor"):
        latest_balance = lib["balance_override_minor"] / 100.0
    else:
        past_sched = schedule_df[schedule_df["due_date"] <= today_str]
        if not past_sched.empty:
            latest_balance = past_sched["balance_minor"].iloc[-1] / 100.0
        else:
            latest_balance = original_principal

    total_interest_all_time = schedule_df["interest_minor"].sum() / 100.0
    principal_paid = max(0.0, original_principal - latest_balance)
    pct_repaid = (principal_paid / original_principal * 100.0) if original_principal > 0 else 0.0

    # Rate period fixed until countdown
    rate_period = conn.execute(
        "SELECT * FROM liability_rate_periods WHERE liability_id = ? ORDER BY from_date ASC LIMIT 1",
        (lib_id,),
    ).fetchone()
    fixed_until_str = rate_period["fixed_until"] if rate_period else "N/A"
    annual_rate = (rate_period["annual_rate"] * 100.0) if rate_period else 3.85

    # Fetch actual mortgage payments from bank accounts
    mortgage_cat_row = conn.execute("SELECT id FROM categories WHERE name = 'Mortgage'").fetchone()
    mortgage_cat_id = mortgage_cat_row["id"] if mortgage_cat_row else 11
    lib_pattern = lib.get("payment_match_pattern")

    where_or = ["t.category_id = ?"]
    p_params = [mortgage_cat_id]
    if lib_pattern:
        where_or.append("(t.merchant_normalized LIKE ? OR t.description_raw LIKE ?)")
        p_params.extend([f"%{lib_pattern}%", f"%{lib_pattern}%"])

    tx_query = f"""
    SELECT t.id, t.booking_date, a.name AS account,
           -t.amount_eur_minor / 100.0 AS amount_eur,
           COALESCE(NULLIF(t.merchant_normalized, ''), t.description_raw) AS merchant,
           t.description_raw
    FROM transactions t
    JOIN accounts a ON a.id = t.account_id
    WHERE ({' OR '.join(where_or)})
      AND t.amount_eur_minor < 0
    ORDER BY t.booking_date DESC
    """
    mortgage_tx_rows = conn.execute(tx_query, p_params).fetchall()
    total_bank_paid = sum(r["amount_eur"] for r in mortgage_tx_rows)

    # Top KPIs
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        kpi_card("Current Balance", f"€{latest_balance:,.2f}", subtext=f"Original €{original_principal:,.2f}")
    with c2:
        kpi_sub = f"{len(mortgage_tx_rows)} bank debits verified (€{total_bank_paid:,.2f})" if mortgage_tx_rows else f"{pct_repaid:.1f}% repaid"
        kpi_card("Principal Repaid", f"€{principal_paid:,.2f}", delta_str=f"{pct_repaid:.1f}%", is_positive=True, subtext=kpi_sub)
    with c3:
        kpi_card("Current Rate", f"{annual_rate:.2f}%", subtext=f"Fixed until {fixed_until_str}")
    with c4:
        kpi_card("Total Lifetime Interest", f"€{total_interest_all_time:,.2f}")

    st.progress(min(max(pct_repaid / 100.0, 0.0), 1.0), text=f"Repayment Progress: {pct_repaid:.1f}%")

    # Amortization curve
    section_header("Amortization Schedule", "Evolution of loan balance and principal paydown over 30 years")
    st.plotly_chart(build_mortgage_amortization_chart(schedule_df), use_container_width=True)

    # Monthly breakdown: interest vs principal
    section_header("Monthly Payment Composition", "Principal vs Interest per monthly installment")
    st.plotly_chart(build_mortgage_interest_principal_bar(schedule_df.head(60)), use_container_width=True)

    # Actual Mortgage Payments & Bank Debits
    section_header(
        "Actual Mortgage Payments (Bank Transactions)",
        f"Verified debits matched to {lib['name']} ({lib['lender']})",
    )
    if mortgage_tx_rows:
        matched_records = []
        for tx in mortgage_tx_rows:
            tx_month = tx["booking_date"][:7]
            # Find schedule row matching month
            sched_match = schedule_df[schedule_df["due_date"].str.startswith(tx_month)]
            if sched_match.empty:
                sched_match = schedule_df[schedule_df["due_date"] <= tx["booking_date"]].tail(1)

            if not sched_match.empty:
                s_row = sched_match.iloc[0]
                s_pay = s_row["payment_minor"] / 100.0
                s_p = s_row["principal_minor"] / 100.0
                s_i = s_row["interest_minor"] / 100.0
                s_due = s_row["due_date"]
                diff = abs(tx["amount_eur"] - s_pay)
                status = "Exact Match" if diff < 1.0 else ("Extra Payment" if tx["amount_eur"] > s_pay else "Partial Payment")
            else:
                s_pay = 0.0
                s_p = 0.0
                s_i = 0.0
                s_due = "-"
                status = "Unmatched Period"

            matched_records.append({
                "Date": tx["booking_date"],
                "Account": tx["account"],
                "Merchant": tx["merchant"],
                "Paid (€)": format_money(tx["amount_eur"]),
                "Scheduled Due": s_due,
                "Scheduled (€)": format_money(s_pay) if s_pay > 0 else "-",
                "Principal (€)": format_money(s_p) if s_p > 0 else "-",
                "Interest (€)": format_money(s_i) if s_i > 0 else "-",
                "Status": status,
            })

        matched_df = pd.DataFrame(matched_records)
        st.dataframe(matched_df, use_container_width=True, hide_index=True)
    else:
        st.info("No bank payment transactions assigned to mortgage yet. You can assign uncategorized bank payments to this mortgage from the Spending tab.")

    # Recorded Extra Repayments (Boetevrij Aflossen)
    extra_repayments = conn.execute(
        "SELECT * FROM liability_extra_payments WHERE liability_id = ? ORDER BY paid_date DESC",
        (lib_id,),
    ).fetchall()
    if extra_repayments:
        st.markdown("##### ⚡ Logged Extra Principal Repayments")
        extra_recs = []
        for er in extra_repayments:
            extra_recs.append({
                "Date": er["paid_date"],
                "Amount (€)": format_money(er["amount_minor"] / 100.0),
                "Benefit Strategy": "Lower Monthly Payment" if er["recalc"] == "lower_payment" else "Shorten Loan Term",
            })
        st.dataframe(pd.DataFrame(extra_recs), use_container_width=True, hide_index=True)

    # Simulator: Extra Repayments
    section_header("Extra Repayment Simulator (Boetevrij Aflossen)", "See the impact of penalty-free extra principal repayments")
    col_sim1, col_sim2 = st.columns(2)
    with col_sim1:
        extra_annual = st.number_input("Extra Lump-Sum Payment (€)", min_value=0.0, value=2500.0, step=500.0)
        recalc_choice = st.selectbox("Aflos Benefit", options=["lower_payment", "shorter_term"], format_func=lambda x: "Lower Monthly Payment" if x == "lower_payment" else "Shorten Loan Term")

    with col_sim2:
        # Run what-if
        sim_extras = [{"paid_date": date.today(), "amount_minor": int(extra_annual * 100), "recalc": recalc_choice}]
        sim_rates = [dict(rate_period)] if rate_period else []
        sim_sched = calculate_mortgage_schedule(
            loan_type=lib["loan_type"],
            principal_cents=lib["original_principal_minor"],
            start_date=datetime.strptime(lib["start_date"][:10], "%Y-%m-%d").date(),
            term_months=lib["term_months"],
            rate_periods=sim_rates,
            extra_payments=sim_extras,
        )
        sim_df = pd.DataFrame(sim_sched)
        sim_interest = sim_df["interest_minor"].sum() / 100.0
        interest_saved = total_interest_all_time - sim_interest
        st.metric("Total Interest Saved", f"€{max(0.0, interest_saved):,.2f}")
        if recalc_choice == "shorter_term":
            months_saved = len(schedule_df) - len(sim_df)
            st.metric("Months Saved", f"{max(0, months_saved)} months")

    conn.close()
