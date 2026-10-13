from datetime import date, datetime
import pandas as pd
import streamlit as st

from config import DB_PATH
from db import database
from money import Money
from services.mortgage import calculate_mortgage_schedule, sync_liability_schedule
from ui.charts import build_mortgage_amortization_chart, build_mortgage_interest_principal_bar
from ui.components import format_money, is_hidden, kpi_card, mask_if_hidden, section_header
from ui.theme import render_chart


def render():

    conn = database.connect(DB_PATH)
    liabilities = conn.execute("SELECT * FROM liabilities").fetchall()

    if not liabilities:
        col_msg, col_btn = st.columns([0.7, 0.3], vertical_alignment="bottom")
        with col_btn:
            from ui.dialogs import mortgage_config_dialog
            if st.button("⚙️ Configure Mortgage / Loan", type="primary", width="stretch"):
                mortgage_config_dialog()
        st.info("No mortgage or liability configured yet. Enter your mortgage details below to generate the schedule.")
        conn.close()
        return

    from ui.dialogs import mortgage_config_dialog
    col_space, col_btn = st.columns([0.7, 0.3], vertical_alignment="bottom")
    with col_btn:
        if st.button("⚙️ Add / Edit Mortgage Configuration", width="stretch"):
            mortgage_config_dialog(liabilities[0]["id"])

    lib = dict(liabilities[0])
    lib_id = lib["id"]

    # Schedule is pre-generated on save.
    # No need to sync on every page load.

    schedule_df = pd.read_sql_query(
        "SELECT * FROM liability_schedule WHERE liability_id = ? ORDER BY month_idx ASC",
        conn,
        params=(lib_id,),
    )

    if schedule_df.empty:
        conn.close()
        st.warning("Schedule could not be computed. Please edit the configuration to generate it.")
        return

    original_principal = Money.from_cents(lib["original_principal_minor"]).to_major()

    today_str = date.today().isoformat()
    if lib.get("balance_override_minor"):
        latest_balance = Money.from_cents(lib["balance_override_minor"]).to_major()
    else:
        past_sched = schedule_df[schedule_df["due_date"] <= today_str]
        if not past_sched.empty:
            latest_balance = Money.from_cents(past_sched["balance_minor"].iloc[-1]).to_major()
        else:
            latest_balance = original_principal

    total_interest_all_time = Money.from_cents(schedule_df["interest_minor"].sum()).to_major()
    principal_paid = max(0.0, original_principal - latest_balance)
    pct_repaid = (principal_paid / original_principal *
                  100.0) if original_principal > 0 else 0.0

    # Rate period fixed until countdown
    rate_period = conn.execute(
        "SELECT * FROM liability_rate_periods WHERE liability_id = ? ORDER BY from_date ASC LIMIT 1",
        (lib_id,),
    ).fetchone()
    fixed_until_str = rate_period["fixed_until"] if rate_period else "N/A"
    annual_rate = (rate_period["annual_rate"] * 100.0) if rate_period else 3.85

    # Fetch actual mortgage payments from bank accounts
    mortgage_cat_row = conn.execute(
        "SELECT id FROM categories WHERE name = 'Mortgage'").fetchone()
    mortgage_cat_id = mortgage_cat_row["id"] if mortgage_cat_row else 11
    lib_pattern = lib.get("payment_match_pattern")

    where_or = ["t.category_id = ?"]
    p_params = [mortgage_cat_id]
    if lib_pattern:
        where_or.append(
            "(t.merchant_normalized LIKE ? OR t.description_raw LIKE ?)")
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

    home_val = Money.from_cents(lib["home_value_minor"]).to_major() if lib.get(
        "home_value_minor") is not None else original_principal
    home_equity = home_val - latest_balance

    # Top KPIs
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        kpi_card("Current Balance", f"€{latest_balance:,.2f}",
                 subtext=f"Original €{original_principal:,.2f}")
    with c2:
        kpi_sub = f"Property Value €{home_val:,.2f} ({pct_repaid:.1f}% paid)"
        kpi_card("Home Equity", f"€{home_equity:,.2f}",
                 delta_str=f"+€{principal_paid:,.0f}" if principal_paid > 0 else None, subtext=kpi_sub)
    with c3:
        kpi_card("Current Rate", f"{annual_rate:.2f}%",
                 subtext=f"Fixed until {fixed_until_str}")
    with c4:
        kpi_card("Total Lifetime Interest", f"€{total_interest_all_time:,.2f}")

    prog_text = mask_if_hidden(f"Repayment Progress: {pct_repaid:.1f}%")
    st.progress(min(max(pct_repaid / 100.0, 0.0), 1.0),
                text=prog_text)

    # Amortization curve
    with section_header("Amortization Schedule",
                   "Evolution of loan balance and principal paydown over 30 years"):
        with st.container(border=True):
            st.markdown("##### 📈 Loan Balance & Principal Amortization")
            render_chart(build_mortgage_amortization_chart(schedule_df))

        # Monthly breakdown: interest vs principal
    with section_header("Monthly Payment Composition",
                   "Principal vs Interest per monthly installment"):
        with st.container(border=True):
            st.markdown("##### 📊 Monthly Installment Composition (Interest vs Principal)")
            render_chart(build_mortgage_interest_principal_bar(schedule_df.head(60)))

        # Actual Mortgage Payments & Bank Debits
    with section_header(
        "Actual Mortgage Payments (Bank Transactions)",
        f"Verified debits matched to {lib['name']} ({lib['lender']})",
    ):
        if mortgage_tx_rows:
            matched_records = []
            for tx in mortgage_tx_rows:
                tx_month = tx["booking_date"][:7]
                # Find schedule row matching month
                sched_match = schedule_df[schedule_df["due_date"].str.startswith(
                    tx_month)]
                if sched_match.empty:
                    sched_match = schedule_df[schedule_df["due_date"] <= tx["booking_date"]].tail(
                        1)

                if not sched_match.empty:
                    s_row = sched_match.iloc[0]
                    s_pay = Money.from_cents(s_row["payment_minor"]).to_major()
                    s_p = Money.from_cents(s_row["principal_minor"]).to_major()
                    s_i = Money.from_cents(s_row["interest_minor"]).to_major()
                    s_due = s_row["due_date"]
                    diff = abs(tx["amount_eur"] - s_pay)
                    status = "Exact Match" if diff < 1.0 else (
                        "Extra Payment" if tx["amount_eur"] > s_pay else "Partial Payment")
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
                    "Paid (€)": tx["amount_eur"],
                    "Scheduled Due": s_due,
                    "Scheduled (€)": s_pay,
                    "Principal (€)": s_p,
                    "Interest (€)": s_i,
                    "Status": status,
                })

            matched_df = pd.DataFrame(matched_records)
            if is_hidden():
                if "Merchant" in matched_df.columns:
                    matched_df["Merchant"] = "****"
                for c in ["Paid (€)", "Scheduled (€)", "Principal (€)", "Interest (€)"]:
                    matched_df[c] = matched_df[c].map(lambda x: format_money(x) if isinstance(
                        x, (int, float)) and x > 0 else ("-" if x == 0.0 else x))
                st.dataframe(matched_df, width="stretch", hide_index=True)
            else:
                num_cfg = st.column_config.NumberColumn(
                    "Amount (€)", format="€%.2f", disabled=True)
                st.dataframe(
                    matched_df,
                    width="stretch",
                    hide_index=True,
                    column_config={
                        "Merchant": st.column_config.TextColumn("Merchant", width="medium"),
                        "Paid (€)": num_cfg,
                        "Scheduled (€)": num_cfg,
                        "Principal (€)": num_cfg,
                        "Interest (€)": num_cfg,
                    }
                )
        else:
            st.info("No bank payment transactions assigned to mortgage yet. You can assign uncategorized bank payments to this mortgage from the Spending tab.")

        # Recorded Extra Repayments (Boetevrij Aflossen)
        extra_repayments = conn.execute(
            "SELECT * FROM liability_extra_payments WHERE liability_id = ? ORDER BY paid_date DESC",
            (lib_id,),
        ).fetchall()
        if extra_repayments:
            st.markdown("##### ⚡ Logged Extra Principal Repayments")
            with st.container(border=True):
                for er in extra_repayments:
                    er_date = er["paid_date"]
                    er_amt = Money.from_cents(er["amount_minor"]).to_major()
                    er_strat = "Lower Monthly Payment" if er["recalc"] == "lower_payment" else "Shorten Loan Term"
                    amt_str = "€****" if is_hidden() else f"€{er_amt:,.2f}"

                    col_edate, col_eamt, col_estrat, col_eact = st.columns([2, 2, 4, 1.5], vertical_alignment="center")
                    with col_edate:
                        st.markdown(f"**{er_date}**")
                    with col_eamt:
                        st.markdown(amt_str)
                    with col_estrat:
                        st.caption(f"Strategy: {er_strat}")
                    with col_eact:
                        if st.button("🗑️ Delete", key=f"del_extra_pmt_{lib_id}_{er_date}", help=f"Delete repayment from {er_date}"):
                            del_conn = database.connect(DB_PATH)
                            try:
                                with del_conn:
                                    del_conn.execute(
                                        "DELETE FROM liability_extra_payments WHERE liability_id = ? AND paid_date = ?",
                                        (lib_id, er_date),
                                    )
                                sync_liability_schedule(del_conn, lib_id)
                            finally:
                                del_conn.close()
                            st.success(f"Deleted extra repayment of {amt_str} from {er_date}")
                            st.rerun()

        # Simulator: Extra Repayments
    with section_header("Extra Repayment Simulator (Boetevrij Aflossen)",
                   "See the impact of penalty-free extra principal repayments"):
        col_sim1, col_sim2 = st.columns(2)
        with col_sim1:
            extra_annual = st.number_input(
                "Extra Lump-Sum Payment (€)", min_value=0.0, value=2500.0, step=500.0)
            recalc_choice = st.selectbox("Aflos Benefit", options=[
                                         "lower_payment", "shorter_term"], format_func=lambda x: "Lower Monthly Payment" if x == "lower_payment" else "Shorten Loan Term")

        with col_sim2:
            # Run what-if
            sim_extras = [{"paid_date": date.today(), "amount_minor": Money.from_major(extra_annual).cents, "recalc": recalc_choice}]
            sim_rates = [dict(rate_period)] if rate_period else []
            sim_sched = calculate_mortgage_schedule(
                loan_type=lib["loan_type"],
                principal_cents=lib["original_principal_minor"],
                start_date=datetime.strptime(
                    lib["start_date"][:10], "%Y-%m-%d").date(),
                term_months=lib["term_months"],
                rate_periods=sim_rates,
                extra_payments=sim_extras,
            )
            sim_df = pd.DataFrame(sim_sched)
            sim_interest = Money.from_cents(sim_df["interest_minor"].sum()).to_major()
            interest_saved = total_interest_all_time - sim_interest
            st.metric("Total Interest Saved", f"€{max(0.0, interest_saved):,.2f}")
            if recalc_choice == "shorter_term":
                months_saved = len(schedule_df) - len(sim_df)
                st.metric("Months Saved", f"{max(0, months_saved)} months")

        conn.close()
