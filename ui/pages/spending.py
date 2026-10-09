import pandas as pd
import streamlit as st

from config import DB_PATH
from db import database
from services.analytics import detect_recurring_charges
from ui.charts import build_monthly_spending_bar, build_spending_donut
from ui.components import format_money, is_hidden, kpi_card, section_header
from ui.filters import build_where_clause, render_sidebar_filters


def render():
    st.title("Spending Analysis")
    filters = render_sidebar_filters()

    conn = database.connect(DB_PATH)
    where_sql, params = build_where_clause(filters, table_alias="t")

    # Strictly exclude internal transfers, savings/investments, and inflows from spending
    where_parts = []
    if where_sql:
        where_parts.append(where_sql.replace("WHERE ", "", 1))
    where_parts.append("t.amount_eur_minor < 0")
    where_parts.append("t.is_internal_transfer = 0")
    where_parts.append(
        "(c.kind IS NULL OR c.kind NOT IN ('savings', 'transfer', 'income'))")

    base_where = "WHERE " + " AND ".join(where_parts)

    # 1. Fetch Monthly Summary Aggregation
    monthly_query = f"""
    SELECT strftime('%Y-%m', t.booking_date) as month,
           COUNT(*) as tx_count,
           SUM(-t.amount_eur_minor) / 100.0 as total_spent,
           SUM(CASE WHEN c.kind = 'fixed' THEN -t.amount_eur_minor ELSE 0 END) / 100.0 as fixed_spent,
           SUM(CASE WHEN c.kind = 'discretionary' THEN -t.amount_eur_minor ELSE 0 END) / 100.0 as disc_spent,
           SUM(CASE WHEN c.id IS NULL THEN -t.amount_eur_minor ELSE 0 END) / 100.0 as uncat_spent
    FROM transactions t
    LEFT JOIN categories c ON c.id = t.category_id
    {base_where}
    GROUP BY month
    ORDER BY month DESC
    """
    monthly_df = pd.read_sql_query(monthly_query, conn, params=params)

    if monthly_df.empty:
        conn.close()
        st.info("No spending transactions found for the selected filter criteria.")
        return

    # 2. Fetch Detailed Spending Transactions
    detail_query = f"""
    SELECT t.booking_date,
           strftime('%Y-%m', t.booking_date) as month,
           t.merchant_normalized AS merchant,
           COALESCE(c.name, 'Uncategorized') AS category,
           COALESCE(p.name, c.name, 'Uncategorized') AS parent_category,
           COALESCE(c.kind, 'discretionary') AS category_kind,
           -t.amount_eur_minor / 100.0 AS amount_eur
    FROM transactions t
    LEFT JOIN categories c ON c.id = t.category_id
    LEFT JOIN categories p ON p.id = c.parent_id
    {base_where}
    """
    df_all = pd.read_sql_query(detail_query, conn, params=params)

    # 3. Monthly Scope Selector
    months = monthly_df["month"].tolist()
    month_options = months + ["All Months (Monthly Average)"]

    col_sel, col_empty = st.columns([2, 3])
    with col_sel:
        selected_scope = st.selectbox(
            "View Scope", options=month_options, index=0)

    # Filter data according to selected scope
    if selected_scope == "All Months (Monthly Average)":
        display_df = df_all.copy()
        n_months = max(1, len(months))
        total_spent = monthly_df["total_spent"].sum() / n_months
        fixed_spent = monthly_df["fixed_spent"].sum() / n_months
        disc_spent = monthly_df["disc_spent"].sum() / n_months
        uncat_spent = monthly_df["uncat_spent"].sum() / n_months
        header_title = f"Average Monthly Expenses ({n_months} months)"
    else:
        display_df = df_all[df_all["month"] == selected_scope].copy()
        month_row = monthly_df[monthly_df["month"] == selected_scope].iloc[0]
        total_spent = float(month_row["total_spent"])
        fixed_spent = float(month_row["fixed_spent"])
        disc_spent = float(month_row["disc_spent"])
        uncat_spent = float(month_row["uncat_spent"])
        header_title = f"Monthly Expenses ({selected_scope})"

    # KPI Row
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        kpi_card("Total Expenses",
                 f"€{total_spent:,.2f}", subtext=header_title)
    with c2:
        fixed_pct = (fixed_spent / total_spent * 100) if total_spent > 0 else 0
        kpi_card("Fixed Expenses",
                 f"€{fixed_spent:,.2f}", subtext=f"{fixed_pct:.1f}% of total")
    with c3:
        disc_pct = (disc_spent / total_spent * 100) if total_spent > 0 else 0
        kpi_card("Discretionary", f"€{disc_spent:,.2f}",
                 subtext=f"{disc_pct:.1f}% of total")
    with c4:
        uncat_pct = (uncat_spent / total_spent * 100) if total_spent > 0 else 0
        kpi_card("Uncategorized", f"€{uncat_spent:,.2f}",
                 subtext=f"{uncat_pct:.1f}% of total")

    # 4. Monthly Trend Chart & Summary Table
    section_header("Monthly Expenses Trend",
                   "Month-by-month spending broken down by expense kind")
    col_chart, col_tbl = st.columns([3, 2])
    with col_chart:
        st.plotly_chart(build_monthly_spending_bar(monthly_df),
                        use_container_width=True, theme=None)
    with col_tbl:
        tbl_df = monthly_df[["month", "total_spent",
                             "fixed_spent", "disc_spent", "uncat_spent"]].copy()
        tbl_df.columns = [
            "Month", "Total (€)", "Fixed (€)", "Discretionary (€)", "Uncategorized (€)"]
        if is_hidden():
            for col in ["Total (€)", "Fixed (€)", "Discretionary (€)", "Uncategorized (€)"]:
                tbl_df[col] = tbl_df[col].map(lambda x: format_money(x))
            st.dataframe(tbl_df, use_container_width=True, hide_index=True)
        else:
            st.dataframe(
                tbl_df,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Total (€)": st.column_config.NumberColumn("Total (€)", format="€%.2f"),
                    "Fixed (€)": st.column_config.NumberColumn("Fixed (€)", format="€%.2f"),
                    "Discretionary (€)": st.column_config.NumberColumn("Discretionary (€)", format="€%.2f"),
                    "Uncategorized (€)": st.column_config.NumberColumn("Uncategorized (€)", format="€%.2f"),
                }
            )

    # 5. Expense Breakdown & Top Merchants
    section_header(f"Expense Breakdown ({selected_scope})",
                   "Hierarchical spending across categories and merchants")
    if not display_df.empty:
        st.plotly_chart(build_spending_donut(display_df), use_container_width=True, theme=None)

        col_left, col_right = st.columns([1, 1])
        with col_left:
            section_header("Top Merchants",
                           f"Highest spending in {selected_scope}")
            top_merchants = display_df.groupby(
                "merchant")["amount_eur"].sum().reset_index()
            top_merchants = top_merchants.sort_values(
                by="amount_eur", ascending=False).head(10)
            top_merchants.columns = ["Merchant", "Spent (€)"]
            if is_hidden():
                top_merchants["Spent (€)"] = top_merchants["Spent (€)"].map(
                    lambda x: format_money(x))
                spent_cfg = st.column_config.TextColumn(
                    "Spent (€)", disabled=True)
            else:
                spent_cfg = st.column_config.NumberColumn(
                    "Spent (€)", format="€%.2f", disabled=True)
            st.dataframe(
                top_merchants,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Merchant": st.column_config.TextColumn("Merchant", width="medium"),
                    "Spent (€)": spent_cfg
                }
            )

        with col_right:
            section_header("Subscription Leak Detector",
                           "Recurring services and annual commitments")
            all_tx_rows = [dict(r) for r in conn.execute(
                "SELECT * FROM v_transactions ORDER BY booking_date DESC").fetchall()]
            recurring = detect_recurring_charges(all_tx_rows)
            if recurring:
                rec_df = pd.DataFrame(recurring)[
                    ["merchant", "cadence", "amount_eur", "annual_cost_eur"]]
                rec_df.columns = ["Merchant", "Cadence",
                                  "Cost / Cycle", "Annual Cost (€)"]
                if is_hidden():
                    rec_df["Cost / Cycle"] = rec_df["Cost / Cycle"].map(
                        lambda x: format_money(x))
                    rec_df["Annual Cost (€)"] = rec_df["Annual Cost (€)"].map(
                        lambda x: format_money(x))
                    cost_cfg = st.column_config.TextColumn(
                        "Cost / Cycle", disabled=True)
                    ann_cfg = st.column_config.TextColumn(
                        "Annual Cost (€)", disabled=True)
                else:
                    cost_cfg = st.column_config.NumberColumn(
                        "Cost / Cycle", format="€%.2f", disabled=True)
                    ann_cfg = st.column_config.NumberColumn(
                        "Annual Cost (€)", format="€%.2f", disabled=True)

                st.dataframe(
                    rec_df,
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "Merchant": st.column_config.TextColumn("Merchant", width="medium"),
                        "Cost / Cycle": cost_cfg,
                        "Annual Cost (€)": ann_cfg
                    }
                )
            else:
                st.caption("No subscriptions detected.")

    # 6. Top Uncategorized Expenses & Mortgage Assignment
    section_header("Top Uncategorized Expenses",
                   "Review, categorize, or assign your largest uncategorized expenses to mortgage")

    # Scope selection toggle: allow viewing for current month scope or across all months
    scope_choice = "All Filtered Months"
    if selected_scope != "All Months (Monthly Average)":
        col_sc1, _ = st.columns([2, 3])
        with col_sc1:
            scope_choice = st.radio(
                "Uncategorized Scope",
                options=[
                    f"Selected Month ({selected_scope})", "All Filtered Months"],
                horizontal=True,
                key="uncat_spending_scope_toggle",
            )

    uncat_where_parts = []
    if where_sql:
        uncat_where_parts.append(where_sql.replace("WHERE ", "", 1))
    uncat_where_parts.append("t.category_id IS NULL")
    uncat_where_parts.append("t.amount_eur_minor < 0")
    uncat_where_parts.append("t.is_internal_transfer = 0")

    uncat_params = list(params)
    if scope_choice.startswith("Selected Month") and selected_scope != "All Months (Monthly Average)":
        uncat_where_parts.append("strftime('%Y-%m', t.booking_date) = ?")
        uncat_params.append(selected_scope)

    uncat_query = f"""
    SELECT t.id,
           t.booking_date,
           a.name AS account,
           COALESCE(NULLIF(t.merchant_normalized, ''), t.description_raw) AS merchant,
           -t.amount_eur_minor / 100.0 AS amount_eur,
           t.description_raw
    FROM transactions t
    JOIN accounts a ON a.id = t.account_id
    WHERE {" AND ".join(uncat_where_parts)}
    ORDER BY abs(t.amount_eur_minor) DESC
    LIMIT 10
    """
    uncat_df = pd.read_sql_query(uncat_query, conn, params=uncat_params)

    if uncat_df.empty:
        st.success("🎉 No uncategorized expenses found in this scope!")
    else:
        cat_rows = conn.execute(
            "SELECT id, name FROM categories ORDER BY name ASC").fetchall()
        cat_names = [r["name"] for r in cat_rows]
        cat_name_to_id = {r["name"]: r["id"] for r in cat_rows}

        st.caption(
            f"Showing top {len(uncat_df)} uncategorized expenses by amount. Select a category below and click **Save Categorizations**, or use the Mortgage Assignment tool.")

        edit_df = uncat_df[["id", "booking_date",
                            "account", "merchant", "amount_eur"]].copy()
        edit_df["category"] = None

        if is_hidden():
            edit_df_display = edit_df.copy()
            edit_df_display["amount_eur"] = edit_df_display["amount_eur"].map(
                lambda x: format_money(x))
            amount_col_cfg = st.column_config.TextColumn(
                "Amount (€)", disabled=True)
        else:
            edit_df_display = edit_df
            amount_col_cfg = st.column_config.NumberColumn(
                "Amount (€)", format="€%.2f", disabled=True)

        edited_uncat = st.data_editor(
            edit_df_display,
            column_config={
                "id": None,
                "booking_date": st.column_config.DateColumn("Date", disabled=True),
                "account": st.column_config.TextColumn("Account", disabled=True),
                "merchant": st.column_config.TextColumn("Merchant / Description", width="medium", disabled=True),
                "amount_eur": amount_col_cfg,
                "category": st.column_config.SelectboxColumn("Assign Category", options=cat_names, required=False),
            },
            disabled=["id", "booking_date",
                      "account", "merchant", "amount_eur"],
            use_container_width=True,
            hide_index=True,
            key="spending_uncat_editor",
        )

        col_save, _ = st.columns([1, 3])
        with col_save:
            if st.button("Save Categorizations", type="primary", key="btn_save_uncat"):
                saved_count = 0
                for idx, row in edited_uncat.iterrows():
                    new_cat = row["category"]
                    if new_cat and new_cat in cat_name_to_id:
                        new_cat_id = cat_name_to_id[new_cat]
                        tx_id = int(uncat_df.loc[idx, "id"])
                        merchant = str(uncat_df.loc[idx, "merchant"])
                        with conn:
                            conn.execute(
                                "UPDATE transactions SET category_id = ?, category_source = 'user' WHERE id = ?",
                                (new_cat_id, tx_id),
                            )
                            if merchant:
                                database.upsert_category_rule(
                                    conn, merchant, new_cat_id, source="user")
                            if new_cat == "Mortgage":
                                conn.execute(
                                    "UPDATE liabilities SET payment_match_pattern = COALESCE(payment_match_pattern, ?) WHERE id = (SELECT id FROM liabilities LIMIT 1)",
                                    (merchant,),
                                )
                        saved_count += 1

                if saved_count > 0:
                    st.success(
                        f"Successfully categorized {saved_count} transaction(s) and updated rules!")
                    st.rerun()

        # Dedicated Mortgage Assignment Tool
        liabilities = conn.execute("SELECT * FROM liabilities").fetchall()
        with st.expander("🏠 Assign Transaction to Mortgage Details & Tab Info", expanded=True):
            st.markdown(
                "Link an uncategorized payment directly to your mortgage schedule and details. "
                "This assigns the transaction to the **Mortgage** category, records it against your loan liability, "
                "and updates the **Mortgage** tab info."
            )

            tx_options = []
            tx_lookup = {}
            for _, r in uncat_df.iterrows():
                lbl = f"{r['booking_date']} — {format_money(r['amount_eur'])} — {r['merchant'][:45]}"
                tx_options.append(lbl)
                tx_lookup[lbl] = r

            cm1, cm2, cm3 = st.columns([2, 1, 1])
            with cm1:
                chosen_tx_lbl = st.selectbox(
                    "Select Uncategorized Transaction", options=tx_options, key="mortgage_tx_select")
                chosen_tx = tx_lookup[chosen_tx_lbl]
            with cm2:
                if liabilities:
                    lib_map = {
                        f"{lib['name']} ({lib['lender']})": lib for lib in liabilities}
                    chosen_lib_lbl = st.selectbox("Mortgage Liability", options=list(
                        lib_map.keys()), key="mortgage_lib_select")
                    chosen_lib = lib_map[chosen_lib_lbl]
                else:
                    chosen_lib = None
                    st.warning(
                        "No mortgage loan configured yet. Set one up in Settings or Mortgage tab.")
            with cm3:
                payment_kind = st.selectbox(
                    "Payment Assignment",
                    options=["Monthly Installment",
                             "Extra Repayment (Boetevrij)"],
                    key="mortgage_assign_kind",
                )

            recalc_strat = "lower_payment"
            if payment_kind == "Extra Repayment (Boetevrij)":
                recalc_strat = st.selectbox(
                    "Recalculation Benefit",
                    options=["lower_payment", "shorter_term"],
                    format_func=lambda x: "Lower Monthly Payment" if x == "lower_payment" else "Shorten Loan Term",
                    key="mortgage_recalc_strat",
                )

            if st.button("Confirm Mortgage Assignment", type="primary", key="btn_confirm_mortgage_assign", disabled=chosen_lib is None):
                mortgage_cat_id = cat_name_to_id.get("Mortgage", 11)
                tx_id = int(chosen_tx["id"])
                tx_date = str(chosen_tx["booking_date"])
                tx_amount_minor = int(round(chosen_tx["amount_eur"] * 100))
                tx_merchant = str(chosen_tx["merchant"])

                with conn:
                    # 1. Update transaction category to Mortgage
                    conn.execute(
                        "UPDATE transactions SET category_id = ?, category_source = 'user' WHERE id = ?",
                        (mortgage_cat_id, tx_id),
                    )
                    # 2. Update merchant category rule
                    if tx_merchant:
                        database.upsert_category_rule(
                            conn, tx_merchant, mortgage_cat_id, source="user")

                    # 3. Save payment match pattern on liability if unset
                    conn.execute(
                        "UPDATE liabilities SET payment_match_pattern = COALESCE(payment_match_pattern, ?) WHERE id = ?",
                        (tx_merchant, chosen_lib["id"]),
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
                            (chosen_lib["id"], tx_date,
                             tx_amount_minor, recalc_strat),
                        )

                # Resync schedule if extra payment
                if payment_kind == "Extra Repayment (Boetevrij)":
                    from services.mortgage import sync_liability_schedule
                    sync_liability_schedule(conn, chosen_lib["id"])

                st.success(
                    f"Successfully assigned {format_money(chosen_tx['amount_eur'])} on {tx_date} to {chosen_lib['name']}! "
                    f"View detailed breakdown on the Mortgage tab."
                )
                st.rerun()

    conn.close()
